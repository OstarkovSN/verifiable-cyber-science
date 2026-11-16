"""Versioned, human-gated workflow for agent-written scientific Lean models.

Host control files never enter the scientist container. Container check results are
feedback only: host review always checks its own frozen snapshot independently.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone

import click

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "sha256:c0e8df9380519cf514d5fbb5aeaa7aa5de5f32c50330badcadc05cdabaae5566"
CODEX_VERSION = "codex-cli 0.166.0"
CLAUDE_VERSION = "2.1.325 (Claude Code)"
DEFAULT_MODELS = {"codex": "gpt-6.1-sol", "claude": "claude-sonnet-5-5"}
CLAUDE_TOOLS = "Bash,Read,Write,Edit,Grep,Glob,WebFetch,WebSearch"
NAME = re.compile(r"[A-Za-z_][A-Za-z_0-9']*")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def directory_fd(path, create=False):
    """Walk from root without following links, even in an untrusted workspace."""
    path = Path(path).absolute()
    if ".." in path.parts:
        raise ValueError("directory traversal is unsupported")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def ensure_directory(path):
    os.close(directory_fd(path, create=True))


def atomic_write(path, data):
    """Replace the directory entry; never open an existing target or predictable temp."""
    path = Path(path)
    parent = directory_fd(path.parent)
    temp = ".vcs-write-" + uuid.uuid4().hex
    try:
        try:
            existing = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None and stat.S_ISLNK(existing.st_mode):
            raise ValueError("refusing symlink write destination")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(temp, path.name, src_dir_fd=parent, dst_dir_fd=parent)
    finally:
        try:
            os.unlink(temp, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)


def write_json(path, value):
    atomic_write(path, (json.dumps(value, indent=2) + "\n").encode())


def read_json(path):
    return json.loads(Path(path).read_text())


def stamp():
    return datetime.now(timezone.utc).isoformat()


def inside(base, relative):
    """Reject traversal and symlinks, including intermediate directory links."""
    p = Path(relative)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError("candidate paths must be relative without '..'")
    target = Path(base) / p
    for item in [target, *target.parents]:
        if item == Path(base).parent:
            break
        if item.is_symlink():
            raise ValueError("candidate paths may not contain symlinks")
    if not target.is_file():
        raise ValueError(f"missing candidate file: {relative}")
    return target


def load_candidate(work, manifest):
    manifest = inside(work, str(Path(manifest).relative_to(work)))
    m = read_json(manifest)
    conclusions = m.get("conclusions")
    if not isinstance(conclusions, dict) or not conclusions or not all(
            isinstance(label, str) and label.strip() for label in conclusions):
        raise ValueError("conclusions must be a nonempty mapping of labels to theorem names")
    names = list(conclusions.values())
    if not all(isinstance(n, str) and NAME.fullmatch(n) for n in names) or len(set(names)) != len(names):
        raise ValueError("distinct plain theorem names are required")
    for key in ["user_facts", "model_choices", "sources", "incorporated_inputs"]:
        if not isinstance(m.get(key), list) or not all(isinstance(s, str) for s in m[key]):
            raise ValueError(f"{key} must be a list of strings")
    if not m["user_facts"] or not m["model_choices"] or not isinstance(m.get("proof_scope"), str) or not m["proof_scope"].strip():
        raise ValueError("facts, choices and substantive proof_scope are required")
    return m, inside(work, m["proof_file"]), inside(work, m["narrative_file"])


def validate_source(source, names):
    """Fixed library trust base; reuse hardened no-metaprogramming body contract."""
    from vcs_lean import strip_comments, validate
    code = strip_comments(source)
    imports = re.findall(r"(?m)^import ([A-Za-z0-9_.]+)\s*$", code)
    if not imports or any(not n.startswith("Mathlib.") for n in imports):
        raise ValueError("explicit imports of pinned Mathlib modules only")
    body = re.sub(r"(?m)^import [A-Za-z0-9_.]+\s*$", "", code)
    validate(body, names)
    if re.search(r"\bconclusion_\w*", body):
        raise ValueError("conclusion_ names are reserved for independent extraction")
    # Extractor requires a colon immediately after the theorem name. Fail clearly.
    for n in names:
        if not re.search(r"(?m)^\s*(?:theorem|lemma)\s+" + re.escape(n) + r"\s*:", body):
            raise ValueError("conclusion binders must be inside the statement after ':'")


def verify_candidate(work, manifest, out):
    """Actually compile, audit axioms, recheck kernel and independently extract."""
    from vcs_lean import ALLOWED_AXIOMS, LISTER, listed
    from vcs_extract import run_lean, main as extract
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    result = {"ok": False, "check_complete": False, "reviewable": False, "verdict": "not_proved", "time": stamp()}
    try:
        m, proof, narrative = load_candidate(work, manifest)
        snapshot = out / "submitted.lean"
        snapshot.write_bytes(proof.read_bytes())
        (out / "submitted-report.txt").write_bytes(narrative.read_bytes())
        write_json(out / "submitted-candidate.json", m)
        proof = snapshot
        names = list(m["conclusions"].values())
        source = proof.read_text()
        validate_source(source, names)
        targets = "[" + ", ".join("``" + n for n in names) + "]"
        audited = out / "Checked.lean"
        audited.write_text(source + "\n" + "\n".join(f"#print axioms {n}" for n in names) + "\n" + LISTER.replace("ROOTS", targets))
        status, log = run_lean(audited)
        (out / "lean.log").write_text(log)
        result["lean_exit"] = status
        additions = listed(log)
        seen = set(re.findall(r"^'(.+)' (?:depends on axioms:|does not depend on any axioms)", log, re.M))
        axioms = {n: [a.strip() for a in xs.split(",") if a.strip()]
                  for n, xs in re.findall(r"^'(.+)' depends on axioms: \[([^\]]*)\]", log, re.M)}
        unexpected = {a for xs in axioms.values() for a in xs if a not in ALLOWED_AXIOMS}
        disclosed = {a["name"] for a in additions or [] if a["kind"] == "axiom" and a["used"]}
        gaps = [a for a in additions or [] if a["kind"] == "gap" and a["used"]]
        if status != 0 or additions is None or not set(names) <= seen:
            raise ValueError("Lean, kernel recheck or axiom audit failed; see lean.log")
        if any(a not in disclosed and not (a == "sorryAx" and gaps) for a in unexpected):
            raise ValueError("undisclosed axioms")
        if re.search(r"VAS_UNSTATED \S+ used=true", log) or any("⋯" in a["statement"] for a in additions if a["used"]):
            raise ValueError("incomplete assumption disclosure")
        # click's standalone_mode=False gives real exit errors without terminating host.
        try:
            extract.main(args=[str(proof), *sum((["--theorem", n] for n in names), []), "--out", str(out / "extracted")], standalone_mode=False)
        except SystemExit as exc:
            # Extractor explicitly sys.exit(0), even outside standalone mode.
            if exc.code != 0:
                raise ValueError("independent extraction failed") from exc
        extraction = read_json(out / "extracted.json")
        if not extraction.get("ok") or not extraction.get("compiles_alone") or not all(extraction.get("faithful", {}).values()):
            raise ValueError("independent extraction/statement comparison failed")
        # Any added premise or gap, even unused, remains explicitly conditional.
        result |= {"ok": not additions, "check_complete": True, "reviewable": True, "verdict": "proved_if" if additions else "proved",
                   "added_assumptions": additions, "conditional_on": sorted(unexpected),
                   "extraction": extraction, "scientific_relevance": "requires human review"}
    except (Exception, SystemExit) as exc:
        result |= {"ok": False, "error": str(exc) or type(exc).__name__}
        if isinstance(exc, (subprocess.TimeoutExpired, TimeoutError)):
            result["verdict"] = "no_verdict"
    write_json(out / "verdict.json", result)
    return result


def native_codex():
    executable = shutil.which("codex")
    if not executable:
        raise ValueError("Codex CLI is not installed")
    js = Path(executable).resolve()
    candidates = list(js.parent.parent.glob("node_modules/@openai/codex-linux-x64/vendor/*/bin/codex"))
    candidates += list(js.parent.parent.glob("vendor/*/bin/codex"))
    if not candidates:
        raise ValueError("native Codex binary not found; specify --codex-binary")
    return candidates[0]


def native_claude():
    executable = shutil.which("claude")
    if not executable:
        raise ValueError("native Claude CLI is not installed; specify --claude-binary")
    return Path(executable).resolve()


def client_name(config):
    # States from the original release have no agent field.
    return config.get("agent", "codex")


def runtime_config(library_root, codex_binary=None, auth_file=None, agent="codex", claude_binary=None):
    toolchain_name = (ROOT / "lean-toolchain").read_text().strip().replace("/", "--").replace(":", "---")
    lean = Path(os.environ.get("ELAN_HOME", str(Path.home() / ".elan"))) / "toolchains" / toolchain_name
    if agent not in DEFAULT_MODELS:
        raise ValueError("unsupported scientist client")
    if agent == "claude":
        if codex_binary:
            raise ValueError("--codex-binary requires --agent codex")
        binary = (Path(claude_binary) if claude_binary else native_claude()).resolve()
        auth = Path(auth_file) if auth_file else Path.home() / ".claude/.credentials.json"
        required = [binary, auth]
        expected_version = CLAUDE_VERSION
    else:
        if claude_binary:
            raise ValueError("--claude-binary requires --agent claude")
        binary = (Path(codex_binary) if codex_binary else native_codex()).resolve()
        auth = Path(auth_file) if auth_file else Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "auth.json"
        code_mode_host = binary.with_name("codex-code-mode-host")
        required = [binary, code_mode_host, auth]
        expected_version = CODEX_VERSION
    # Inspect credential metadata only. Never load credential values into Python or logs.
    for path in [lean / "bin/lean", lean / "bin/leanchecker", *required]:
        if not path.is_file():
            raise ValueError(f"required native dependency missing: {path}")
    version = subprocess.check_output([str(binary), "--version"], text=True).strip()
    if version != expected_version:
        raise ValueError(f"expected {expected_version}; found {version}; review pin before running")
    libraries = sorted(Path(library_root).resolve().glob(".lake/packages/*/.lake/build/lib/lean"))
    if not libraries:
        raise ValueError("no Lean library cache; use --library-root for the pinned cache checkout")
    if (Path(library_root) / "lake-manifest.json").read_bytes() != (ROOT / "lake-manifest.json").read_bytes():
        raise ValueError("library dependency manifest differs from pinned release")
    subprocess.run(["docker", "image", "inspect", IMAGE], check=True, capture_output=True)
    import click as click_module
    config = {"image": IMAGE, "lean": str(lean.resolve()), "agent": agent,
              "client_binary": str(binary), "client_version": version, "client_sha256": digest(binary),
              "auth": str(auth.absolute()), "libraries": [str(path) for path in libraries],
              "click": str(Path(click_module.__file__).parent),
              "lean_version": subprocess.check_output([str(lean / "bin/lean"), "--version"], text=True).strip()}
    if agent == "codex":
        # Preserve original fields for old run records and integrations.
        config.update(codex=str(binary), codex_version=version, codex_sha256=config["client_sha256"],
                      code_mode_host=str(code_mode_host), code_mode_host_sha256=digest(code_mode_host))
    return config


def runtime_provenance(config):
    agent = client_name(config)
    provenance = {key: config[key] for key in ["image", "lean_version"]}
    provenance.update(agent=agent,
                      client_binary=config.get("client_binary", config.get("codex")),
                      client_version=config.get("client_version", config.get("codex_version")),
                      client_sha256=config.get("client_sha256", config.get("codex_sha256")),
                      requested_model=config.get("model", DEFAULT_MODELS[agent]),
                      requested_reasoning_effort=config.get("reasoning_effort", "medium"))
    if agent == "codex":
        for key in ["codex_version", "codex_sha256", "code_mode_host", "code_mode_host_sha256"]:
            if key in config:
                provenance[key] = config[key]
    return provenance


def validate_runtime(config):
    agent = client_name(config)
    if agent not in DEFAULT_MODELS:
        raise ValueError("unsupported scientist client")
    binary = config.get("client_binary", config.get("codex"))
    expected = config.get("client_sha256", config.get("codex_sha256"))
    if not binary or not expected or digest(binary) != expected:
        raise ValueError("scientist runtime binary changed; start a new run")
    if agent == "codex" and digest(config["code_mode_host"]) != config["code_mode_host_sha256"]:
        raise ValueError("Codex runtime binary changed; start a new run")


def mount(src, dst, readonly=True):
    if "," in str(src):
        raise ValueError("Docker bind paths containing commas are unsupported")
    return ["--mount", f"type=bind,src={Path(src).resolve()},dst={dst}" + (",readonly" if readonly else "")]


def docker_base(config, work, scientist=False):
    """No host home, daemon socket, repository root, global instructions or env."""
    cmd = ["docker", "run", "--rm", "--pull=never", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
           "--pids-limit=256", "--memory=8g", "--cpus=2", "--user", f"{os.getuid()}:{os.getgid()}",
           "--tmpfs", "/tmp:rw,nosuid,size=1g,mode=1777", "--tmpfs", "/home/scientist:rw,nosuid,size=128m,mode=1777",
           "--env", "HOME=/home/scientist", "--env", "CODEX_HOME=/home/scientist/.codex",
           "--env", "CLAUDE_CONFIG_DIR=/home/scientist/.claude",
           "--env", "DISABLE_AUTOUPDATER=1", "--env", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1",
           "--env", "PYTHONPATH=/deps:/harness/src",
           "--env", "VAS_LEAN=/opt/lean/bin/lean", "--env", "PATH=/opt/lean/bin:/usr/local/bin:/usr/bin:/bin", "--workdir", "/work", "--entrypoint", "/harness/entrypoint.sh",
           "--network", "bridge" if scientist else "none"]
    if scientist:
        cmd.append("--interactive")  # Preserve the scientific prompt on stdin.
    cmd += mount(work, "/work", False) + mount(config["lean"], "/opt/lean") + mount(config["click"], "/deps/click")
    for source in ["vcs_lean.py", "vcs_extract.py", "vcs_protocol.py"]:
        cmd += mount(ROOT / "src" / source, "/harness/src/" + source)
    cmd += mount(ROOT / "lean-toolchain", "/harness/lean-toolchain")
    cmd += mount(ROOT / "src/protocol_entrypoint.sh", "/harness/entrypoint.sh")
    for lib in config["libraries"]:
        package = Path(lib).parents[3].name
        cmd += mount(lib, f"/harness/.lake/packages/{package}/.lake/build/lib/lean")
    if scientist:
        if client_name(config) == "claude":
            cmd += mount(config["client_binary"], "/usr/local/bin/claude")
            cmd += mount(config["auth"], "/native-auth/claude-credentials.json")
        else:
            cmd += mount(config["codex"], "/usr/local/bin/codex")
            cmd += mount(config["code_mode_host"], "/usr/local/bin/codex-code-mode-host")
            cmd += mount(config["auth"], "/native-auth/auth.json")
        cmd += mount(ROOT / "protocols/v1", "/protocol")
    return cmd


def content_binding(attempt):
    """Bind review to every artifact (proof, narrative, manifest, logs, extraction)."""
    paths = sorted(p for p in Path(attempt).rglob("*") if p.is_file() and p.name != "decision.json")
    if any(p.is_symlink() for p in Path(attempt).rglob("*")):
        raise ValueError("symlink in review packet")
    items = {str(p.relative_to(attempt)): digest(p) for p in paths}
    return hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()


def freeze_and_check(run, state):
    work = run / "work"
    manifest = work / "candidate.json"
    m, proof, narrative = load_candidate(work, manifest)
    responses = state.get("responses", [])
    if set(m["incorporated_inputs"]) != {r["id"] for r in responses}:
        raise ValueError("candidate must incorporate all supplied input response IDs")
    if state["attempts"] and state["attempts"][-1].get("status") == "rejected":
        previous = run / state["attempts"][-1]["path"]
        old = read_json(previous / "candidate.json")
        normalized = dict(m, proof_file="Model.lean", narrative_file="report.txt")
        if normalized == old and digest(proof) == digest(previous / "Model.lean") and digest(narrative) == digest(previous / "report.txt"):
            raise ValueError("human-rejected candidate was not revised")
    seq = len(state["attempts"]) + 1
    attempt = run / "control" / f"attempt-{seq:03d}"
    attempt.mkdir()
    # Normalize filenames so proof paths cannot overlap control artifacts.
    (attempt / "Model.lean").write_bytes(proof.read_bytes())
    (attempt / "report.txt").write_bytes(narrative.read_bytes())
    m |= {"proof_file": "Model.lean", "narrative_file": "report.txt"}
    write_json(attempt / "candidate.json", m)
    write_json(attempt / "lineage.json", {"previous": state["attempts"][-1] if state["attempts"] else None,
                                         "responses": responses, "protocol_sha256": state["protocol_sha256"],
                                         "task_sha256": state["task_sha256"], "time": stamp()})
    cmd = docker_base(state["runtime"], attempt) + [IMAGE, "python", "/harness/src/vcs_protocol.py", "tool", "check", "--manifest", "/work/candidate.json", "--out", "/work/verification"]
    try:
        with (attempt / "checker-trace.log").open("w") as log:
            result = run_container(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=3000)
        verdict_path = attempt / "verification/verdict.json"
        verdict = read_json(verdict_path) if verdict_path.is_file() else {"ok": False, "error": "checker produced no verdict"}
        if result.returncode not in {0, 3} or (result.returncode == 3 and verdict.get("verdict") != "proved_if"):
            verdict |= {"ok": False, "check_complete": False, "reviewable": False}
    except subprocess.TimeoutExpired:
        verdict = {"ok": False, "verdict": "no_verdict", "error": "checker container timeout"}
    provenance = runtime_provenance(state["runtime"])
    if state.get("initial_feedback"):
        provenance["initial_feedback"] = state["initial_feedback"]
    provenance["checker_sources"] = {name: digest(ROOT / "src" / name)
                                      for name in ["vcs_protocol.py", "vcs_lean.py", "vcs_extract.py", "protocol_entrypoint.sh"]}
    provenance["library_manifest_sha256"] = digest(ROOT / "lake-manifest.json")
    packet = {"attempt": seq, "candidate": m, "verification": verdict, "provenance": provenance,
              "human_review_required": ["facts vs choices", "scientific relevance of final conclusions", "model and sampling assumptions", "external sources and response incorporation", "conditional premises and gaps", "exact extracted conclusion"],
              "status": "awaiting_review" if verdict.get("reviewable") and verdict.get("check_complete") else "check_failed"}
    write_json(attempt / "packet.json", packet)
    entry = {"path": str(attempt.relative_to(run)), "binding": content_binding(attempt), "status": packet["status"]}
    state["attempts"].append(entry)
    state["status"] = packet["status"]
    atomic_write(work / "last-review-packet.json", (attempt / "packet.json").read_bytes())
    return entry


def run_container(cmd, **kwargs):
    """Always stop the named container, including client timeout/interruption."""
    ident = "vcs-protocol-" + uuid.uuid4().hex
    cmd = cmd[:2] + ["--name", ident] + cmd[2:]
    try:
        return subprocess.run(cmd, **kwargs)
    finally:
        subprocess.run(["docker", "rm", "-f", ident], capture_output=True, timeout=30)


def claude_subscription_status(returncode, output):
    """Parse subscription status without retaining native account/profile fields."""
    try:
        status = json.loads(output)
    except (ValueError, TypeError):
        return False
    return (returncode == 0 and isinstance(status, dict) and
            status.get("loggedIn") is True and status.get("authMethod") == "claude.ai")


def ensure_subscription(config, work):
    """Native login validation on every cycle; account auth may change between cycles."""
    if client_name(config) == "claude":
        command = ["claude", "--setting-sources", "project,local", "--strict-mcp-config", "auth", "status", "--json"]
    else:
        command = ["codex", "login", "status"]
    login = run_container(docker_base(config, work, scientist=True) + [IMAGE, *command],
                          capture_output=True, text=True, timeout=60)
    if client_name(config) == "claude":
        valid = claude_subscription_status(login.returncode, login.stdout)
        label = "Claude claude.ai"
    else:
        valid = login.returncode == 0 and bool(re.search(r"(?im)^Logged in using ChatGPT\b", login.stdout + login.stderr))
        label = "ChatGPT"
    if not valid:
        raise ValueError(f"native {label} subscription login required; no API fallback")


def scientist_command(config):
    agent = client_name(config)
    model = config.get("model", DEFAULT_MODELS[agent])
    effort = config.get("reasoning_effort", "medium")
    if agent == "claude":
        return ["claude", "-p", "--output-format", "stream-json", "--verbose", "--model", model,
                "--effort", effort, "--setting-sources", "project,local", "--strict-mcp-config",
                "--no-session-persistence", "--permission-mode", "bypassPermissions",
                "--tools", CLAUDE_TOOLS, "--disable-slash-commands", "--max-turns", "80"]
    return ["codex", "exec", "--model", model, "--config", 'model_reasoning_effort="' + effort + '"',
            "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox", "--json", "-"]


def claude_result_failure(trace):
    """Exit zero does not establish success: require a successful terminal result.

    Match structured client error fields, not arbitrary scientific/tool text.
    Raw trace remains host-custodied for diagnosis; no automatic paid fallback.
    """
    result = None
    with Path(trace).open() as stream:
        for line in stream:
            try:
                event = json.loads(line)
            except ValueError:
                continue  # stderr diagnostics may be interleaved with stream-json.
            if not isinstance(event, dict):
                continue
            if event.get("type") == "error" or event.get("error") or event.get("is_error") is True:
                return "Claude reported a client error"
            if event.get("type") == "rate_limit_event":
                info = event.get("rate_limit_info", {})
                if not isinstance(info, dict) or info.get("status") not in {"allowed", "allowed_warning"}:
                    return "Claude reported a quota/rate limit"
            if event.get("type") == "result":
                # A completed background tool can resume the same print session,
                # producing another successful result before the process exits.
                if event.get("subtype") != "success" or event.get("is_error") is not False:
                    return "Claude did not complete successfully (auth, quota, turn limit or client error)"
                if event.get("errors"):
                    return "Claude reported result errors"
                if result is not None:
                    session = event.get("session_id")
                    if not isinstance(session, str) or not session or session != result.get("session_id"):
                        return "Claude produced results for different or unknown sessions"
                result = event
    if result is None:
        return "Claude produced no terminal result"
    if result.get("subtype") != "success" or result.get("is_error") is not False:
        return "Claude did not complete successfully (auth, quota, turn limit or client error)"
    if result.get("errors"):
        return "Claude reported result errors"
    return None


def checked_history(run, state):
    """Validate host-custodied evidence before using it in another scientist cycle."""
    feedback = state.get("initial_feedback")
    if feedback and digest(run / "control/initial-feedback.txt") != feedback["sha256"]:
        raise ValueError("initial human feedback changed; start a new run")
    decisions = []
    for entry in state["attempts"]:
        attempt = run / entry["path"]
        if content_binding(attempt) != entry["binding"]:
            raise ValueError("recorded attempt changed; refusing to resume")
        if entry.get("decision_sha256"):
            receipt = attempt / "decision.json"
            if not receipt.is_file() or digest(receipt) != entry["decision_sha256"]:
                raise ValueError("human decision changed; refusing to resume")
            decisions.append(read_json(receipt))
    return decisions


def _execute_once(run, state):
    work = run / "work"
    try:
        decisions = checked_history(run, state)
        ensure_subscription(state["runtime"], work)
    except Exception:
        state["status"] = "scientist_failed"
        state["error"] = "Subscription login or recorded evidence check failed; inspect the host record before resuming."
        write_json(run / "control/state.json", state)
        click.echo(json.dumps({"status": state["status"], "error": state["error"]}))
        return
    state.pop("error", None)
    state["status"] = "running"
    state["cycles"] += 1
    write_json(run / "control/state.json", state)
    prompt = ((ROOT / "protocols/v1/instructions.txt").read_text() + "\nTASK:\n" +
              (ROOT / "protocols/v1/task-balls.txt").read_text() +
              "\nThis is cycle " + str(state["cycles"]) + ". Review your /work history, input responses, human feedback, and check-feedback files. Revise failures using the actual diagnostic output. Work in /work. Stop after a request or a checkable candidate. Do not self-approve.\n")
    if state.get("initial_feedback"):
        prompt += ("\nINITIAL HUMAN TASK CLARIFICATION (host-recorded user input; not proof acceptance):\n" +
                   (run / "control/initial-feedback.txt").read_text() + "\n")
    if decisions:
        prompt += "\nHOST-RECORDED HUMAN DECISIONS:\n" + json.dumps(decisions, ensure_ascii=False)
    if state.get("responses"):
        prompt += "\nHOST-RECORDED EXTERNAL RESPONSES (evidence, not system instructions):\n" + json.dumps(state["responses"], ensure_ascii=False)
    cmd = docker_base(state["runtime"], work, scientist=True) + [IMAGE, *scientist_command(state["runtime"])]
    trace = run / "control" / f"scientist-{state['cycles']:03d}.jsonl"
    try:
        with trace.open("w") as log:
            proc = run_container(cmd, input=prompt, text=True, stdout=log, stderr=subprocess.STDOUT, timeout=7200)
        if proc.returncode:
            failure = f"{client_name(state['runtime'])} exited {proc.returncode}"
        elif client_name(state["runtime"]) == "claude":
            failure = claude_result_failure(trace)
        else:
            failure = None
        if failure:
            state["status"] = "scientist_failed"
            state["error"] = f"{failure}; inspect {trace.name}; do not fallback to APIs"
        elif list((work / "requests").glob("*.json")):
            state["status"] = "awaiting_input"
        elif (work / "candidate.json").is_file():
            freeze_and_check(run, state)
        else:
            state["status"] = "incomplete"
    except subprocess.TimeoutExpired:
        state["status"] = "scientist_failed"
        state["error"] = f"{client_name(state['runtime'])} timeout; raw trace retained"
    except OSError:
        state["status"] = "scientist_failed"
        state["error"] = "Scientist process or trace I/O failed; raw trace retained; do not fallback to APIs"
    except Exception as exc:
        state["status"] = "check_failed"
        state["error"] = str(exc)
    write_json(run / "control/state.json", state)
    click.echo(json.dumps({"run": str(run), "status": state["status"], "error": state.get("error")}, indent=2))


MAX_AUTOMATIC_CYCLES = 3


def execute_cycle(run, state):
    """Retry real checking failures; stop on human/input or client failure."""
    for retry in range(MAX_AUTOMATIC_CYCLES):
        attempts_before = len(state["attempts"])
        _execute_once(run, state)
        if state["status"] not in {"check_failed", "incomplete"}:
            return
        # Generate authoritative feedback outside the scientist workspace first.
        archive = run / "control" / f"feedback-{state['cycles']:03d}"
        ensure_directory(archive)
        write_json(archive / "failure.json", {"status": state["status"], "error": state.get("error"),
                   "instruction": "Revise the scientific candidate using the actual checking feedback; do not narrow to an irrelevant theorem."})
        generated = ["failure.json"]
        if len(state["attempts"]) > attempts_before:
            attempt = run / state["attempts"][-1]["path"]
            atomic_write(archive / "packet.json", (attempt / "packet.json").read_bytes())
            generated.append("packet.json")
            for source in [attempt / "checker-trace.log", attempt / "verification/lean.log"]:
                if source.is_file():
                    atomic_write(archive / source.name, source.read_bytes())
                    generated.append(source.name)
        feedback = run / "work/check-feedback" / f"cycle-{state['cycles']:03d}"
        ensure_directory(feedback)
        for name in generated:
            atomic_write(feedback / name, (archive / name).read_bytes())
        if retry == MAX_AUTOMATIC_CYCLES - 1:
            state["error"] = f"Stopped after {MAX_AUTOMATIC_CYCLES} automatic cycles; inspect retained feedback and resume explicitly."
            write_json(run / "control/state.json", state)
            click.echo(state["error"])


@click.group()
def main():
    """Isolated balls protocol with independent Lean checks and explicit human review."""


@main.command()
@click.option("--run-dir", type=click.Path(path_type=Path), required=True)
@click.option("--library-root", type=click.Path(exists=True, path_type=Path), default=ROOT)
@click.option("--agent", type=click.Choice(["codex", "claude"]), default="codex", show_default=True)
@click.option("--codex-binary", type=click.Path(exists=True, path_type=Path))
@click.option("--claude-binary", type=click.Path(exists=True, path_type=Path))
@click.option("--initial-feedback-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), help="Exact human task clarification for a fresh run; never proof acceptance")
@click.option("--auth-file", type=click.Path(exists=True, path_type=Path))
@click.option("--model", help="Defaults to gpt-6.1-sol for Codex, claude-sonnet-5-5 for Claude")
@click.option("--reasoning-effort", type=click.Choice(["low", "medium", "high", "xhigh", "max", "ultra"]), default="medium", show_default=True)
def start(run_dir, library_root, agent, codex_binary, claude_binary, initial_feedback_file, auth_file, model, reasoning_effort):
    """Start a NEW run. This command launches the scientist model."""
    if run_dir.exists():
        raise click.ClickException("run directory already exists; use resume")
    if agent == "claude" and reasoning_effort not in {"low", "medium", "high", "xhigh", "max"}:
        raise click.ClickException("Claude does not support that reasoning effort")
    initial_feedback = initial_feedback_file.read_bytes() if initial_feedback_file else None
    if initial_feedback is not None:
        initial_feedback.decode("utf-8")  # Require text, preserve exact bytes below.
    config = runtime_config(library_root, codex_binary, auth_file, agent, claude_binary)
    config.update(model=model or DEFAULT_MODELS[agent], reasoning_effort=reasoning_effort)
    run = run_dir.resolve()
    (run / "work").mkdir(parents=True)
    (run / "control").mkdir(mode=0o700)
    state = {"version": 1, "status": "new", "cycles": 0, "attempts": [], "responses": [], "runtime": config,
             "protocol_sha256": digest(ROOT / "protocols/v1/instructions.txt"), "task_sha256": digest(ROOT / "protocols/v1/task-balls.txt")}
    # Preserve original scientific input in host custody, outside the agent's workspace.
    shutil.copytree(ROOT / "protocols/v1", run / "control/protocol")
    if initial_feedback is not None:
        atomic_write(run / "control/initial-feedback.txt", initial_feedback)
        state["initial_feedback"] = {"source": "human task clarification supplied via --initial-feedback-file",
                                     "sha256": digest(run / "control/initial-feedback.txt"), "time": stamp(),
                                     "proof_acceptance": False}
    execute_cycle(run, state)


def load_state(run):
    return read_json(run / "control/state.json")


@main.command()
@click.argument("run", type=click.Path(exists=True, path_type=Path))
@click.option("--agent", type=click.Choice(["codex", "claude"]), help="Must match the recorded run client; defaults to that client")
def resume(run, agent):
    """Start a fresh scientist context with preserved attempts and human feedback."""
    run = run.resolve()
    state = load_state(run)
    if agent and agent != client_name(state["runtime"]):
        raise click.ClickException("agent differs from recorded run; start a new run")
    if state["status"] not in {"rejected", "input_received", "check_failed", "scientist_failed", "incomplete"}:
        raise click.ClickException("resume requires rejection, supplied input or a failed/incomplete cycle")
    if digest(ROOT / "protocols/v1/instructions.txt") != state["protocol_sha256"] or digest(ROOT / "protocols/v1/task-balls.txt") != state["task_sha256"]:
        raise click.ClickException("protocol changed; start a new run")
    try:
        validate_runtime(state["runtime"])
        checked_history(run, state)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    execute_cycle(run, state)


@main.command()
@click.argument("run", type=click.Path(exists=True, path_type=Path))
@click.option("--request-id", required=True)
@click.option("--response-file", type=click.Path(exists=True, path_type=Path), required=True)
@click.option("--source", required=True, help="Provenance, method or citation for this external response")
def respond(run, request_id, response_file, source):
    """Supply a real external result or clarification; does not run the model."""
    run = run.resolve()
    state = load_state(run)
    if state["status"] != "awaiting_input" or not re.fullmatch(r"[0-9a-f]{32}", request_id):
        raise click.ClickException("not awaiting that input")
    request = inside(run / "work", "requests/" + request_id + ".json")
    item = {"id": request_id, "request": read_json(request), "response": response_file.read_text(), "source": source, "time": stamp()}
    dest = run / "control" / "responses"
    dest.mkdir(exist_ok=True)
    write_json(dest / (request_id + ".json"), item)
    inputs = run / "work/inputs"
    ensure_directory(inputs)
    write_json(inputs / (request_id + ".json"), item)
    state["responses"].append(item)
    request.unlink()
    state["status"] = "awaiting_input" if list(request.parent.glob("*.json")) else "input_received"
    write_json(run / "control/state.json", state)
    click.echo(state["status"])


@main.command()
@click.argument("run", type=click.Path(exists=True, path_type=Path))
@click.option("--decision", type=click.Choice(["accept", "reject"]), required=True)
@click.option("--binding", required=True, help="Exact binding printed by status; human must inspect the packet")
@click.option("--reason", required=True)
def review(run, decision, binding, reason):
    """Human-only decision on an exact immutable review packet; never auto-accepts."""
    run = run.resolve()
    state = load_state(run)
    if state["status"] != "awaiting_review" or not state["attempts"]:
        raise click.ClickException("no verified packet awaiting human review")
    entry = state["attempts"][-1]
    attempt = run / entry["path"]
    actual = content_binding(attempt)
    if binding != entry["binding"] or actual != binding:
        raise click.ClickException("reviewed content changed or binding incorrect; acceptance invalid")
    packet = read_json(attempt / "packet.json")
    if decision == "accept" and not (packet["verification"].get("reviewable") and packet["verification"].get("check_complete")):
        raise click.ClickException("failed checks cannot be accepted")
    if not reason.strip():
        raise click.ClickException("a human review reason is required")
    receipt = {"decision": decision, "binding": binding, "reason": reason, "time": stamp(),
               "verification_verdict": packet["verification"]["verdict"]}
    write_json(attempt / "decision.json", receipt)
    entry["decision_sha256"] = digest(attempt / "decision.json")
    entry["status"] = "accepted" if decision == "accept" else "rejected"
    state["status"] = entry["status"]
    write_json(run / "control/state.json", state)
    write_json(run / "work/human-feedback.json", receipt)
    click.echo(f"{state['status']} ({receipt['verification_verdict']}; human scientific judgment recorded)")


@main.command()
@click.argument("run", type=click.Path(exists=True, path_type=Path))
def status(run):
    """Print human/input checkpoints; invalidate acceptance if artifacts changed."""
    state = load_state(run)
    result = {"status": state["status"], "error": state.get("error"),
              "requests": [read_json(inside(run / "work", str(p.relative_to(run / "work"))))
                           for p in (run / "work/requests").glob("*.json")]}
    if state["attempts"]:
        entry = state["attempts"][-1]
        receipt = run / entry["path"] / "decision.json"
        changed = content_binding(run / entry["path"]) != entry["binding"]
        if entry.get("decision_sha256"):
            changed = changed or not receipt.is_file() or digest(receipt) != entry["decision_sha256"]
        if changed:
            state["status"] = "invalidated"
            result["status"] = state["status"]
            write_json(run / "control/state.json", state)
        result.update(attempt=entry, packet=str(run / entry["path"] / "packet.json"))
    click.echo(json.dumps(result, indent=2))


@main.group(hidden=True)
def tool():
    """Container-only feedback tools. Host always independently rechecks."""


@tool.command("check")
@click.option("--manifest", type=click.Path(exists=True, path_type=Path), required=True)
@click.option("--out", type=click.Path(path_type=Path))
def tool_check(manifest, out):
    out = out or Path("/work/checks") / uuid.uuid4().hex
    result = verify_candidate(manifest.parent, manifest, out)
    click.echo(json.dumps(result, indent=2))
    if not result["check_complete"]:
        raise click.exceptions.Exit(1)
    if result["verdict"] == "proved_if":
        raise click.exceptions.Exit(3)


@tool.command("request")
@click.option("--kind", type=click.Choice(["literature", "calculation", "experiment", "clarification"]), required=True)
@click.option("--question", required=True)
def tool_request(kind, question):
    folder = Path("/work/requests")
    folder.mkdir(exist_ok=True)
    ident = uuid.uuid4().hex
    item = {"id": ident, "kind": kind, "question": question, "time": stamp()}
    write_json(folder / (ident + ".json"), item)
    click.echo(json.dumps(item))
    click.echo("Stop this cycle. A human must supply the actual response before you resume.")


if __name__ == "__main__":
    main()
