"""Question/instruction custody and resource controls; no scientist inference."""
import json
import os
from pathlib import Path
import subprocess

from click.testing import CliRunner
import pytest

import vcs_protocol as p


@pytest.mark.parametrize("agent", ["codex", "claude"])
def test_default_inputs_are_frozen_and_survive_source_changes(tmp_path, monkeypatch, agent):
    instructions = (p.ROOT / "protocols/instructions.txt").read_bytes()
    question = (p.ROOT / "protocols/task-balls.txt").read_bytes()
    source = tmp_path / "source"
    (source / "protocols").mkdir(parents=True)
    task_file = source / "protocols/task-balls.txt"
    instruction_file = source / "protocols/instructions.txt"
    task_file.write_bytes(question)
    instruction_file.write_bytes(instructions)
    monkeypatch.setattr(p, "ROOT", source)
    monkeypatch.setattr(p, "runtime_config", lambda *a: {"agent": a[3]})
    monkeypatch.setattr(p, "execute_cycle", lambda run, state: p.write_json(run / "control/state.json", state))
    run = tmp_path / "run"
    result = CliRunner().invoke(p.main, ["start", "--run-dir", str(run), "--agent", agent])
    assert result.exit_code == 0, result.output
    state = p.load_state(run)
    assert state["runtime"]["agent"] == agent
    assert {item.name for item in (run / "control/protocol").iterdir()} == {"task.txt", "instructions.txt"}
    assert (run / "control/protocol/instructions.txt").read_bytes() == instructions
    assert (run / "control/protocol/task.txt").read_bytes() == question
    instruction_file.write_text("Changed scientist instructions")
    task_file.write_text("Changed scientific question")
    assert p.protocol_text(run, state) == (instructions.decode(), question.decode())


def test_missing_snapshot_metadata_stops_before_authentication_or_inference(tmp_path, monkeypatch):
    run = tmp_path / "run"
    (run / "work").mkdir(parents=True)
    (run / "control").mkdir()
    calls = []
    monkeypatch.setattr(p, "ensure_subscription", lambda *a: calls.append("authentication"))
    monkeypatch.setattr(p, "run_container", lambda *a, **k: calls.append("inference"))
    state = {"status": "new", "cycles": 0, "runtime": {"agent": "codex"}, "attempts": []}
    p._execute_once(run, state)
    assert state["status"] == "scientist_failed" and state["cycles"] == 0
    assert calls == []


def test_client_identity_requires_explicit_recorded_agent():
    with pytest.raises(ValueError, match="unsupported scientist client"):
        p.client_name({})


@pytest.fixture
def custom_run(tmp_path, monkeypatch):
    task = tmp_path / "question.txt"
    instructions = tmp_path / "instructions-source.txt"
    task.write_bytes("Question α.\r\nOnly current observations.\n".encode())
    instructions.write_bytes(b"Current scientist instructions.\r\nNo prior solutions.\n")
    run = tmp_path / "run"
    with monkeypatch.context() as setup:
        setup.setattr(p, "runtime_config", lambda *a: {"agent": a[3]})
        setup.setattr(p, "execute_cycle", lambda run, state: p.write_json(run / "control/state.json", state))
        result = CliRunner().invoke(p.main, ["start", "--run-dir", str(run), "--task-file", str(task),
                                           "--instructions-file", str(instructions), "--memory", "4g", "--cpus", "2"])
    assert result.exit_code == 0, result.output
    return run, p.load_state(run), task, instructions


def test_snapshots_preserve_exact_bytes_sources_and_hashes(custom_run):
    run, state, task, instructions = custom_run
    assert state["version"] == 2
    for name, source in [("task.txt", task), ("instructions.txt", instructions)]:
        assert (run / "control/protocol" / name).read_bytes() == source.read_bytes()
        assert state["protocol_inputs"][name]["sha256"] == p.digest(source)
        assert state["protocol_inputs"][name]["source"] == str(source.resolve())
    assert state["runtime"]["memory"] == "4g" and state["runtime"]["cpus"] == "2"
    assert list((run / "work").iterdir()) == []


