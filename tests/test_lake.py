"""Fixed-world survey controls: no scientist client or network access."""
import copy
import importlib.util
import json
from pathlib import Path
import sys

import pytest
from click.testing import CliRunner

# The deliverable intentionally stays operator-only at repo root, outside runtime src/.
spec = importlib.util.spec_from_file_location("lake", Path(__file__).parents[1] / "lake.py")
lake = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = lake
spec.loader.exec_module(lake)


@pytest.fixture(scope="module")
def baseline():
    return lake.bundle()


def test_fixed_census_stratum_size_totals_and_geometry():
    world = lake.truth()
    assert world["totals"] == {"perch": 2400, "roach": 1800, "ruffe": 600, "pike": 60,
                               "burbot": 40, "bleak": 0, "vendace": 0, "common_bream": 0}
    assert world["total_fish"] == 4900
    assert world["area_m2"] == 60000 and world["volume_m3"] == 210600
    assert world["mean_depth_m"] == 3.51
    assert {h: sum(sum(v[h].values()) for v in world["populations"].values()) for h in lake.HABITATS} == {
        "littoral": 2199, "open": 1920, "deep": 781}
    assert sum(v[h]["small_le8cm"] for v in world["populations"].values() for h in lake.HABITATS) == 2410
    assert all(isinstance(n, int) and n >= 0 for pop in world["populations"].values() for sizes in pop.values() for n in sizes.values())


def test_doc_tables_are_generated_from_authoritative_spec():
    doc = (Path(__file__).parents[1] / "LAKE.md").read_text()
    actual = doc.split("<!-- BEGIN GENERATED OPERATOR TABLES -->\n")[1].split("\n<!-- END GENERATED OPERATOR TABLES -->")[0]
    assert actual == lake.operator_tables()


def test_reproducibility_method_order_and_stream_independence(baseline):
    assert lake.encoded(lake.bundle()) == lake.encoded(baseline)
    for method in reversed(lake.METHODS):
        assert lake.bundle(method)["observations"][method] == baseline["observations"][method]
    extended = lake.bundle(sites=4, passes=3)
    for method in ("sonar", "camera"):
        old = baseline["observations"][method]["rows"]
        kept = [r for r in extended["observations"][method]["rows"] if r["station"] <= 3 and r["pass"] <= 2]
        assert old == kept
    reduced = lake.bundle(habitats=["deep", "littoral"])
    for method in ("sonar", "camera", "edna", "habitat"):
        old = baseline["observations"][method]["rows"]
        assert reduced["observations"][method]["rows"] == [r for r in old if r.get("habitat") != "open"]


def test_new_survey_id_changes_observations_only(baseline):
    before = lake.encoded(lake.truth())
    other = lake.bundle(survey_id="independent-observation")
    for method in lake.METHODS:
        assert other["observations"][method] != baseline["observations"][method]
    assert lake.encoded(lake.truth()) == before


FORBIDDEN = {"truth", "populations", "total_fish", "totals", "seed", "world_seed", "_STREAM_KEY", "observation_constants",
             "shedding", "amplification", "sonar_detection", "camera_habitat", "camera_taxon_visibility", "latent_fish_id",
             "source_sha256", "truth_sha256", "operator_only", "posterior", "population_estimate"}


def hidden_keys(value):
    if isinstance(value, dict):
        return (set(value) & FORBIDDEN) | set().union(*(hidden_keys(v) for v in value.values()), set())
    if isinstance(value, list):
        return set().union(*(hidden_keys(v) for v in value), set())
    return set()


def test_exports_exclude_truth_latent_parameters_source_and_seeds_with_negative_control(baseline):
    assert hidden_keys(baseline) == set()
    text = lake.encoded(baseline).decode()
    assert text.count("SYNTHETIC") == 1
    assert lake._STREAM_KEY not in text
    assert "/home/" not in text and "lake.py" not in text
    planted = copy.deepcopy(baseline)
    planted["observations"]["edna"]["leak"] = lake.truth()
    assert {"total_fish", "observation_constants", "populations"} <= hidden_keys(planted)


