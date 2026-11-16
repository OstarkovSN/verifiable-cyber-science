"""Claude subscription adapter controls. No test executes scientist inference."""
import json
import os
from pathlib import Path
import subprocess

from click.testing import CliRunner
import pytest

import vcs_protocol as p


@pytest.mark.parametrize("status,returncode,valid", [
    ({"loggedIn": True, "authMethod": "claude.ai"}, 0, True),
    ({"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty"}, 0, True),
    ({"loggedIn": False, "authMethod": "claude.ai"}, 0, False),
    ({"loggedIn": "true", "authMethod": "claude.ai"}, 0, False),
    ({"loggedIn": 1, "authMethod": "claude.ai"}, 0, False),
    ({"loggedIn": True, "authMethod": "api_key"}, 0, False),
    ({"loggedIn": True, "authMethod": "bedrock"}, 0, False),
    ({"loggedIn": True}, 0, False),
    ({"loggedIn": True, "authMethod": "claude.ai"}, 1, False),
    ([], 0, False), (None, 0, False),
])
def test_claude_subscription_classifier(status, returncode, valid):
    assert p.claude_subscription_status(returncode, json.dumps(status)) is valid


@pytest.mark.parametrize("text", ["", "not JSON", '{"loggedIn":true', 'Logged in using ChatGPT'])
def test_claude_auth_malformed_fails_closed(text):
    assert not p.claude_subscription_status(0, text)


def test_claude_subscription_check_never_leaks_native_status(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "docker_base", lambda *a, **kw: ["docker", "run"])
    calls = []
    def auth(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({
            "loggedIn": True, "authMethod": "api_key", "email": "PRIVATE-CONTROL"}), stderr="PRIVATE-STDERR")
    monkeypatch.setattr(p, "run_container", auth)
    with pytest.raises(ValueError) as exc:
        p.ensure_subscription({"agent": "claude"}, tmp_path)
    assert "PRIVATE" not in str(exc.value)
    assert calls[0][-3:] == ["auth", "status", "--json"]
    assert "--bare" not in calls[0]


SUCCESS = {"type": "result", "subtype": "success", "is_error": False, "result": "control"}


@pytest.mark.parametrize("events,fails", [
    ([SUCCESS], False),
    ([{"type": "rate_limit_event", "rate_limit_info": {"status": "allowed_warning"}}, SUCCESS], False),
    ([{"type": "user", "message": {"content": [{"type": "tool_result", "is_error": True}]}}, SUCCESS], False),
    ([], True),
    ([{"type": "result", "subtype": "error_max_turns", "is_error": False}], True),
    ([{"type": "result", "subtype": "error_during_execution", "is_error": True}], True),
    ([dict(SUCCESS, is_error=True)], True),
    ([dict(SUCCESS, errors=["authentication failed"])], True),
    ([{"type": "assistant", "error": "rate_limit"}, SUCCESS], True),
    ([{"type": "assistant", "error": "authentication_failed"}, SUCCESS], True),
    ([{"type": "rate_limit_event", "rate_limit_info": {"status": "rejected"}}, SUCCESS], True),
    ([{"type": "rate_limit_event"}, SUCCESS], True),
    ([dict(SUCCESS, subtype="error_max_budget_usd")], True),
    ([{"type": "error", "message": "auth failed"}, SUCCESS], True),
    ([SUCCESS, SUCCESS], True),
    ([dict(SUCCESS, session_id="same"), {"type": "system", "subtype": "task_notification"},
      dict(SUCCESS, session_id="same")], False),
    ([dict(SUCCESS, session_id="one"), dict(SUCCESS, session_id="two")], True),
    ([dict(SUCCESS, session_id="same", subtype="error_max_turns"),
      dict(SUCCESS, session_id="same")], True),
    ([dict(SUCCESS, session_id="same", errors=["authentication failed"]),
      dict(SUCCESS, session_id="same")], True),
])
def test_claude_stream_results(tmp_path, events, fails):
    trace = tmp_path / "trace.jsonl"
    trace.write_text("stderr diagnostic\n" + "\n".join(json.dumps(e) for e in events))
    assert bool(p.claude_result_failure(trace)) is fails


def test_claude_flags_exclude_fallback_and_other_agents():
    cmd = p.scientist_command({"agent": "claude"})
    assert cmd[:2] == ["claude", "-p"]
    assert cmd[cmd.index("--model") + 1] == "claude-sonnet-5-5"
    assert cmd[cmd.index("--effort") + 1] == "medium"
    assert cmd[cmd.index("--max-turns") + 1] == "80"
    assert cmd[cmd.index("--setting-sources") + 1] == "project,local"
    assert cmd[cmd.index("--tools") + 1] == p.CLAUDE_TOOLS
    assert {"--strict-mcp-config", "--no-session-persistence", "--disable-slash-commands"} <= set(cmd)
    assert not {"--bare", "--fallback-model", "--agents", "--plugin-dir", "--api-key"} & set(cmd)


