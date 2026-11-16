"""Protocol controls: mock scientific candidates are NOT scientist runs."""
import json
import os
from pathlib import Path
import subprocess

import pytest
from click.testing import CliRunner

import vcs_protocol as p


@pytest.fixture
def candidate(tmp_path):
    (tmp_path / "Model.lean").write_text("import Mathlib.Data.Nat.Basic\n"
        "def given_count : Nat := 50\n"
        "theorem model_result : given_count = 50 := rfl\n"
        "theorem update_result : 1 = 1 := rfl\n"
        "theorem prediction_result : 2 = 2 := rfl\n")
    (tmp_path / "report.txt").write_text("MOCK CONTROL ONLY. No scientific inference is claimed.")
    m = {"proof_file": "Model.lean", "narrative_file": "report.txt",
         "conclusions": {"model": "model_result", "update": "update_result", "prediction": "prediction_result"},
         "user_facts": ["control"], "model_choices": ["control"], "sources": [], "incorporated_inputs": [],
         "proof_scope": "MOCK CHECKER CONTROL ONLY, not a substantive balls solution."}
    p.write_json(tmp_path / "candidate.json", m)
    return tmp_path


def test_help_does_not_run_model():
    result = CliRunner().invoke(p.main, ["--help"])
    assert result.exit_code == 0
    assert "start" in result.output and "review" in result.output


def test_import_and_metaprogram_contract(candidate):
    source = (candidate / "Model.lean").read_text()
    names = list(p.read_json(candidate / "candidate.json")["conclusions"].values())
    p.validate_source(source, names)
    for bad in ["import Task\n" + source, source + '\nrun_cmd pure ()', source + '\n#eval 1',
                source.replace("model_result :", "model_result (x : Nat) :"), source + '\ndef x := "secret"']:
        with pytest.raises(ValueError):
            p.validate_source(bad, names)


def test_paths_and_manifest_fail_closed(candidate):
    manifest = p.read_json(candidate / "candidate.json")
    manifest["proof_file"] = "../outside.lean"
    p.write_json(candidate / "candidate.json", manifest)
    with pytest.raises(ValueError):
        p.load_candidate(candidate, candidate / "candidate.json")
    (candidate / "linked").symlink_to(candidate / "Model.lean")
    with pytest.raises(ValueError):
        p.inside(candidate, "linked")


def review_fixture(tmp_path, verdict="proved_if"):
    run = tmp_path / "run"
    attempt = run / "control/attempt-001"
    attempt.mkdir(parents=True)
    (run / "work").mkdir()
    (attempt / "Model.lean").write_text("mock original")
    p.write_json(attempt / "packet.json", {"verification": {"ok": verdict == "proved", "check_complete": True, "reviewable": True, "verdict": verdict}})
    binding = p.content_binding(attempt)
    state = {"status": "awaiting_review", "attempts": [{"path": "control/attempt-001", "binding": binding}]}
    p.write_json(run / "control/state.json", state)
    return run, attempt, binding


def test_accept_retains_conditional_verdict_and_invalidates_mutation(tmp_path):
    run, attempt, binding = review_fixture(tmp_path)
    runner = CliRunner()
    result = runner.invoke(p.main, ["review", str(run), "--decision", "accept", "--binding", binding, "--reason", "human reviewed premises"])
    assert result.exit_code == 0, result.output
    assert "proved_if" in result.output
    assert p.read_json(attempt / "decision.json")["verification_verdict"] == "proved_if"
    result = runner.invoke(p.main, ["status", str(run)])
    assert '"status": "accepted"' in result.output
    (attempt / "Model.lean").write_text("changed after approval")
    assert '"status": "invalidated"' in runner.invoke(p.main, ["status", str(run)]).output


def test_changed_packet_cannot_be_approved(tmp_path):
    run, attempt, binding = review_fixture(tmp_path)
    (attempt / "Model.lean").write_text("changed before approval")
    result = CliRunner().invoke(p.main, ["review", str(run), "--decision", "accept", "--binding", binding, "--reason", "review"])
    assert result.exit_code != 0
    assert not (attempt / "decision.json").exists()