def test_reference_panel_keeps_absent_taxa_and_zeros(baseline):
    assert {r["taxon"] for r in baseline["metadata"]["reference_panel"]} == set(lake.FISH)
    assert "presence" not in lake.encoded(baseline["metadata"]["reference_panel"]).decode()
    for row in baseline["observations"]["camera"]["rows"]:
        assert set(row["counts"]) == set(lake.FISH)
    for row in baseline["observations"]["edna"]["rows"]:
        assert set(row["reads"]) == set(lake.FISH)
        assert sum(row["reads"].values()) + row["unassigned_reads"] == row["library_reads"]
        assert all(n >= 0 and isinstance(n, int) for n in row["reads"].values())


def test_edna_field_pcr_blanks_and_calibration_units(baseline):
    rows = baseline["observations"]["edna"]["rows"]
    lake_rows = [r for r in rows if r["sample_type"] == "lake_water"]
    assert len(lake_rows) == 3 * 3 * 2 * 3
    assert len([r for r in rows if r["sample_type"] == "field_blank"]) == 6
    assert len([r for r in rows if r["sample_type"] == "reagent_blank"]) == 6
    assert all("habitat" not in r for r in rows if r["sample_type"] != "lake_water")
    for h in lake.HABITATS:
        site = [r for r in lake_rows if r["habitat"] == h and r["station"] == 1]
        assert {(r["field_replicate"], r["pcr_replicate"]) for r in site} == {(f, p) for f in (1, 2) for p in (1, 2, 3)}
    calibration = baseline["observations"]["calibration"]["rows"]
    for instrument in ("edna", "camera"):
        assert {r["taxon"] for r in calibration if r["instrument"] == instrument} == set(lake.FISH)
    for row in calibration:
        assert "fixture" in row and "sample_type" not in row
        for count, n in (("positive_reactions", "trials"), ("correct_detections", "known_encounters"),
                         ("detected_targets", "known_targets"), ("false_positive_trials", "trials")):
            if count in row:
                assert 0 <= row[count] <= row[n]
    assert len([r for r in calibration if r["instrument"] == "edna_mock"]) == 4
    # An equimolar reference mixture must not be mistaken for equal read fractions.
    mock = next(r for r in calibration if r["instrument"] == "edna_mock")
    assert len(set(mock["reads"].values())) > 4


def test_encounter_coverage_counts_and_missing_habitats(baseline):
    assert "repeat" in baseline["observations"]["camera"]["design"]["repeat_warning"].lower() or "same fish" in baseline["observations"]["camera"]["design"]["repeat_warning"]
    mapping = {r["habitat"]: r["area_estimate_m2"] for r in baseline["observations"]["habitat"]["areas"]}
    for method in ("sonar", "camera"):
        for row in baseline["observations"][method]["rows"]:
            assert row["stratum_area_estimate_m2"] == mapping[row["habitat"]]
            assert 0 < row["nominal_fraction_of_estimated_stratum"] < 1
            assert row["sampled_footprint_m2"] > 0 and row["pass"] in (1, 2)
            if method == "sonar":
                assert set(row["target_counts"]) == set(lake.SIZES)
                assert not (set(row) & set(lake.FISH))
                assert all(isinstance(n, int) and n >= 0 for n in row["target_counts"].values())
            else:
                assert all(isinstance(n, int) and n >= 0 for sizes in row["counts"].values() for n in sizes.values())
    reduced = lake.bundle("sonar", habitats=["littoral"])
    assert reduced["metadata"]["selected_habitats"] == ["littoral"]
    assert all(r["habitat"] == "littoral" for r in reduced["observations"]["sonar"]["rows"])


def test_repeated_passes_are_nondestructive_not_cumulative():
    before = lake.encoded(lake.truth())
    one = lake.bundle("camera", passes=1)
    four = lake.bundle("camera", passes=4)
    assert one["observations"]["camera"]["rows"] == [r for r in four["observations"]["camera"]["rows"] if r["pass"] == 1]
    lake.bundle("sonar", sites=6, passes=4)
    assert lake.encoded(lake.truth()) == before
    assert not any("unique" in k for r in four["observations"]["camera"]["rows"] for k in r)


