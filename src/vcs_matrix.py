"""Finite, host-owned queue of three questions × two independent native clients.

No daemon, automatic review, answer synthesis, client fallback or implicit resume.
"""
from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

import click

import vcs_protocol as p

MAX_JOB_SECONDS = 9 * 60 * 60  # Larger than all three bounded protocol cycles.
CHECKPOINTS = {"awaiting_input", "awaiting_review"}
FAILURES = {"failed", "scientist_failed", "check_failed", "incomplete", "invalidated", "interrupted", "timed_out"}


def matrix_limits(memory, cpus, max_concurrent):
    limits = p.resource_limits(memory, cpus)
    number = int(limits["memory"][:-1])
    size_mib = number * (1024 if limits["memory"].endswith("g") else 1)
    if not 1 <= max_concurrent <= 3:
        raise ValueError("max-concurrent must be between 1 and 3")
    if size_mib * max_concurrent > 12 * 1024 or Decimal(limits["cpus"]) * max_concurrent > 6:
        raise ValueError("matrix configured allocations must fit 12 GiB memory and 6 CPUs total")
    return limits


def read_inputs(task_dir, instructions_file):
    tasks = sorted(Path(task_dir).glob("*.txt"))
    if len(tasks) != 3 or any(not path.is_file() for path in tasks):
        raise ValueError("task-dir must contain exactly three natural-language *.txt files")
    sources = {"instructions.txt": Path(instructions_file)}
    sources.update({f"task-{i:02d}.txt": task for i, task in enumerate(tasks, 1)})
    inputs = {}
    for name, source in sources.items():
        data = source.read_bytes()
        if not data.decode("utf-8").strip():
            raise ValueError("matrix inputs must be nonempty UTF-8 text")
        inputs[name] = {"source": str(source.resolve()), "sha256": hashlib.sha256(data).hexdigest(), "data": data}
    return tasks, inputs


def job_command(job, library_root, memory, cpus, input_root):
    return [sys.executable, str(p.ROOT / "src/vcs_protocol.py"), "start",
            "--agent", job["agent"], "--run-dir", job["run_dir"],
            "--library-root", str(Path(library_root).resolve()),
            "--task-file", str(input_root / job["input_name"]),
            "--instructions-file", str(input_root / "instructions.txt"),
            "--expected-task-sha256", job["task_sha256"],
            "--expected-instructions-sha256", job["instructions_sha256"],
            "--model", p.DEFAULT_MODELS[job["agent"]], "--reasoning-effort", "medium",
            "--memory", memory, "--cpus", cpus]


def prepare_manifest(task_dir, instructions_file, run_root, library_root, memory, cpus, max_concurrent):
    """Read inputs once and prepare a reviewable plan, without native CLI calls."""
    limits = matrix_limits(memory, cpus, max_concurrent)
    root = Path(run_root).absolute()
    if root.exists() or root.is_symlink():
        raise ValueError("run-root already exists; matrix runs cannot be reused or resumed")
    tasks, inputs = read_inputs(task_dir, instructions_file)
    manifest = {"version": 1, "created": p.stamp(), "status": "planned", "run_root": str(root),
                "max_concurrent": max_concurrent, "limits_per_run": limits,
                "models": dict(p.DEFAULT_MODELS), "reasoning_effort": "medium",
                "scientific_acceptance": "requires explicit human review for every frozen attempt",
                "inputs": {name: {k: v for k, v in data.items() if k != "data"} for name, data in inputs.items()},
                "blocked_clients": {}, "jobs": []}
    for i, task in enumerate(tasks, 1):
        slug = re.sub(r"[^A-Za-z0-9_-]+", "-", task.stem).strip("-") or "task"
        for agent in ["codex", "claude"]:
            ident = f"{i:02d}-{slug}-{agent}"
            job = {"id": ident, "agent": agent, "input_name": f"task-{i:02d}.txt",
                   "task_source": str(task.resolve()),
                   "task_sha256": inputs[f"task-{i:02d}.txt"]["sha256"],
                   "instructions_sha256": inputs["instructions.txt"]["sha256"], "run_dir": str(root / "runs" / ident),
                   "status": "queued", "exit_code": None,
                   "cli_log": str(root / "logs" / (ident + ".log"))}
            job["command"] = job_command(job, library_root, **limits, input_root=root / "inputs")
            manifest["jobs"].append(job)
    # First wave covers all three questions; the second client follows independently.
    manifest["jobs"].sort(key=lambda job: (job["agent"] != "codex", job["id"]))
    return manifest, inputs


