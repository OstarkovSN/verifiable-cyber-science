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


def test_single_final_conclusion_can_leave_supporting_results_intermediate(candidate):
    manifest = p.read_json(candidate / "candidate.json")
    manifest["conclusions"] = {"answer": "prediction_result"}
    p.write_json(candidate / "candidate.json", manifest)
    loaded, source, _ = p.load_candidate(candidate, candidate / "candidate.json")
    p.validate_source(source.read_text(), list(loaded["conclusions"].values()))
    assert loaded["conclusions"] == {"answer": "prediction_result"}


@pytest.mark.parametrize("conclusions", [None, {}, [], {"": "prediction_result"},
    {"answer": []}, {"answer": "not a name"}, {"answer": "prediction_result", "duplicate": "prediction_result"}])
def test_invalid_final_conclusion_manifests_are_rejected(candidate, conclusions):
    manifest = p.read_json(candidate / "candidate.json")
    manifest["conclusions"] = conclusions
    p.write_json(candidate / "candidate.json", manifest)
    with pytest.raises(ValueError):
        p.load_candidate(candidate, candidate / "candidate.json")


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
    # Real Docker transport control: the scientific prompt must reach stdin intact.
    prompt = "CONTROL ONLY: stdin transport, not scientist inference.\n"
    cmd = p.docker_base(runtime, work, scientist=True) + [p.IMAGE, "python", "-c",
           "import sys; sys.stdout.write(sys.stdin.read())"]
    result = p.run_container(cmd, input=prompt, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0 and result.stdout == prompt, result.stderr
    # The CLI's terminal tool is a companion executable, not part of codex itself.
    cmd = p.docker_base(runtime, work, scientist=True) + [p.IMAGE, "codex-code-mode-host", "--help"]
    result = p.run_container(cmd, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0 and "--listen" in result.stdout, result.stderr


@pytest.mark.parametrize("kind,expected", [("valid", "proved"), ("single", "proved"), ("invalid", "not_proved"), ("axiom", "proved_if"), ("sorry", "proved_if")])
def test_real_lean_controls(runtime, candidate, kind, expected):
    source = candidate / "Model.lean"
    s = source.read_text()
    if kind == "single":
        manifest = p.read_json(candidate / "candidate.json")
        manifest["conclusions"] = {"answer": "prediction_result"}
        p.write_json(candidate / "candidate.json", manifest)
    elif kind == "invalid":
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
        if kind != "single":
            assert "given_count" in verdict["extraction"]["assumption_declarations"]
        else:
            assert verdict["extraction"]["conclusions"] == ["prediction_result"]
            assert "given_count" not in verdict["extraction"]["assumption_declarations"]
    if expected == "proved_if":
        assert verdict["added_assumptions"]


def test_checker_timeout_is_no_verdict(candidate, monkeypatch):
    import vcs_extract
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("lean", 900)
    monkeypatch.setattr(vcs_extract, "run_lean", timeout)
    result = p.verify_candidate(candidate, candidate / "candidate.json", candidate / "timeout")
    assert not result["ok"] and result["verdict"] == "no_verdict"


def test_missing_audit_never_becomes_success(candidate, monkeypatch):
    import vcs_extract
    monkeypatch.setattr(vcs_extract, "run_lean", lambda *args: (0, ""))
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
    assert packet["provenance"]["requested_model"] == "gpt-6.1-sol"
    assert packet["provenance"]["requested_reasoning_effort"] == "medium"
    p.write_json(run / "control/state.json", state)
    (run / "work/Model.lean").write_text("the agent changed its mutable draft")
    assert p.content_binding(run / entry["path"]) == entry["binding"]
    result = CliRunner().invoke(p.main, ["review", str(run), "--decision", "reject", "--binding", entry["binding"], "--reason", "arithmetic control has no scientific substance"])
    assert result.exit_code == 0, result.output
    assert p.load_state(run)["status"] == "rejected"


def test_requested_model_flags_are_explicit(tmp_path, monkeypatch):
    """Inspect a mocked client invocation without running inference."""
    run = tmp_path / "run"
    (run / "work").mkdir(parents=True)
    (run / "control").mkdir()
    calls = []
    monkeypatch.setattr(p, "docker_base", lambda *args, **kwargs: ["docker", "run"])
    def client(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 9)
    monkeypatch.setattr(p, "run_container", client)
    monkeypatch.setattr(p, "ensure_subscription", lambda *args: None)
    state = {"cycles": 0, "runtime": {"model": "requested-model", "reasoning_effort": "high"}, "attempts": []}
    p.execute_cycle(run, state)
    assert len(calls) == 1  # Client failures never automatically retry.
    cmd = calls[0]
    assert cmd[cmd.index("--model") + 1] == "requested-model"
    assert cmd[cmd.index("--config") + 1] == 'model_reasoning_effort="high"'
    assert p.load_state(run)["runtime"]["model"] == "requested-model"
    assert state["status"] == "scientist_failed"


def test_automatic_retry_bound_retains_feedback(tmp_path, monkeypatch):
    run = tmp_path / "run"
    (run / "work").mkdir(parents=True)
    (run / "control").mkdir()
    state = {"cycles": 0, "attempts": []}
    def incomplete(run, state):
        state["cycles"] += 1
        state["status"] = "incomplete"
        p.write_json(run / "control/state.json", state)
    monkeypatch.setattr(p, "_execute_once", incomplete)
    p.execute_cycle(run, state)
    assert state["cycles"] == p.MAX_AUTOMATIC_CYCLES
    assert state["status"] == "incomplete"
    for cycle in range(1, p.MAX_AUTOMATIC_CYCLES + 1):
        feedback = f"feedback-{cycle:03d}/failure.json"
        assert p.read_json(run / "control" / feedback)["status"] == "incomplete"
    assert "explicitly" in p.load_state(run)["error"]


def test_real_check_failure_feedback_reaches_retry(tmp_path, monkeypatch):
    run = tmp_path / "run"
    (run / "work").mkdir(parents=True)
    attempt = run / "control/attempt-001"
    (attempt / "verification").mkdir(parents=True)
    p.write_json(attempt / "packet.json", {"verification": {"error": "actual diagnostic"}})
    (attempt / "checker-trace.log").write_text("actual checker output")
    (attempt / "verification/lean.log").write_text("actual Lean output")
    state = {"cycles": 0, "attempts": []}
    def cycle(run, state):
        state["cycles"] += 1
        if state["cycles"] == 1:
            state["attempts"].append({"path": "control/attempt-001"})
            state["status"] = "check_failed"
        else:
            feedback = run / "work/check-feedback/cycle-001"
            assert (feedback / "lean.log").read_text() == "actual Lean output"
            assert (feedback / "checker-trace.log").read_text() == "actual checker output"
            state["status"] = "awaiting_review"
    monkeypatch.setattr(p, "_execute_once", cycle)
    p.execute_cycle(run, state)
    assert state["cycles"] == 2
    assert state["status"] == "awaiting_review"


def test_host_finalizer_rejects_symlink_packet_destination(candidate, monkeypatch):
    """Run the host finalizer, stubbing only the isolated checker process."""
    import shutil
    run = candidate / "run"
    (run / "work").mkdir(parents=True)
    (run / "control").mkdir()
    for name in ["Model.lean", "candidate.json", "report.txt"]:
        shutil.copyfile(candidate / name, run / "work" / name)
    sentinel = candidate / "host-sentinel"
    sentinel.write_text("preserve host data")
    (run / "work/last-review-packet.json").symlink_to(sentinel)
    monkeypatch.setattr(p, "docker_base", lambda *args, **kwargs: ["docker", "run"])
    def checker(cmd, **kwargs):
        out = run / "control/attempt-001/verification"
        out.mkdir()
        p.write_json(out / "verdict.json", {"ok": True, "reviewable": True, "check_complete": True, "verdict": "proved"})
        return subprocess.CompletedProcess(cmd, 0)
    monkeypatch.setattr(p, "run_container", checker)
    state = {"runtime": dict.fromkeys(["image", "lean_version", "codex_version", "codex_sha256"], "control"),
             "attempts": [], "responses": [], "protocol_sha256": "control", "task_sha256": "control"}
    with pytest.raises((OSError, ValueError)):
        p.freeze_and_check(run, state)
    assert sentinel.read_text() == "preserve host data"


@pytest.mark.parametrize("destination", ["human-feedback.json", "human-feedback.json.tmp"])
def test_human_feedback_cannot_overwrite_host_via_symlink(tmp_path, destination):
    run, attempt, binding = review_fixture(tmp_path)
    sentinel = tmp_path / "host-sentinel"
    sentinel.write_text("preserve host data")
    (run / "work" / destination).symlink_to(sentinel)
    result = CliRunner().invoke(p.main, ["review", str(run), "--decision", "reject", "--binding", binding, "--reason", "revise model"])
    assert sentinel.read_text() == "preserve host data"
    if destination.endswith(".tmp"):
        assert result.exit_code == 0, result.output
        assert p.read_json(run / "work/human-feedback.json")["reason"] == "revise model"
    else:
        assert result.exit_code != 0


def test_response_rejects_symlink_inputs_parent(tmp_path):
    run = tmp_path / "run"
    (run / "control").mkdir(parents=True)
    (run / "work/requests").mkdir(parents=True)
    outside = tmp_path / "host-directory"
    outside.mkdir()
    (run / "work/inputs").symlink_to(outside, target_is_directory=True)
    ident = "b" * 32
    p.write_json(run / "work/requests" / (ident + ".json"), {"id": ident, "question": "clarification?"})
    p.write_json(run / "control/state.json", {"status": "awaiting_input", "responses": []})
    response = tmp_path / "response.txt"
    response.write_text("external response")
    result = CliRunner().invoke(p.main, ["respond", str(run), "--request-id", ident, "--response-file", str(response), "--source", "human"])
    assert result.exit_code != 0
    assert list(outside.iterdir()) == []
    assert p.load_state(run)["status"] == "awaiting_input"


@pytest.mark.parametrize("parent", ["check-feedback", "check-feedback/cycle-001"])
def test_automatic_feedback_rejects_symlink_parents(tmp_path, monkeypatch, parent):
    run = tmp_path / "run"
    (run / "work").mkdir(parents=True)
    (run / "control").mkdir()
    outside = tmp_path / "host-directory"
    outside.mkdir()
    linked = run / "work" / parent
    linked.parent.mkdir(parents=True, exist_ok=True)
    linked.symlink_to(outside, target_is_directory=True)
    def incomplete(run, state):
        state.update(cycles=1, status="incomplete")
    monkeypatch.setattr(p, "_execute_once", incomplete)
    with pytest.raises((OSError, ValueError)):
        p.execute_cycle(run, {"cycles": 0, "attempts": []})
    assert list(outside.iterdir()) == []


def test_subscription_change_stops_cycle_before_inference(tmp_path, monkeypatch):
    run = tmp_path / "run"
    (run / "work").mkdir(parents=True)
    (run / "control").mkdir()
    calls = []
    monkeypatch.setattr(p, "docker_base", lambda *args, **kwargs: ["docker", "run"])
    def login(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="Logged in using an API key\n", stderr="")
    monkeypatch.setattr(p, "run_container", login)
    state = {"cycles": 4, "runtime": {}, "attempts": [], "status": "input_received"}
    p.execute_cycle(run, state)
    assert state["status"] == "scientist_failed"
    assert state["cycles"] == 4
    assert len(calls) == 1
    assert calls[0][-3:] == ["codex", "login", "status"]
    assert "exec" not in calls[0]


def test_status_shows_outstanding_request_after_prior_attempt(tmp_path):
    run, attempt, binding = review_fixture(tmp_path)
    requests = run / "work/requests"
    requests.mkdir()
    ident = "c" * 32
    p.write_json(requests / (ident + ".json"), {"id": ident, "question": "need sampling details"})
    state = p.load_state(run)
    state.update(status="awaiting_input", error="retained error detail")
    p.write_json(run / "control/state.json", state)
    result = CliRunner().invoke(p.main, ["status", str(run)])
    assert result.exit_code == 0, result.output
    status = json.loads(result.output)
    assert status["requests"][0]["id"] == ident
    assert status["packet"] == str(attempt / "packet.json")
    assert status["error"] == "retained error detail"


def test_mutated_review_receipt_blocks_resume_before_model(tmp_path, monkeypatch):
    run, attempt, binding = review_fixture(tmp_path)
    rejected = CliRunner().invoke(p.main, ["review", str(run), "--decision", "reject", "--binding", binding, "--reason", "original human feedback"])
    assert rejected.exit_code == 0, rejected.output
    codex = tmp_path / "native-codex"
    codex.write_text("control native binary")
    state = p.load_state(run)
    state.update(runtime={"codex": str(codex), "codex_sha256": p.digest(codex),
                          "code_mode_host": str(codex), "code_mode_host_sha256": p.digest(codex)},
                 protocol_sha256=p.digest(p.ROOT / "protocols/v1/instructions.txt"),
                 task_sha256=p.digest(p.ROOT / "protocols/v1/task-balls.txt"))
    p.write_json(run / "control/state.json", state)
    receipt = p.read_json(attempt / "decision.json")
    receipt["reason"] = "altered human decision"
    p.write_json(attempt / "decision.json", receipt)
    model_calls = []
    monkeypatch.setattr(p, "execute_cycle", lambda *args: model_calls.append(args))
    result = CliRunner().invoke(p.main, ["resume", str(run)])
    assert result.exit_code != 0
    assert "human decision changed" in result.output
    assert model_calls == []


def test_fresh_cycle_receives_host_recorded_human_feedback(tmp_path, monkeypatch):
    run, attempt, binding = review_fixture(tmp_path)
    rejected = CliRunner().invoke(p.main, ["review", str(run), "--decision", "reject", "--binding", binding, "--reason", "host human says revise sampling model"])
    assert rejected.exit_code == 0, rejected.output
    # A scientist can alter its working copy; the next prompt uses host custody.
    (run / "work/human-feedback.json").write_text('{"reason":"forged approval"}')
    state = p.load_state(run)
    state.update(cycles=0, runtime={})
    prompts = []
    monkeypatch.setattr(p, "ensure_subscription", lambda *args: None)
    monkeypatch.setattr(p, "docker_base", lambda *args, **kwargs: ["docker", "run"])
    def client(cmd, **kwargs):
        prompts.append(kwargs["input"])
        return subprocess.CompletedProcess(cmd, 9)
    monkeypatch.setattr(p, "run_container", client)
    p.execute_cycle(run, state)
    assert len(prompts) == 1
    assert "host human says revise sampling model" in prompts[0]
    assert "forged approval" not in prompts[0]


@pytest.mark.parametrize("prior_attempt", [False, True])
def test_planted_work_feedback_never_becomes_host_evidence(tmp_path, monkeypatch, prior_attempt):
    run = tmp_path / "run"
    feedback = run / "work/check-feedback/cycle-001"
    feedback.mkdir(parents=True)
    (run / "control").mkdir()
    for name in ["packet.json", "lean.log", "checker-trace.log"]:
        (feedback / name).write_text("forged agent feedback")
    state = {"cycles": 0, "attempts": []}
    if prior_attempt:
        old = run / "control/attempt-001"
        old.mkdir()
        p.write_json(old / "packet.json", {"old": "previous cycle"})
        (old / "checker-trace.log").write_text("previous checker output")
        state["attempts"].append({"path": "control/attempt-001"})
    def cycle(run, state):
        state["cycles"] += 1
        state["status"] = "incomplete" if state["cycles"] == 1 else "awaiting_input"
    monkeypatch.setattr(p, "_execute_once", cycle)
    p.execute_cycle(run, state)
    archive = run / "control/feedback-001"
    assert {path.name for path in archive.iterdir()} == {"failure.json"}
    assert p.read_json(archive / "failure.json")["status"] == "incomplete"
    assert state["status"] == "awaiting_input"