def invoke_survey(tmp_path, output="export", root="operator"):
    return CliRunner().invoke(lake.main, ["survey", "--method", "all", "--survey-id", "baseline",
        "--out", str(tmp_path / output), "--operator-root", str(tmp_path / root)])


def test_cli_exports_receipts_and_same_bundle_for_both_researchers(tmp_path):
    assert invoke_survey(tmp_path).exit_code == 0
    assert sorted(p.name for p in (tmp_path / "export").iterdir()) == ["observations.json"]
    receipt_dir = next((tmp_path / "operator").iterdir())
    receipt = json.loads((receipt_dir / "receipt.json").read_bytes())
    payload = (tmp_path / "export/observations.json").read_bytes()
    assert receipt["outputs"]["observations.json"] == lake.sha(payload)
    assert receipt["source_sha256"] == lake.sha((receipt_dir / "lake.py").read_bytes())
    assert receipt["options_sha256"] == lake.sha(lake.encoded(receipt["options"]))
    assert receipt["truth_sha256"] == lake.sha((receipt_dir / "truth.json").read_bytes())
    assert invoke_survey(tmp_path, "second-export").exit_code == 0
    assert (tmp_path / "second-export/observations.json").read_bytes() == payload
    # Same bytes can be copied to two independent request responses without customization.
    assert lake.encoded(json.loads(payload)) == payload
    before = sorted((tmp_path / "operator").iterdir())
    result = invoke_survey(tmp_path)
    assert result.exit_code != 0 and "already exists" in result.output
    assert (tmp_path / "export/observations.json").read_bytes() == payload
    assert sorted((tmp_path / "operator").iterdir()) == before


@pytest.mark.parametrize("output,operator", [("x", "x/hidden"), ("x/export", "x"), ("x", "x")])
def test_receipts_cannot_be_exported_accidentally(tmp_path, output, operator):
    result = invoke_survey(tmp_path, output, operator)
    assert result.exit_code != 0 and "non-nested" in result.output
    assert not (tmp_path / "x").exists()


@pytest.mark.parametrize("args", [["--method", "capture"], ["--sites", "0"], ["--passes", "9"],
                                  ["--habitat", "unknown"], ["--survey-id", "../invalid"]])
def test_cli_rejects_invalid_options_before_export(tmp_path, args):
    result = CliRunner().invoke(lake.main, ["survey", "--out", str(tmp_path / "export"),
        "--operator-root", str(tmp_path / "operator"), *args])
    assert result.exit_code != 0 and not (tmp_path / "export").exists()


def test_count_sampler_negative_and_full_coverage_positive_controls(monkeypatch):
    # In a complete, perfect acoustic census, each size-bin count must equal truth.
    monkeypatch.setattr(lake, "poisson", lambda *a: 0)
    monkeypatch.setattr(lake, "SONAR_DETECTION", {h: (1, 1) for h in lake.HABITATS})
    spec = copy.deepcopy(lake.HABITATS)
    for h in spec:
        spec[h]["sonar_length_m"], spec[h]["sonar_width_m"] = spec[h]["area_m2"], 1
    monkeypatch.setattr(lake, "HABITATS", spec)
    rows = lake.count_data("sonar", "positive-control", list(spec), 1, 1)["rows"]
    for i, row in enumerate(rows):
        assert row["target_counts"] == {size: sum(cells[i][b] for cells in lake.FISH.values()) for b, size in enumerate(lake.SIZES)}
    monkeypatch.setattr(lake, "FISH", {s: ((0, 0), (0, 0), (0, 0)) for s in lake.FISH})
    for method in ("sonar", "camera"):
        rows = lake.count_data(method, "empty-control", list(spec), 1, 1)["rows"]
        for row in rows:
            if method == "sonar":
                assert set(row["target_counts"].values()) == {0}
            else:
                assert {n for counts in row["counts"].values() for n in counts.values()} == {0}


def test_camera_false_positive_calibration_matches_taxon_size_unit(baseline):
    negatives = [r for r in baseline["observations"]["calibration"]["rows"]
                 if r["instrument"] == "camera" and r["fixture"] == "fish-free reference videos"]
    assert {(r["taxon"], r["size_bin"]) for r in negatives} == {(s, size) for s in lake.FISH for size in lake.SIZES}