def verify_inputs(root, manifest):
    for name, meta in manifest["inputs"].items():
        path = p.inside(root, "inputs/" + name)
        if p.digest(path) != meta["sha256"]:
            raise ValueError("matrix input snapshot changed; queued jobs will not launch")


def save_manifest(root, manifest):
    manifest["updated"] = p.stamp()
    p.write_json(root / "matrix.json", manifest)


def event(root, kind, job=None, **fields):
    with (root / "matrix.log").open("a") as stream:
        stream.write(json.dumps({"time": p.stamp(), "event": kind,
                                 **({"job": job["id"]} if job else {}), **fields}) + "\n")


def current_state(job, final=False):
    """Only this run's state and checkpoint, never another scientist's output."""
    run = Path(job["run_dir"])
    if not (run / "control/state.json").is_file():
        return None
    if final:
        return p.status_result(run)
    state = p.load_state(run)
    return {"status": state["status"], "cycles": state.get("cycles", 0), "error": state.get("error"), "failure_kind": state.get("failure_kind")}


def startup_failure(job):
    """Startup may stop before a run exists; trust only the launcher's marker."""
    with Path(job["cli_log"]).open() as stream:
        for line in stream:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if (isinstance(item, dict) and item.get("vcs_client_failure") is True and
                    item.get("agent") == job["agent"] and item.get("failure_kind") in {"authentication", "quota"}):
                return item["failure_kind"]
    return None


def stop_child(proc):
    """SIGINT gives protocol.run_container its finally cleanup before escalation."""
    if proc.poll() is not None:
        return
    for sig, grace in [(signal.SIGINT, 40), (signal.SIGTERM, 5), (signal.SIGKILL, 5)]:
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=grace)
            return
        except subprocess.TimeoutExpired:
            continue