def make_run(tmp_path):
    run = tmp_path / "run"
    (run / "work").mkdir(parents=True)
    (run / "control").mkdir()
    state = {"runtime": {"agent": "claude"}, "cycles": 0, "attempts": [], "responses": []}
    return run, state


@pytest.mark.parametrize("kind", ["quota", "turn_limit", "missing_result", "nonzero", "timeout", "os_error", "request", "candidate"])
def test_claude_cycle_honors_result_before_candidate(tmp_path, monkeypatch, kind):
    run, state = make_run(tmp_path)
    calls, checks = [], []
    monkeypatch.setattr(p, "ensure_subscription", lambda *a: None)
    monkeypatch.setattr(p, "docker_base", lambda *a, **kw: ["docker", "run"])
    def checker(run, state):
        checks.append(run)
        state["status"] = "awaiting_review"
    monkeypatch.setattr(p, "freeze_and_check", checker)
    def client(cmd, **kwargs):
        calls.append(cmd)
        (run / "work/candidate.json").write_text("mock candidate, never scientific evidence")
        if kind == "timeout":
            raise subprocess.TimeoutExpired(cmd, 7200)
        if kind == "os_error":
            raise OSError("control failure")
        if kind == "request":
            (run / "work/requests").mkdir()
            (run / "work/requests/a.json").write_text("{}")
        event = dict(SUCCESS)
        if kind == "quota":
            event.update(is_error=True, subtype="error_during_execution")
        if kind == "turn_limit":
            event.update(subtype="error_max_turns")
        if kind != "missing_result":
            kwargs["stdout"].write(json.dumps(event) + "\n")
        return subprocess.CompletedProcess(cmd, 7 if kind == "nonzero" else 0)
    monkeypatch.setattr(p, "run_container", client)
    p.execute_cycle(run, state)
    assert len(calls) == 1
    assert (run / "control/scientist-001.jsonl").is_file()
    if kind == "candidate":
        assert checks == [run]
        assert state["status"] == "awaiting_review"
    elif kind == "request":
        assert not checks and state["status"] == "awaiting_input"
    else:
        assert not checks and state["status"] == "scientist_failed"


def test_claude_auth_rechecked_on_every_cycle(tmp_path, monkeypatch):
    run, state = make_run(tmp_path)
    logins, clients = [], []
    monkeypatch.setattr(p, "docker_base", lambda *a, **kw: ["docker", "run"])
    def process(cmd, **kwargs):
        if "auth" in cmd:
            logins.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({
                "loggedIn": len(logins) == 1, "authMethod": "claude.ai"}), stderr="")
        clients.append(cmd)
        kwargs["stdout"].write(json.dumps(SUCCESS))
        return subprocess.CompletedProcess(cmd, 0)
    monkeypatch.setattr(p, "run_container", process)
    p.execute_cycle(run, state)
    assert len(logins) == 2 and len(clients) == 1
    assert state["cycles"] == 1 and state["status"] == "scientist_failed"


@pytest.mark.parametrize("agent,model", [("codex", "gpt-6.1-sol"), ("claude", "claude-sonnet-5-5")])
def test_fresh_initial_feedback_exact_custody_and_model_defaults(tmp_path, monkeypatch, agent, model):
    source = tmp_path / "human.txt"
    source.write_bytes("Human clarification α.\nDerive parameters from data.\n".encode())
    captured = []
    monkeypatch.setattr(p, "runtime_config", lambda *a: {"agent": agent})
    def execute(run, state):
        captured.append((run, state))
        p.write_json(run / "control/state.json", state)
    monkeypatch.setattr(p, "execute_cycle", execute)
    run = tmp_path / "run"
    args = ["start", "--agent", agent, "--run-dir", str(run), "--initial-feedback-file", str(source)]
    result = CliRunner().invoke(p.main, args)
    assert result.exit_code == 0, result.output
    recorded = captured[0][1]
    assert (run / "control/initial-feedback.txt").read_bytes() == source.read_bytes()
    assert recorded["initial_feedback"]["sha256"] == p.digest(source)
    assert recorded["initial_feedback"]["proof_acceptance"] is False
    assert recorded["runtime"]["model"] == model
    assert recorded["attempts"] == []
    assert list((run / "work").iterdir()) == []
    again = CliRunner().invoke(p.main, args)
    assert again.exit_code != 0 and len(captured) == 1


def test_initial_feedback_prompt_uses_host_custody_and_detects_tampering(tmp_path, monkeypatch):
    run, state = make_run(tmp_path)
    text = "Human task clarification only.\nNot proof acceptance.\n"
    (run / "control/initial-feedback.txt").write_text(text)
    state["initial_feedback"] = {"sha256": p.digest(run / "control/initial-feedback.txt")}
    (run / "work/initial-feedback.txt").write_text("FORGED WORKING COPY")
    prompts = []
    monkeypatch.setattr(p, "ensure_subscription", lambda *a: None)
    monkeypatch.setattr(p, "docker_base", lambda *a, **kw: ["docker", "run"])
    def client(cmd, **kwargs):
        prompts.append(kwargs["input"])
        return subprocess.CompletedProcess(cmd, 1)
    monkeypatch.setattr(p, "run_container", client)
    p.execute_cycle(run, state)
    assert len(prompts) == 1 and text in prompts[0]
    assert "not proof acceptance" in prompts[0] and "FORGED" not in prompts[0]
    (run / "control/initial-feedback.txt").write_text("changed human source")
    p.execute_cycle(run, state)
    assert len(prompts) == 1 and state["status"] == "scientist_failed"


