"""Bounded scheduler controls with fake child processes, never model calls."""
import json
from pathlib import Path
import subprocess

from click.testing import CliRunner
import pytest

import vcs_matrix as m
import vcs_protocol as p


@pytest.fixture
def plan(tmp_path):
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    for name in ["carp", "boiling-salt", "coffee"]:
        (tasks / (name + ".txt")).write_text("Natural question " + name + "\n")
    instructions = tmp_path / "instructions.txt"
    instructions.write_text("Current generic instructions only.\n")
    root = tmp_path / "matrix"
    manifest, inputs = m.prepare_manifest(tasks, instructions, root, tmp_path, "4g", "2", 3)
    return root, manifest, inputs, tasks, instructions


def materialize(plan):
    root, manifest, inputs, _, _ = plan
    root.mkdir()
    for folder in ["inputs", "runs", "logs"]:
        (root / folder).mkdir()
    for name, item in inputs.items():
        (root / "inputs" / name).write_bytes(item["data"])
    return root, manifest


class FakeChildren:
    def __init__(self, manifest, outcomes=None, launch_errors=None):
        self.jobs = {job["run_dir"]: job for job in manifest["jobs"]}
        self.outcomes = outcomes or {}
        self.launch_errors = set(launch_errors or [])
        self.tick = 0
        self.live = set()
        self.maximum = 0
        self.launched = []
        self.children = []

    def sleep(self, duration):
        self.tick += 1

    def popen(self, command, **kwargs):
        job = self.jobs[command[command.index("--run-dir") + 1]]
        self.launched.append(job["id"])
        if job["id"] in self.launch_errors:
            raise OSError("test child launch error")
        assert kwargs["stdin"] == subprocess.DEVNULL and kwargs["start_new_session"] is True
        assert kwargs["stderr"] == subprocess.STDOUT
        child = FakeProcess(self, job, kwargs["stdout"])
        self.children.append(child)
        self.live.add(job["id"])
        self.maximum = max(self.maximum, len(self.live))
        return child


class FakeProcess:
    def __init__(self, queue, job, output):
        self.queue, self.job = queue, job
        self.pid = 10000 + len(queue.children)
        self.done = queue.tick + 2
        self.returncode = None
        output.write("raw test child output\n")
        output.flush()

    def poll(self):
        if self.returncode is None and self.queue.tick >= self.done:
            outcome = self.queue.outcomes.get(self.job["id"], {"status": "awaiting_review"})
            self.returncode = outcome.get("exit_code", 0)
            self.queue.live.discard(self.job["id"])
            run = Path(self.job["run_dir"])
            (run / "control").mkdir(parents=True)
            (run / "work/requests").mkdir(parents=True)
            state = {"status": outcome["status"], "attempts": [], "cycles": 1,
                     "failure_kind": outcome.get("failure_kind"), "error": outcome.get("error")}
            p.write_json(run / "control/state.json", state)
            if state["status"] == "awaiting_input":
                p.write_json(run / "work/requests/test.json", {"id": "test", "question": "actual human input needed"})
        return self.returncode


def test_dry_run_and_help_never_spawn_or_create_root(plan, monkeypatch):
    root, manifest, _, tasks, instructions = plan
    monkeypatch.setattr(m.subprocess, "Popen", lambda *a, **kw: pytest.fail("dry run started a child"))
    args = ["--task-dir", str(tasks), "--instructions-file", str(instructions), "--run-root", str(root), "--dry-run"]
    result = CliRunner().invoke(m.main, args)
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert len(data["jobs"]) == 6 and data["status"] == "planned"
    assert len({job["task_source"] for job in data["jobs"][:3]}) == 3
    assert [job["agent"] for job in data["jobs"]] == ["codex"] * 3 + ["claude"] * 3
    assert not root.exists()
    assert CliRunner().invoke(m.main, ["--help"]).exit_code == 0
    for job in data["jobs"]:
        cmd = job["command"]
        assert cmd[cmd.index("--model") + 1] == p.DEFAULT_MODELS[job["agent"]]
        assert cmd[cmd.index("--reasoning-effort") + 1] == "medium"
        assert cmd[cmd.index("--memory") + 1] == "4g"
        assert cmd[cmd.index("--cpus") + 1] == "2"