@pytest.mark.parametrize("agent", ["codex", "claude"])
def test_prompt_uses_frozen_bytes_after_live_sources_change(custom_run, monkeypatch, agent):
    run, state, task, instructions = custom_run
    expected_task, expected_instructions = task.read_bytes().decode(), instructions.read_bytes().decode()
    task.write_text("Changed live question")
    instructions.write_text("Changed live instructions")
    state["runtime"].update(agent=agent, model=p.DEFAULT_MODELS[agent])
    monkeypatch.setattr(p, "ensure_subscription", lambda *a: None)
    monkeypatch.setattr(p, "docker_base", lambda *a, **kw: ["docker", "run"])
    calls = []
    def client(cmd, **kwargs):
        calls.append((cmd, kwargs["input"]))
        return subprocess.CompletedProcess(cmd, 5)
    monkeypatch.setattr(p, "run_container", client)
    p._execute_once(run, state)
    assert len(calls) == 1
    cmd, prompt = calls[0]
    assert expected_task in prompt and expected_instructions in prompt
    assert "Changed live" not in prompt
    assert cmd[cmd.index("--model") + 1] == p.DEFAULT_MODELS[agent]
    assert ("exec" in cmd) == (agent == "codex")


@pytest.mark.parametrize("name", ["task.txt", "instructions.txt"])
def test_snapshot_mutation_blocks_cycle_and_resume_before_client(custom_run, monkeypatch, name):
    run, state, _, _ = custom_run
    (run / "control/protocol" / name).write_text("mutated host snapshot")
    calls = []
    monkeypatch.setattr(p, "ensure_subscription", lambda *a: calls.append("login"))
    monkeypatch.setattr(p, "run_container", lambda *a, **kw: calls.append("client"))
    p._execute_once(run, state)
    assert state["status"] == "scientist_failed" and state["cycles"] == 0
    result = CliRunner().invoke(p.main, ["resume", str(run)])
    assert result.exit_code != 0 and "snapshot changed" in result.output
    assert calls == []


def fake_config(tmp_path, agent="codex"):
    return {"agent": agent, "lean": str(tmp_path / "lean"), "click": str(tmp_path / "click"), "libraries": [],
            "code_mode_host": str(tmp_path / "companion"),
            "auth": str(tmp_path / "auth"), "client_binary": str(tmp_path / agent),
            "memory": "4g", "cpus": "2"}


@pytest.mark.parametrize("agent", ["codex", "claude"])
def test_mounts_only_selected_protocol_files_and_resources(custom_run, agent):
    run, _, _, _ = custom_run
    cmd = p.docker_base(fake_config(run.parent, agent), run / "work", scientist=True)
    mounts = [cmd[i + 1] for i, part in enumerate(cmd[:-1]) if part == "--mount"]
    protocol = [entry for entry in mounts if "dst=/protocol" in entry]
    assert len(protocol) == 2
    for name in ["instructions.txt", "task.txt"]:
        assert f"type=bind,src={run}/control/protocol/{name},dst=/protocol/{name},readonly" in protocol
    assert not any(f"src={run}/control," in entry or f"src={p.ROOT}/protocols," in entry for entry in mounts)
    assert "--memory=4g" in cmd and "--cpus=2" in cmd
    checker = p.docker_base(fake_config(run.parent, agent), run / "control/attempt-001")
    assert "--memory=4g" in checker and "--cpus=2" in checker
    assert not any("dst=/protocol" in part or "dst=/native-auth" in part for part in checker)


@pytest.mark.parametrize("memory,cpus", [("0", "2"), ("0g", "2"), ("127m", "2"), ("9g", "2"),
    ("4g", "0"), ("4g", "-1"), ("4g", "NaN"), ("4g", "inf"), ("4g", "9"), ("4g", "bad")])