@contextmanager
def interruption_handler():
    def stop(signum, frame):
        raise KeyboardInterrupt
    previous = signal.signal(signal.SIGTERM, stop)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def run_queue(root, manifest, *, popen=None, sleep=None, monotonic=None):
    """A finite set of six children; checkpoints free their occupied slot."""
    popen = popen or subprocess.Popen
    sleep = sleep or time.sleep
    monotonic = monotonic or time.monotonic
    active = {}
    jobs = manifest["jobs"]
    manifest["status"] = "running"
    save_manifest(root, manifest)
    try:
        while True:
            # Reap all completed children before deciding whether another may launch.
            for ident, item in list(active.items()):
                job, proc, stream, started = item
                code = proc.poll()
                timed_out = code is None and monotonic() - started > MAX_JOB_SECONDS
                if timed_out:
                    stop_child(proc)
                    code = proc.poll()
                if code is None:
                    try:
                        job["current"] = current_state(job)
                    except (OSError, ValueError, KeyError) as exc:
                        job["status_error"] = str(exc)
                    continue
                stream.close()
                del active[ident]
                job.update(exit_code=code, finished=p.stamp())
                try:
                    result = current_state(job, final=True)
                except (OSError, ValueError, KeyError) as exc:
                    result = None
                    job["status_error"] = str(exc)
                if result:
                    job["current"] = result
                status = result.get("status") if result else None
                job["status"] = "timed_out" if timed_out else (status if code == 0 and status else "failed")
                if job["status"] in {"new", "running", "accepted"}:
                    job["status"] = "failed"
                    job["status_error"] = "child ended without an independent input/review checkpoint or failure state"
                failure_kind = (result or {}).get("failure_kind") or startup_failure(job)
                if failure_kind in {"authentication", "quota"}:
                    job["failure_kind"] = failure_kind
                    manifest["blocked_clients"][job["agent"]] = {
                        "job": ident, "reason": failure_kind + "; owner must repair native subscription before launching queued jobs"}
                event(root, "finished", job, status=job["status"], exit_code=code)
                click.echo(json.dumps({"job": ident, "status": job["status"], "exit_code": code}))
            for job in jobs:
                if len(active) >= manifest["max_concurrent"]:
                    break
                if job["status"] != "queued":
                    continue
                if job["agent"] in manifest["blocked_clients"]:
                    job["blocked_by"] = manifest["blocked_clients"][job["agent"]]
                    continue  # Preserve unfinished jobs as queued, with an explicit reason.
                verify_inputs(root, manifest)
                stream = Path(job["cli_log"]).open("x")
                try:
                    proc = popen(job["command"], stdin=subprocess.DEVNULL, stdout=stream,
                                 stderr=subprocess.STDOUT, start_new_session=True)
                except OSError as exc:
                    stream.close()
                    job.update(status="failed", error=str(exc), finished=p.stamp())
                    event(root, "launch_failed", job, error=str(exc))
                    continue
                job.update(status="running", started=p.stamp(), pid=proc.pid)
                active[job["id"]] = (job, proc, stream, monotonic())
                event(root, "started", job, pid=proc.pid)
            save_manifest(root, manifest)
            if not active:
                break
            sleep(0.25)
        # Fill reasons even if the concurrency bound cut short the last launch scan.
        for job in jobs:
            if job["status"] == "queued" and job["agent"] in manifest["blocked_clients"]:
                job["blocked_by"] = manifest["blocked_clients"][job["agent"]]
        manifest["status"] = "owner_action_required" if manifest["blocked_clients"] else "finished"
    except BaseException as exc:
        manifest["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        manifest["error"] = type(exc).__name__ + ": " + str(exc)
        raise
    finally:
        for job, proc, stream, started in active.values():
            stop_child(proc)
            stream.close()
            job.update(status="interrupted", exit_code=proc.poll(), finished=p.stamp())
            try:
                job["current"] = current_state(job, final=True)
            except (OSError, ValueError, KeyError):
                pass
            event(root, "interrupted", job)
        save_manifest(root, manifest)


@click.command()
@click.option("--task-dir", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
@click.option("--instructions-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--run-root", type=click.Path(path_type=Path), required=True)
@click.option("--library-root", type=click.Path(exists=True, file_okay=False, path_type=Path), default=p.ROOT)
@click.option("--max-concurrent", type=click.IntRange(1, 3), default=3, show_default=True)
@click.option("--memory", default="4g", show_default=True)
@click.option("--cpus", default="2", show_default=True)
@click.option("--dry-run", is_flag=True, help="Print plan without creating files, starting Docker or invoking native clients")
def main(task_dir, instructions_file, run_root, library_root, max_concurrent, memory, cpus, dry_run):
    """Launch six independent runs (three tasks, Codex + Claude); stop at checkpoints."""
    try:
        manifest, inputs = prepare_manifest(task_dir, instructions_file, run_root, library_root,
                                            memory, cpus, max_concurrent)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    if dry_run:
        click.echo(json.dumps(manifest, indent=2))
        return
    root = Path(manifest["run_root"])
    # Exclusive creation: another invocation can never reuse this queue or its state.
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    for folder in ["inputs", "runs", "logs"]:
        p.ensure_directory(root / folder)
    for name, item in inputs.items():
        p.atomic_write(root / "inputs" / name, item["data"])
    save_manifest(root, manifest)
    event(root, "created")
    try:
        with interruption_handler():
            run_queue(root, manifest)
    except KeyboardInterrupt:
        raise click.ClickException("matrix interrupted; children stopped; checkpoints and queued jobs retained")
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps({"matrix": str(root / "matrix.json"), "status": manifest["status"],
                           "jobs": {job["id"]: job["status"] for job in manifest["jobs"]},
                           "scientific_acceptance": manifest["scientific_acceptance"]}, indent=2))
    if manifest["blocked_clients"] or any(job["status"] in FAILURES for job in manifest["jobs"]):
        raise click.exceptions.Exit(1)


if __name__ == "__main__":
    main()