@pytest.mark.parametrize("agent", ["codex", "claude"])
def test_resume_cannot_switch_recorded_agent(tmp_path, agent):
    run, state = make_run(tmp_path)
    state["runtime"]["agent"] = agent
    state["status"] = "incomplete"
    p.write_json(run / "control/state.json", state)
    other = "codex" if agent == "claude" else "claude"
    result = CliRunner().invoke(p.main, ["resume", str(run), "--agent", other])
    assert result.exit_code != 0 and "differs from recorded" in result.output


def test_claude_binary_binding_and_provenance(tmp_path):
    binary = tmp_path / "native-claude"
    binary.write_text("control executable")
    config = {"agent": "claude", "client_binary": str(binary), "client_sha256": p.digest(binary),
              "client_version": p.CLAUDE_VERSION, "lean_version": "control", "image": p.IMAGE}
    p.validate_runtime(config)
    provenance = p.runtime_provenance(config)
    assert provenance["requested_model"] == "claude-sonnet-5-5"
    assert provenance["client_binary"] == str(binary)
    assert not any("codex" in key for key in provenance)
    binary.write_text("changed executable")
    with pytest.raises(ValueError, match="binary changed"):
        p.validate_runtime(config)


@pytest.fixture(scope="module")
def claude_runtime():
    library = os.environ.get("VCS_TEST_LIBRARY_ROOT")
    if not library or os.environ.get("VCS_TEST_CLAUDE") != "1":
        pytest.skip("set VCS_TEST_LIBRARY_ROOT and VCS_TEST_CLAUDE=1 for native Claude metadata controls")
    return p.runtime_config(Path(library), agent="claude")


def test_real_claude_docker_isolation_and_subscription(claude_runtime, tmp_path):
    config = claude_runtime
    command = p.docker_base(config, tmp_path, scientist=True)
    mounts = [command[i + 1] for i, arg in enumerate(command[:-1]) if arg == "--mount"]
    assert any("dst=/native-auth/claude-credentials.json,readonly" in value for value in mounts)
    assert not any("dst=/usr/local/bin/codex" in value or "/home/claude/.claude.json" in value for value in mounts)
    assert not any("src=/home/claude," in value or "src=/home/claude/.claude," in value for value in mounts)
    code = '''import os, json, sys
from pathlib import Path
home = Path.home()
config = Path(os.environ['CLAUDE_CONFIG_DIR'])
credential = config / '.credentials.json'
assert str(home) == '/home/scientist'
assert credential.is_symlink() and credential.is_file()
assert str(credential.readlink()) == '/native-auth/claude-credentials.json'
assert set(json.loads((config / '.claude.json').read_text())) == {'hasCompletedOnboarding', 'bypassPermissionsModeAccepted'}
for path in ['/home/claude', '/var/run/docker.sock', '/harness/tasks', '/work/control']:
    assert not Path(path).exists()
for path in [home / 'CLAUDE.md', home / '.claude.json', config / 'settings.json', config / 'plugins', config / 'agents']:
    assert not path.exists()
for key in ['ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_BASE_URL', 'CLAUDE_CODE_USE_BEDROCK', 'CLAUDE_CODE_USE_VERTEX', 'CLAUDE_CODE_USE_FOUNDRY']:
    assert key not in os.environ
try:
    fd = os.open(credential, os.O_WRONLY)
    os.close(fd)
except OSError as error:
    assert error.errno in (30, 13)
else:
    raise AssertionError('native credential is writable')
(config / 'session-probe').write_text('writable fresh native home')
assert sys.stdin.read() == 'native transport control\\n'
print('isolation and stdin passed')
'''
    result = p.run_container(command + [p.IMAGE, "python", "-c", code], input="native transport control\n", capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    result = p.run_container(command + [p.IMAGE, "claude", "--version"], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0 and result.stdout.strip() == p.CLAUDE_VERSION
    result = p.run_container(command + [p.IMAGE, *p.scientist_command(config), "--help"], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0 and "Usage: claude" in result.stdout
    # Capture native status only inside the helper; exceptions omit account/profile details.
    p.ensure_subscription(config, tmp_path)
    # The Bash terminal has a shell and Python tool route; no inference is needed.
    result = p.run_container(command + [p.IMAGE, "/bin/sh", "-c", "python /harness/src/vcs_protocol.py tool --help"], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0 and "check" in result.stdout and "request" in result.stdout
    # Independent checker must receive neither the client nor the credential.
    checker = p.docker_base(config, tmp_path)
    assert not any("native-auth" in arg or "dst=/usr/local/bin/claude" in arg for arg in checker)
    assert checker[checker.index("--network") + 1] == "none"