def test_invalid_resources_rejected_before_native_runtime(tmp_path, monkeypatch, memory, cpus):
    calls = []
    monkeypatch.setattr(p, "runtime_config", lambda *a: calls.append(a))
    result = CliRunner().invoke(p.main, ["start", "--run-dir", str(tmp_path / "run"), "--memory", memory, "--cpus", cpus])
    assert result.exit_code != 0 and calls == []
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize("agent,event,expected", [
    ("codex", {"type": "error", "message": "You've hit your usage limit"}, "quota"),
    ("codex", {"type": "turn.failed", "error": {"message": "Token expired"}}, "authentication"),
    ("codex", {"type": "error", "message": "Failed to refresh token: Read-only file system"}, "authentication"),
    ("codex", {"type": "item.completed", "item": {"text": "quota authentication failed"}}, None),
    ("claude", {"type": "assistant", "error": "rate_limit"}, "quota"),
    ("claude", {"type": "assistant", "error": "authentication_failed"}, "authentication"),
    ("claude", {"type": "result", "subtype": "error_max_turns", "errors": []}, None),
    ("claude", {"type": "assistant", "message": {"content": "authentication quota"}}, None),
])
def test_client_failure_metadata_classifier(tmp_path, agent, event, expected):
    trace = tmp_path / "trace.jsonl"
    trace.write_text(json.dumps(event) + "\n")
    assert p.client_failure_kind(trace, agent) == expected


def test_real_snapshot_visibility_without_inference(custom_run):
    library = os.environ.get("VCS_TEST_LIBRARY_ROOT")
    if not library:
        pytest.skip("set VCS_TEST_LIBRARY_ROOT for real Docker protocol visibility")
    run, _, _, _ = custom_run
    # Native binary/version and credential metadata only; scientist command never runs.
    config = p.runtime_config(Path(library))
    config.update(memory="4g", cpus="2")
    (run / "control/protocol/other-task.txt").write_text("must be hidden")
    (run / "control/prior-answer.txt").write_text("must be hidden")
    script = """from pathlib import Path
assert sorted(p.name for p in Path('/protocol').iterdir()) == ['instructions.txt', 'task.txt']
assert not Path('/protocol/other-task.txt').exists()
assert not Path('/protocol/prior-answer.txt').exists()
assert not Path('/work/../control').exists()
for name in ['instructions.txt', 'task.txt']:
    try:
        Path('/protocol', name).write_text('mutate')
    except OSError:
        pass
    else:
        raise AssertionError('writable snapshot')
print('two read-only protocol files visible; sibling controls hidden')
"""
    cmd = p.docker_base(config, run / "work", scientist=True) + [p.IMAGE, "python", "-c", script]
    result = p.run_container(cmd, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("event,kind", [
    ({"type": "error", "message": "You've hit your usage limit"}, "quota"),
    ({"type": "turn.failed", "error": {"message": "authentication failed"}}, "authentication"),
])
def test_codex_zero_exit_auth_quota_never_checks_candidate_or_retries(custom_run, monkeypatch, event, kind):
    run, state, _, _ = custom_run
    calls = []
    monkeypatch.setattr(p, "ensure_subscription", lambda *a: None)
    monkeypatch.setattr(p, "docker_base", lambda *a, **kw: ["docker", "run"])
    monkeypatch.setattr(p, "freeze_and_check", lambda *a: pytest.fail("client failure candidate checked"))
    (run / "work/candidate.json").write_text("stale candidate must be ignored")
    def client(cmd, **kwargs):
        calls.append(cmd)
        kwargs["stdout"].write(json.dumps(event) + "\n")
        return subprocess.CompletedProcess(cmd, 0)
    monkeypatch.setattr(p, "run_container", client)
    p.execute_cycle(run, state)
    assert len(calls) == 1 and state["status"] == "scientist_failed"
    assert state["failure_kind"] == kind


def test_expected_matrix_hash_checks_exact_bytes_after_runtime_preflight(tmp_path, monkeypatch):
    task = tmp_path / "task.txt"
    task.write_text("matrix frozen question\n")
    instructions = tmp_path / "instructions.txt"
    instructions.write_text("matrix frozen instructions\n")
    expected = p.digest(task)
    def runtime(*args):
        # Mutation in the parent-verification → child-freeze window.
        task.write_text("different question after matrix verified\n")
        return {"agent": "codex"}
    monkeypatch.setattr(p, "runtime_config", runtime)
    monkeypatch.setattr(p, "execute_cycle", lambda *a: pytest.fail("changed matrix input reached inference"))
    result = CliRunner().invoke(p.main, ["start", "--run-dir", str(tmp_path / "run"), "--task-file", str(task),
        "--instructions-file", str(instructions), "--expected-task-sha256", expected,
        "--expected-instructions-sha256", p.digest(instructions)])
    assert result.exit_code != 0
    assert isinstance(result.exception, ValueError) and "expected matrix hash" in str(result.exception)
