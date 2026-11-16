"""Extraction identity and kernel failure controls; never invokes a scientist."""
import json
import os
from pathlib import Path
import subprocess

from click.testing import CliRunner
import pytest

import vcs_extract as extract


@pytest.mark.parametrize("exit_code", [-1, -9, -10, -15, 1, 137])
def test_every_kernel_failure_is_nonzero(tmp_path, monkeypatch, exit_code):
    calls = iter([subprocess.CompletedProcess([], 0, "", ""),
                  subprocess.CompletedProcess([], exit_code, "", "kernel failed")])
    monkeypatch.setattr(extract.subprocess, "run", lambda *args, **kwargs: next(calls))
    status, log = extract.run_lean(tmp_path / "control.lean")
    assert status != 0
    assert f"leanchecker exit {exit_code}" in log


def test_identity_records_reject_duplicates_and_do_not_invent_missing_values():
    assert extract.expression_identities("", "VAS_ORIGINAL_IDENTITY") == {}
    with pytest.raises(ValueError, match="duplicate"):
        extract.expression_identities(
            "VAS_ORIGINAL_IDENTITY t : expression VAS_END\n" * 2,
            "VAS_ORIGINAL_IDENTITY")


@pytest.fixture
def real_lean(monkeypatch):
    root = os.environ.get("VCS_TEST_LIBRARY_ROOT")
    if not root:
        pytest.skip("set VCS_TEST_LIBRARY_ROOT for real Lean identity controls")
    # Only the already installed, pinned library cache is used. No model calls.
    monkeypatch.setattr(extract, "ROOT", Path(root))


@pytest.mark.parametrize("change_type", [False, True])
def test_exact_identity_not_lossy_pretty_printing(real_lean, tmp_path, monkeypatch, change_type):
    source = tmp_path / "Model.lean"
    source.write_text("import Mathlib.Data.Int.Basic\n"
                      "theorem result : (1 : Nat) = 1 := rfl\n")
    original_run = extract.run_lean
    logs = []

    def checking_run(path):
        if change_type and path.name.endswith(".check.lean"):
            # Both propositions pretty-print `1 = 1`. Type identity must still
            # detect a changed extraction, even though each compiles alone.
            text = path.read_text().replace("(1 : Nat)", "(1 : Int)")
            path.write_text(text)
        result = original_run(path)
        logs.append(result[1])
        return result

    monkeypatch.setattr(extract, "run_lean", checking_run)
    result = CliRunner().invoke(extract.main, [str(source), "--theorem", "result",
                                              "--out", str(tmp_path / "extracted")])
    report = json.loads((tmp_path / "extracted.json").read_text())
    assert report["compiles_alone"], result.output
    assert "VAS_CONCLUSION result : 1 = 1 VAS_END" in logs[0]
    assert "VAS_EXTRACTED conclusion_result : 1 = 1 VAS_END" in logs[1]
    assert report["ok"] is (not change_type)
    assert report["faithful"]["result"] is (not change_type)
    assert result.exit_code == (1 if change_type else 0)
    assert report["identity_method"] == "kernel-expression-repr-v1"


def test_scoped_open_cannot_silently_change_conclusion(real_lean, tmp_path):
    source = tmp_path / "Model.lean"
    source.write_text("import Mathlib.Data.Int.Basic\n"
                      "structure A where\n  payload : Nat\n"
                      "structure B where\n  payload : Int\n"
                      "open A in\n"
                      "theorem model_result : mk 0 = mk 0 := rfl\n"
                      "open B\nopen B\n"
                      "theorem ensure_B : (B.mk 0).payload = 0 := rfl\n")
    result = CliRunner().invoke(extract.main, [str(source), "--theorem", "model_result",
                                              "--theorem", "ensure_B",
                                              "--out", str(tmp_path / "extracted")])
    report = json.loads((tmp_path / "extracted.json").read_text())
    assert report["compiles_alone"], result.output
    assert not report["ok"] and not report["faithful"]["model_result"]
    assert report["faithful"]["ensure_B"]
    assert result.exit_code == 1


@pytest.mark.parametrize("change_type", [False, True])
def test_same_named_alias_cannot_hide_changed_definition(real_lean, tmp_path, monkeypatch, change_type):
    source = tmp_path / "Model.lean"
    source.write_text("import Mathlib.Data.Int.Basic\n"
                      "def claim : Prop := (1 : Nat) = 1\n"
                      "theorem result : claim := rfl\n")
    original_run = extract.run_lean

    def checking_run(path):
        if change_type and path.name.endswith(".check.lean"):
            path.write_text(path.read_text().replace("(1 : Nat)", "(1 : Int)"))
        return original_run(path)

    monkeypatch.setattr(extract, "run_lean", checking_run)
    result = CliRunner().invoke(extract.main, [str(source), "--theorem", "result",
                                              "--out", str(tmp_path / "extracted")])
    report = json.loads((tmp_path / "extracted.json").read_text())
    assert report["compiles_alone"], result.output
    # The root expression is the same constant; its dependency must also match.
    assert report["faithful"]["result"]
    assert report["dependency_faithful"]["claim"] is (not change_type)
    assert report["ok"] is (not change_type)
    assert result.exit_code == (1 if change_type else 0)