def test_reject_preserves_feedback(tmp_path):
    run, attempt, binding = review_fixture(tmp_path)
    result = CliRunner().invoke(p.main, ["review", str(run), "--decision", "reject", "--binding", binding, "--reason", "model not justified"])
    assert result.exit_code == 0
    assert p.load_state(run)["status"] == "rejected"
    assert p.read_json(run / "work/human-feedback.json")["reason"] == "model not justified"


def test_response_is_durable_and_does_not_run_model(tmp_path):
    run = tmp_path / "run"
    (run / "control").mkdir(parents=True)
    (run / "work/requests").mkdir(parents=True)
    ident = "a" * 32
    p.write_json(run / "work/requests" / (ident + ".json"), {"id": ident, "question": "sampling method?"})
    p.write_json(run / "control/state.json", {"status": "awaiting_input", "responses": []})
    response = tmp_path / "response.txt"
    response.write_text("operator response")
    result = CliRunner().invoke(p.main, ["respond", str(run), "--request-id", ident, "--response-file", str(response), "--source", "human clarification"])
    assert result.exit_code == 0, result.output
    assert p.load_state(run)["status"] == "input_received"
    assert p.read_json(run / "control/responses" / (ident + ".json"))["response"] == "operator response"


@pytest.fixture(scope="module")
def runtime():
    """Explicit opt-in real local Docker controls; never executes Codex inference."""
    root = os.environ.get("VCS_TEST_LIBRARY_ROOT")
    if not root:
        pytest.skip("set VCS_TEST_LIBRARY_ROOT to run real Docker/Lean controls")
    return p.runtime_config(Path(root), None, None)