def test_six_jobs_are_bounded_and_input_review_checkpoints_free_slots(plan):
    root, manifest = materialize(plan)
    outcomes = {manifest["jobs"][0]["id"]: {"status": "awaiting_input"}}
    queue = FakeChildren(manifest, outcomes)
    m.run_queue(root, manifest, popen=queue.popen, sleep=queue.sleep, monotonic=lambda: queue.tick)
    assert queue.maximum == 3 and len(queue.launched) == 6 and not queue.live
    assert manifest["jobs"][0]["current"]["requests"][0]["question"] == "actual human input needed"
    assert {job["status"] for job in manifest["jobs"]} == {"awaiting_input", "awaiting_review"}
    assert manifest["status"] == "finished" and "requires explicit human review" in manifest["scientific_acceptance"]
    assert p.read_json(root / "matrix.json")["jobs"] == manifest["jobs"]
    assert all(Path(job["cli_log"]).read_text() == "raw test child output\n" for job in manifest["jobs"])
    assert len((root / "matrix.log").read_text().splitlines()) == 12


@pytest.mark.parametrize("failure_kind", ["authentication", "quota"])
def test_auth_quota_stops_only_new_jobs_for_affected_client(plan, failure_kind):
    root, manifest = materialize(plan)
    manifest["max_concurrent"] = 1
    first = manifest["jobs"][0]
    queue = FakeChildren(manifest, {first["id"]: {"status": "scientist_failed", "failure_kind": failure_kind}})
    m.run_queue(root, manifest, popen=queue.popen, sleep=queue.sleep, monotonic=lambda: queue.tick)
    codex = [job for job in manifest["jobs"] if job["agent"] == "codex"]
    claude = [job for job in manifest["jobs"] if job["agent"] == "claude"]
    assert codex[0]["status"] == "scientist_failed"
    assert all(job["status"] == "queued" and "blocked_by" in job for job in codex[1:])
    assert all(job["status"] == "awaiting_review" for job in claude)
    assert len(queue.launched) == 4 and manifest["status"] == "owner_action_required"


@pytest.mark.parametrize("outcome", [{"status": "scientist_failed", "failure_kind": "client"},
                                      {"status": "check_failed"}, {"status": "incomplete"},
                                      {"status": "awaiting_review", "exit_code": 7}])
def test_per_job_failure_does_not_silently_cancel_siblings(plan, outcome):
    root, manifest = materialize(plan)
    queue = FakeChildren(manifest, {manifest["jobs"][0]["id"]: outcome})
    m.run_queue(root, manifest, popen=queue.popen, sleep=queue.sleep, monotonic=lambda: queue.tick)
    assert len(queue.launched) == 6 and manifest["blocked_clients"] == {}
    assert all(job["status"] == "awaiting_review" for job in manifest["jobs"][1:])
    assert manifest["jobs"][0]["status"] in {"failed", "scientist_failed", "check_failed", "incomplete"}


def test_launch_error_keeps_other_jobs_eligible(plan):
    root, manifest = materialize(plan)
    queue = FakeChildren(manifest, launch_errors=[manifest["jobs"][0]["id"]])
    m.run_queue(root, manifest, popen=queue.popen, sleep=queue.sleep, monotonic=lambda: queue.tick)
    assert len(queue.launched) == 6 and manifest["jobs"][0]["status"] == "failed"
    assert all(job["status"] == "awaiting_review" for job in manifest["jobs"][1:])


def test_interruption_cleans_live_children_and_preserves_unstarted_jobs(plan, monkeypatch):
    root, manifest = materialize(plan)
    queue = FakeChildren(manifest)
    stopped = []
    def stop(proc):
        stopped.append(proc.job["id"])
        proc.returncode = -2
        queue.live.discard(proc.job["id"])
    monkeypatch.setattr(m, "stop_child", stop)
    def interrupt(duration):
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        m.run_queue(root, manifest, popen=queue.popen, sleep=interrupt, monotonic=lambda: 0)
    assert len(stopped) == 3 and not queue.live
    assert [job["status"] for job in manifest["jobs"]] == ["interrupted"] * 3 + ["queued"] * 3
    assert p.read_json(root / "matrix.json")["status"] == "interrupted"


def test_mutated_matrix_snapshot_prevents_launch(plan):
    root, manifest = materialize(plan)
    (root / "inputs/task-01.txt").write_text("changed queued task")
    queue = FakeChildren(manifest)
    with pytest.raises(ValueError, match="snapshot changed"):
        m.run_queue(root, manifest, popen=queue.popen, sleep=queue.sleep)
    assert queue.launched == [] and manifest["status"] == "failed"
    assert all(job["status"] == "queued" for job in manifest["jobs"])


def test_existing_root_and_oversized_allocations_are_rejected(plan):
    root, _, _, tasks, instructions = plan
    root.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        m.prepare_manifest(tasks, instructions, root, root.parent, "4g", "2", 3)
    for memory, cpus, concurrent in [("8g", "2", 3), ("4g", "3", 3), ("4g", "2", 4)]:
        with pytest.raises(ValueError):
            m.matrix_limits(memory, cpus, concurrent)
