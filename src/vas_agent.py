"""Run one scientist agent (Claude Code or the Codex CLI) on one task card, reproducibly, and re-check its result.

The agent, model and reasoning effort are pinned in agents/config.json; the prompt is agents/prompt.md (or
agents/prompt_draft.md for claim generation), filled with the task, run, call cap and working directory only.

Isolation. Each run gets a fresh detached git worktree of HEAD outside the home directory, with .lake linked from this
checkout, so the agent sees only committed files. Claude Code runs with --setting-sources project,local (no user
CLAUDE.md, hooks, plugins or MCP servers) and only the Bash, Read, Write, Edit, Grep and Glob tools; Codex runs with
--ignore-user-config (no ~/.codex/config.toml) on the user's own native login: CODEX_HOME, or VAS_CODEX_HOME if set.
Credentials are never copied or read by this script. Codex still reads AGENTS.md from that home; for a clean run, log
in once into a dedicated home (CODEX_HOME=<dir> codex login) and set VAS_CODEX_HOME=<dir>. The manifest records whether
that home has an AGENTS.md. Neither gets web search. Both read the prompt from stdin.

Kept in the repository afterwards:
  artifacts/vas-trail[-drafts]/<task>/<run>.jsonl and <run>/   every checker call (written by src/vas_check.py)
  artifacts/vas-agent-runs/<task>/<run>/                       prompt.md, transcript.jsonl, final.md, manifest.json
  tasks-drafts/<draft>/                                         the agent-written card (claim generation only)
manifest.json records the pinned and the installed CLI versions, the model, the commit, the hashes of the card, the
checker and the prompt, the Lean and Mathlib versions, wall time, exit status and the checker outcome.

Run:  python3 src/vas_agent.py run --agent claude --task radiocarbon --run claude-2 [--cap 20]
      python3 src/vas_agent.py run --agent claude --draft coffee_cooling_2 --run claude-2
      python3 src/vas_agent.py recheck --task radiocarbon --run claude-2     (resubmits the accepted body, no agent)
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

import click

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "agents/config.json").read_text())
RUNS = ROOT / "artifacts/vas-agent-runs"
NAME = re.compile(r"[a-z0-9_-]+")
AGENT_TIMEOUT = 3600


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(*args, cwd=ROOT):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def cli_version(cmd):
    return subprocess.run([cmd, "--version"], capture_output=True, text=True).stdout.strip()


def trail_dir(drafts):
    return ROOT / ("artifacts/vas-trail-drafts" if drafts else "artifacts/vas-trail")


def fill(template, **values):
    # plain substitution: the prompts contain JSON braces, so str.format is not usable
    for key, value in values.items():
        template = template.replace("{" + key + "}", str(value))
    return template


def codex_home():
    return Path(os.environ.get("VAS_CODEX_HOME") or os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def agent_command(agent, workdir):
    cfg = CONFIG[agent]
    if agent == "claude":
        return [cfg["cli"], "-p", "--model", cfg["model"], "--setting-sources", "project,local", "--strict-mcp-config",
                "--no-session-persistence", "--output-format", "stream-json", "--verbose",
                "--permission-mode", "bypassPermissions", "--tools", "Bash,Read,Write,Edit,Grep,Glob"], {}
    return [cfg["cli"], "exec", "--ignore-user-config", "-m", cfg["model"],
            "-c", f'model_reasoning_effort="{cfg["reasoning_effort"]}"', "--skip-git-repo-check", "--ephemeral",
            "--dangerously-bypass-approvals-and-sandbox", "--json", "-C", str(workdir),
            "-o", str(workdir / ".final.md"), "-"], {"CODEX_HOME": str(codex_home())}


def final_message(agent, transcript, workdir):
    if agent == "codex":
        final = workdir / ".final.md"
        return final.read_text() if final.exists() else ""
    for line in reversed(transcript.read_text().splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "result":
            return event.get("result") or ""
    return ""


def outcome(trail_file):
    records = [json.loads(ln) for ln in trail_file.read_text().splitlines()] if trail_file.exists() else []
    accepted = [r["seq"] for r in records if r.get("ok")]
    return {"checker_calls": len(records), "accepted": bool(accepted),
            "first_accepted_seq": accepted[0] if accepted else None}


@click.group()
def cli():
    pass


@cli.command()
@click.option("--agent", type=click.Choice(sorted(CONFIG)), required=True)
@click.option("--task", help="a reviewed card under tasks/")
@click.option("--draft", help="claim generation: the agent writes tasks-drafts/<draft>/ itself")
@click.option("--run", "run_id", required=True)
@click.option("--cap", default=20, show_default=True, help="checker calls the prompt allows")
def run(agent, task, draft, run_id, cap):
    """Run AGENT once on TASK (or DRAFT) in an isolated worktree and keep everything it produced."""
    if bool(task) == bool(draft):
        raise click.UsageError("give exactly one of --task and --draft")
    name = task or draft
    for value in (name, run_id):
        if not NAME.fullmatch(value):
            raise click.UsageError("task, draft and run must match [a-z0-9_-]+")
    drafts = bool(draft)
    trail_file = trail_dir(drafts) / name / f"{run_id}.jsonl"
    out = RUNS / name / run_id
    if trail_file.exists() or out.exists():
        raise click.ClickException(f"run {name}/{run_id} already exists; pick a new run name")
    card = ROOT / ("tasks-drafts" if drafts else "tasks") / name
    if drafts and card.exists():
        raise click.ClickException(f"{card} already exists; pick a new draft name")
    pinned = ["src/vas_check.py", "agents"] + ([] if drafts else [f"tasks/{name}"])
    if git("status", "--porcelain", "--", *pinned):
        raise click.ClickException(f"commit {pinned} first: a run must be tied to a commit")
    if not drafts and not card.exists():
        raise click.ClickException(f"no task card {card}")

    commit = git("rev-parse", "HEAD")
    scratch = Path(tempfile.mkdtemp(prefix="vas-run-"))
    if scratch.resolve().is_relative_to(Path.home()):
        raise click.ClickException("the worktree must be outside the home directory (CLAUDE.md is loaded from there)")
    workdir = scratch / "repo"
    git("worktree", "add", "--detach", str(workdir), commit)
    try:
        (workdir / ".lake").symlink_to(ROOT / ".lake")
        template = (ROOT / "agents" / ("prompt_draft.md" if drafts else "prompt.md")).read_text()
        prompt = fill(template, task=name, draft=name, run=run_id, cap=cap, workdir=workdir)
        out.mkdir(parents=True)
        (out / "prompt.md").write_text(prompt)
        cmd, extra_env = agent_command(agent, workdir)
        env = dict(os.environ, **extra_env)
        env.pop("VAS_DRAFTS", None)
        transcript = out / "transcript.jsonl"
        t0 = time.time()
        with transcript.open("w") as log:
            try:
                status = subprocess.run(cmd, cwd=workdir, env=env, input=prompt, text=True, stdout=log,
                                        stderr=subprocess.STDOUT, timeout=AGENT_TIMEOUT).returncode
            except subprocess.TimeoutExpired:
                status = 124
        wall = time.time() - t0
        (out / "final.md").write_text(final_message(agent, transcript, workdir))

        wt_trail = workdir / trail_file.relative_to(ROOT)
        if wt_trail.exists():
            trail_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(wt_trail, trail_file)
            shutil.copytree(wt_trail.with_suffix(""), trail_file.with_suffix(""))
        if drafts and (workdir / card.relative_to(ROOT)).exists():
            shutil.copytree(workdir / card.relative_to(ROOT), card)
            lint = workdir / "artifacts/vas-trail-drafts" / name / "lint.lean"
            if lint.exists():
                shutil.copy2(lint, trail_file.parent / "lint.lean")
        manifest = {
            "agent": agent, "task": name, "drafts": drafts, "run": run_id, "cap": cap,
            "pinned": CONFIG[agent], "installed_cli": cli_version(CONFIG[agent]["cli"]),
            "instructions_outside_repo": ((codex_home() / "AGENTS.md").exists() if agent == "codex" else False),
            "commit": commit, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "checker_sha256": sha(ROOT / "src/vas_check.py"),
            "card_sha256": {p.name: sha(p) for p in sorted(card.glob("*")) if p.is_file()},
            "lean_toolchain": (ROOT / "lean-toolchain").read_text().strip(),
            "mathlib_rev": next(p["rev"] for p in json.loads((ROOT / "lake-manifest.json").read_text())["packages"]
                                if p["name"] == "mathlib"),
            "started": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(t0)), "wall_s": round(wall, 1),
            "exit_code": status, **outcome(trail_file),
        }
        (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
        click.echo(json.dumps(manifest))
    finally:
        git("worktree", "remove", "--force", str(workdir))
        shutil.rmtree(scratch, ignore_errors=True)


@cli.command()
@click.option("--task", required=True)
@click.option("--run", "run_id", required=True)
@click.option("--drafts", is_flag=True, help="the task is an agent-drafted card under tasks-drafts/")
def recheck(task, run_id, drafts):
    """Resubmit the first accepted body of TASK/RUN from scratch, as run recheck-RUN, without any agent."""
    trail_file = trail_dir(drafts) / task / f"{run_id}.jsonl"
    records = [json.loads(ln) for ln in trail_file.read_text().splitlines()]
    accepted = next((r for r in records if r.get("ok")), None)
    if accepted is None:
        raise click.ClickException(f"{task}/{run_id} has no accepted attempt")
    source = (ROOT / accepted["lean_file"]).read_text()
    start = source.index("open Task\n\n") + len("open Task\n\n")
    body = source[start:source.index("\ntheorem verifier_", start)]
    if drafts:
        os.environ["VAS_DRAFTS"] = "1"
    import vas_check  # after VAS_DRAFTS is set: it selects the task and trail directories at import

    spec = (vas_check.TASKS / task / "Spec.lean").read_text()
    if spec not in source:
        raise click.ClickException("Spec.lean changed since the accepted attempt")
    rec = vas_check.check(task, body, f"recheck-{run_id}", "accepted")
    click.echo(json.dumps({k: rec[k] for k in ("task", "run", "ok", "wall_s", "errors") if k in rec}))
    if not rec["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