def test_real_docker_isolation(runtime, tmp_path):
    outside = tmp_path / "outside-marker"
    outside.write_text("HOST PRIVATE MARKER")
    work = tmp_path / "work"
    work.mkdir()
    (work / "allowed.txt").write_text("ALLOWED")
    code = ("from pathlib import Path; "
            "assert Path('/work/allowed.txt').read_text() == 'ALLOWED'; "
            f"assert not Path({str(outside)!r}).exists(); "
            "assert not Path('/home/claude/.codex/config.toml').exists(); "
            "assert not Path('/home/claude/lair/vas/AGENTS.override.md').exists(); "
            "assert not Path('/harness/tasks').exists(); "
            "assert not Path('/work/control').exists(); "
            "assert Path('/home/scientist/.codex/auth.json').is_file(); "
            "assert Path('/home/scientist/.codex/auth.json').is_symlink(); "
            "Path('/home/scientist/.codex/session-probe').write_text('writable'); "
            "assert not Path('/var/run/docker.sock').exists(); print('isolation passed')")
    cmd = p.docker_base(runtime, work, scientist=True) + [p.IMAGE, "python", "-c", code]
    result = p.run_container(cmd, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    # Version only: native client starts in the real container, no model invocation.
    result = p.run_container(p.docker_base(runtime, work, scientist=True) + [p.IMAGE, "codex", "--version"], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0 and p.CODEX_VERSION in result.stdout


@pytest.mark.parametrize("kind,expected", [("valid", "proved"), ("invalid", "not_proved"), ("axiom", "proved_if"), ("sorry", "proved_if")])
def test_real_lean_controls(runtime, candidate, kind, expected):
    source = candidate / "Model.lean"
    s = source.read_text()
    if kind == "invalid":
        s = s.replace("given_count = 50 := rfl", "given_count = 49 := rfl")
    elif kind == "axiom":
        s = s.replace("theorem prediction_result : 2 = 2 := rfl", "axiom added_premise : 2 = 3\ntheorem prediction_result : 2 = 3 := added_premise")
    elif kind == "sorry":
        s = s.replace("theorem prediction_result : 2 = 2 := rfl", "theorem prediction_result : 2 = 3 := by sorry")
    source.write_text(s)
    cmd = p.docker_base(runtime, candidate) + [p.IMAGE, "python", "/harness/src/vcs_protocol.py", "tool", "check", "--manifest", "/work/candidate.json", "--out", "/work/verification"]
    result = p.run_container(cmd, capture_output=True, text=True, timeout=3000)
    verdict = p.read_json(candidate / "verification/verdict.json")
    assert verdict["verdict"] == expected, result.stdout + result.stderr
    assert result.returncode == {"proved": 0, "proved_if": 3, "not_proved": 1}[expected]
    assert verdict["ok"] == (expected == "proved")
    if expected in {"proved", "proved_if"}:
        assert verdict["extraction"]["compiles_alone"]
        assert all(verdict["extraction"]["faithful"].values())
        assert "given_count" in verdict["extraction"]["assumption_declarations"]
    if expected == "proved_if":
        assert verdict["added_assumptions"]


def test_checker_timeout_is_no_verdict(candidate, monkeypatch):
    import vas_extract
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("lean", 900)
    monkeypatch.setattr(vas_extract, "run_lean", timeout)
    result = p.verify_candidate(candidate, candidate / "candidate.json", candidate / "timeout")
    assert not result["ok"] and result["verdict"] == "no_verdict"


def test_missing_audit_never_becomes_success(candidate, monkeypatch):
    import vas_extract
    monkeypatch.setattr(vas_extract, "run_lean", lambda *args: (0, ""))
    result = p.verify_candidate(candidate, candidate / "candidate.json", candidate / "missing")
    assert not result["ok"] and result["verdict"] == "not_proved"


def test_review_receipt_mutation_invalidates_acceptance(tmp_path):
    run, attempt, binding = review_fixture(tmp_path)
    runner = CliRunner()
    assert runner.invoke(p.main, ["review", str(run), "--decision", "accept", "--binding", binding, "--reason", "reviewed"]).exit_code == 0
    receipt = p.read_json(attempt / "decision.json")
    receipt["reason"] = "tampered"
    p.write_json(attempt / "decision.json", receipt)
    assert '"status": "invalidated"' in runner.invoke(p.main, ["status", str(run)]).output


def test_no_unchanged_resubmission_after_rejection(candidate):
    run = candidate / "run"
    work = run / "work"
    previous = run / "control/attempt-001"
    previous.mkdir(parents=True)
    work.mkdir()
    for name in ["Model.lean", "report.txt", "candidate.json"]:
        import shutil
        shutil.copyfile(candidate / name, previous / name)
        shutil.copyfile(candidate / name, work / name)
    state = {"attempts": [{"path": "control/attempt-001", "status": "rejected"}], "responses": []}
    with pytest.raises(ValueError, match="not revised"):
        p.freeze_and_check(run, state)


def test_untrusted_manifest_and_request_symlinks_are_rejected(candidate):
    manifest = candidate / "candidate.json"
    manifest.rename(candidate / "real.json")
    manifest.symlink_to(candidate / "real.json")
    with pytest.raises(ValueError, match="symlink"):
        p.load_candidate(candidate, manifest)


def test_container_cleanup_on_timeout(monkeypatch):
    calls = []
    def fake_run(command, **kwargs):
        calls.append(command)
        if command[1] == "run":
            raise subprocess.TimeoutExpired(command, 1)
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(p.subprocess, "run", fake_run)
    with pytest.raises(subprocess.TimeoutExpired):
        p.run_container(["docker", "run", "--rm", "image", "true"], timeout=1)
    assert calls[-1][:3] == ["docker", "rm", "-f"]


def test_real_host_freezes_and_checks_before_human_review(runtime, candidate):
    """A mock submission goes through the real host finalizer; no model runs."""
    import shutil
    run = candidate / "run"
    (run / "work").mkdir(parents=True)
    (run / "control").mkdir()
    for name in ["Model.lean", "candidate.json", "report.txt"]:
        shutil.copyfile(candidate / name, run / "work" / name)
    state = {"runtime": runtime, "attempts": [], "responses": [], "protocol_sha256": "control", "task_sha256": "control"}
    entry = p.freeze_and_check(run, state)
    assert state["status"] == "awaiting_review"
    packet = p.read_json(run / entry["path"] / "packet.json")
    assert packet["verification"]["verdict"] == "proved"
    assert packet["provenance"]["image"] == p.IMAGE
    p.write_json(run / "control/state.json", state)
    (run / "work/Model.lean").write_text("the agent changed its mutable draft")
    assert p.content_binding(run / entry["path"]) == entry["binding"]
    result = CliRunner().invoke(p.main, ["review", str(run), "--decision", "reject", "--binding", entry["binding"], "--reason", "arithmetic control has no scientific substance"])
    assert result.exit_code == 0, result.output
    assert p.load_state(run)["status"] == "rejected"
