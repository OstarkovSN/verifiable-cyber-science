#!/usr/bin/env python3
"""OPERATOR ONLY: fixed fictional lake, observation simulator and hidden receipts.

Never mount this source, LAKE.md or operator receipts into scientist containers.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import random
import re
import sys

import click

VERSION = "vcs-lake-1"
# Chosen once, not a CLI option. Used only for observation streams, never populations.
_STREAM_KEY = "VCS-LK-001-observation-streams-20261117"
HABITATS = {
    "littoral": {"area_m2": 18000, "mean_depth_m": 1.2, "sample_depth_m": 0.5,
                 "sonar_length_m": 100, "sonar_width_m": 2, "camera_area_m2": 120},
    "open": {"area_m2": 30000, "mean_depth_m": 3.5, "sample_depth_m": 1.5,
             "sonar_length_m": 150, "sonar_width_m": 6, "camera_area_m2": 180},
    "deep": {"area_m2": 12000, "mean_depth_m": 7.0, "sample_depth_m": 5.0,
             "sonar_length_m": 100, "sonar_width_m": 6, "camera_area_m2": 120},
}
# Rows are (small <=8 cm, large >8 cm), in littoral/open/deep order.
FISH = {
    "perch": ((700, 400), (400, 600), (100, 200)),
    "roach": ((550, 350), (300, 450), (50, 100)),
    "ruffe": ((80, 70), (70, 80), (150, 150)),
    "pike": ((0, 45), (0, 12), (0, 3)),
    "burbot": ((1, 3), (2, 6), (7, 21)),
    "bleak": ((0, 0), (0, 0), (0, 0)),
    "vendace": ((0, 0), (0, 0), (0, 0)),
    "common_bream": ((0, 0), (0, 0), (0, 0)),
}
SCIENTIFIC = ("Perca fluviatilis", "Rutilus rutilus", "Gymnocephalus cernua", "Esox lucius",
              "Lota lota", "Alburnus alburnus", "Coregonus albula", "Abramis brama")
PANEL = [{"taxon": taxon, "scientific_name": name} for taxon, name in zip(FISH, SCIENTIFIC)]
SIZES = ("small_le8cm", "large_gt8cm")
ENVIRONMENT = {"surface_temperature_C": 18, "deep_temperature_C": 9, "secchi_m": 1.4,
               "pH": 6.5, "total_P_ug_L": 25, "DOC_mg_L": 8,
               "surface_oxygen_mg_L": 8.5, "deep_oxygen_mg_L": 4.5}
# Designer-selected observation constants, deliberately absent from exports.
SHEDDING = dict(zip(FISH, (1.0, 0.65, 0.32, 4.2, 0.5, 0.8, 0.9, 1.3)))
AMPLIFICATION = dict(zip(FISH, (1.1, 2.2, 0.45, 0.75, 0.55, 1.5, 0.7, 1.0)))
VISIBILITY = dict(zip(FISH, (0.8, 0.7, 0.3, 0.55, 0.2, 0.75, 0.6, 0.65)))
SONAR_DETECTION = {"littoral": (0.10, 0.42), "open": (0.30, 0.84), "deep": (0.16, 0.60)}
CAMERA_HABITAT = {"littoral": 0.72, "open": 0.52, "deep": 0.30}
METHODS = ("habitat", "edna", "sonar", "camera", "calibration")


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rng(survey_id, *labels):
    material = json.dumps([VERSION, _STREAM_KEY, survey_id, *labels], separators=(",", ":"))
    return random.Random(int(sha(material.encode()), 16))


def binomial(r, n, probability):
    # Exact Bernoulli sum works on Python 3.11; this fixed world is small.
    return sum(r.random() < probability for _ in range(n))


def poisson(r, mean):
    # Sum small independent Poisson draws to avoid exp underflow for larger means.
    result = 0
    while mean > 0:
        part = min(20, mean)
        product, k, limit = 1.0, 0, math.exp(-part)
        while product > limit:
            product *= r.random()
            k += 1
        result += k - 1
        mean -= part
    return result


def truth():
    populations = {s: {h: dict(zip(SIZES, cells[i])) for i, h in enumerate(HABITATS)} for s, cells in FISH.items()}
    area = sum(v["area_m2"] for v in HABITATS.values())
    volume = sum(v["area_m2"] * v["mean_depth_m"] for v in HABITATS.values())
    return {"operator_only": True, "world": "VCS-LK-001", "version": VERSION,
            "region": "fictional unnamed lake near Lieksa, North Karelia, eastern Finland; no real coordinates",
            "window": "two days in late August; closed census including small juveniles",
            "bounding_box_m": [300, 250], "max_depth_m": 9, "area_m2": area,
            "volume_m3": volume, "mean_depth_m": volume / area, "habitats": copy.deepcopy(HABITATS),
            "environment": dict(ENVIRONMENT), "populations": populations,
            "totals": {s: sum(sum(cell) for cell in cells) for s, cells in FISH.items()},
            "total_fish": sum(sum(sum(cell) for cell in cells) for cells in FISH.values()),
            "observation_constants": {"shedding": SHEDDING, "amplification": AMPLIFICATION,
                                      "camera_taxon_visibility": VISIBILITY, "camera_habitat": CAMERA_HABITAT,
                                      "sonar_detection": SONAR_DETECTION}}


def operator_tables():
    """Authoritative Markdown tables used verbatim in LAKE.md and its drift test."""
    world = truth()
    lines = ["| Habitat | Footprint (ha) | Mean depth (m) | Volume (m³) |",
             "|---|---:|---:|---:|"]
    for h, spec in HABITATS.items():
        lines.append(f"| {h} | {spec['area_m2']/10000:g} | {spec['mean_depth_m']:g} | {spec['area_m2']*spec['mean_depth_m']:g} |")
    lines += [f"| **Total** | **{world['area_m2']/10000:g}** | **{world['mean_depth_m']:g}** | **{world['volume_m3']:g}** |", "",
              "| Taxon | Littoral small / large | Open small / large | Deep small / large | Total |", "|---|---:|---:|---:|---:|"]
    for taxon, cells in FISH.items():
        rendered = " | ".join(f"{small} / {large}" for small, large in cells)
        lines.append(f"| {taxon} | {rendered} | {world['totals'][taxon]} |")
    lines += [f"| **All fish** | | | | **{world['total_fish']}** |", "", "| Environmental quantity | Designer value |", "|---|---:|"]
    lines += [f"| {name} | {value:g} |" for name, value in ENVIRONMENT.items()]
    return "\n".join(lines)


def area_measurement(survey_id, habitat):
    return round(HABITATS[habitat]["area_m2"] * rng(survey_id, "habitat", habitat, "area").lognormvariate(-0.035**2 / 2, 0.035), 2)


def habitat_data(survey_id, habitats, sites, passes):
    rows = []
    for h in habitats:
        for site in range(1, sites + 1):
            r = rng(survey_id, "habitat", h, site)
            row = {"habitat": h, "station": site, "depth_reading_m": round(max(0.1, r.gauss(HABITATS[h]["mean_depth_m"], 0.25)), 3)}
            for name, value in ENVIRONMENT.items():
                if name.startswith(("surface_", "deep_")):
                    continue
                row[name] = round(max(0.01, r.gauss(value, 0.03 * value)), 3)
            row["water_temperature_C"] = round(r.gauss(9 if h == "deep" else 18, 0.3), 3)
            row["oxygen_mg_L"] = round(r.gauss(4.5 if h == "deep" else 8.5, 0.2), 3)
            row["sampling_depth_m"] = HABITATS[h]["sample_depth_m"]
            if h == "littoral":
                row["secchi_m"] = None
                row["secchi_status"] = "not measured in shallow stratum"
            else:
                row["secchi_status"] = "measured"
            rows.append(row)
    return {"design": {"selection": "stratified conceptual stations; depth soundings and water grabs; no capture",
                       "area": "one noisy mapping estimate per selected stratum; station soundings have local/instrument variation",
                       "environment": "station water chemistry and profiler readings at reported depths; Secchi omitted at shallow stations",
                       "errors": "mapping and instrument/grab errors; see independent instrument fixtures in calibration",
                       "coverage": "only listed strata; no inference for omitted strata is supplied"},
            "areas": [{"habitat": h, "area_estimate_m2": area_measurement(survey_id, h)} for h in habitats], "rows": rows}


def sequence_library(survey_id, key, signal):
    r = rng(survey_id, "edna", *key)
    weights = []
    for s in FISH:
        concentration = signal[s]
        amplified = concentration * AMPLIFICATION[s] * r.lognormvariate(-0.045, 0.30)
        if r.random() < math.exp(-concentration * 0.65):
            amplified = 0.0  # Low template dropout, including true zeros.
        if r.random() < 0.003:
            amplified += r.uniform(0.3, 2.0)  # Reagent contamination, any panel taxon.
        weights.append(amplified)
    library_reads = r.randint(1800, 2600)
    labels = [*FISH, "unassigned"]
    reads = dict.fromkeys(labels, 0)
    for label in r.choices(labels, weights=[*weights, 10.0], k=library_reads):
        reads[label] += 1
    return {"library_reads": library_reads, "reads": {s: reads[s] for s in FISH}, "unassigned_reads": reads["unassigned"]}


def edna_data(survey_id, habitats, sites, passes):
    rows = []
    volume = truth()["volume_m3"]
    for h in habitats:
        hi = list(HABITATS).index(h)
        for site in range(1, sites + 1):
            for field in (1, 2):
                signal = {}
                for s, cells in FISH.items():
                    r = rng(survey_id, "edna-field", h, site, field, s)
                    local = sum(cells[hi]) / (HABITATS[h]["area_m2"] * HABITATS[h]["mean_depth_m"])
                    mixed = sum(map(sum, cells)) / volume
                    # Fixed site contrast + shared extraction noise across nested PCRs.
                    intensity = (0.85 * local + 0.15 * mixed) * 1000 * SHEDDING[s]
                    intensity *= (0.6 + 0.2 * ((site - 1) % 4)) * r.lognormvariate(-0.125, 0.5)
                    signal[s] = 0 if r.random() < 0.06 else intensity
                    if r.random() < 0.012:
                        signal[s] += r.uniform(0.3, 2.0)
                for pcr in (1, 2, 3):
                    rows.append({"sample_type": "lake_water", "habitat": h, "station": site, "field_replicate": field,
                                 "pcr_replicate": pcr, "water_volume_L": 1, "sampling_depth_m": HABITATS[h]["sample_depth_m"],
                                 **sequence_library(survey_id, (h, site, field, pcr), signal)})
    for blank in ("field_blank", "reagent_blank"):
        for replicate in (1, 2):
            signal = {s: 0.0 for s in FISH}
            if blank == "field_blank":
                for s in FISH:
                    r = rng(survey_id, "blank-field", replicate, s)
                    if r.random() < 0.012:
                        signal[s] = r.uniform(0.3, 2.0)
            for pcr in (1, 2, 3):
                rows.append({"sample_type": blank, "blank_replicate": replicate, "pcr_replicate": pcr,
                             "water_volume_L": 1 if blank == "field_blank" else 0,
                             **sequence_library(survey_id, (blank, replicate, pcr), signal)})
    return {"design": {"assay": "virtual freshwater 12S metabarcoding panel v1; no real laboratory assay is claimed",
                       "replication": "two separately extracted 1 L grabs per station; three nested PCR libraries per grab",
                       "selection": "stratified conceptual stations; same station labels across methods denote co-location",
                       "filter": "virtual 0.45 um filter; no fish contact",
                       "controls": "two field blanks and two reagent blanks, each in triplicate PCR; unassigned includes background reads",
                       "errors": "taxon-dependent shedding/amplification, transport, local heterogeneity, shared extraction loss, PCR dropout and rare contamination",
                       "interpretation": "read fractions are not individual abundance fractions; negative reads do not establish absence; blanks are not lake stations",
                       "coverage": "water at reported depths and selected habitats; transport may carry DNA between strata"}, "rows": rows}


def count_data(method, survey_id, habitats, sites, passes):
    rows = []
    for h in habitats:
        hi, spec = list(HABITATS).index(h), HABITATS[h]
        footprint = spec["sonar_length_m"] * spec["sonar_width_m"] if method == "sonar" else spec["camera_area_m2"]
        for site in range(1, sites + 1):
            for visit in range(1, passes + 1):
                row = {"habitat": h, "station": site, "pass": visit, "sampled_footprint_m2": footprint,
                       "stratum_area_estimate_m2": area_measurement(survey_id, h),
                       "nominal_fraction_of_estimated_stratum": round(footprint / area_measurement(survey_id, h), 6)}
                if method == "sonar":
                    counts = dict.fromkeys(SIZES, 0)
                    for s, cells in FISH.items():
                        for b, size in enumerate(SIZES):
                            r = rng(survey_id, method, h, site, visit, s, size)
                            probability = footprint / spec["area_m2"] * SONAR_DETECTION[h][b]
                            counts[size] += binomial(r, cells[hi][b], probability)
                    for size in SIZES:
                        counts[size] += poisson(rng(survey_id, method, h, site, visit, "clutter", size), 0.4)
                    row.update(length_m=spec["sonar_length_m"], nominal_swath_m=spec["sonar_width_m"], target_counts=counts)
                else:
                    counts = {}
                    for s, cells in FISH.items():
                        counts[s] = {}
                        for b, size in enumerate(SIZES):
                            r = rng(survey_id, method, h, site, visit, s, size)
                            probability = footprint / spec["area_m2"] * CAMERA_HABITAT[h] * VISIBILITY[s] * (0.55 if b == 0 else 1)
                            counts[s][size] = binomial(r, cells[hi][b], probability) + poisson(r, 0.015)
                    row.update(duration_min=10, illumination="standardized low-light camera", counts=counts)
                rows.append(row)
    return {"design": {"selection": "randomized conceptual equal-footprint placements within each selected stratum; locations exchangeable across passes",
                       "count_unit": "target encounters within one pass; no persistent individual identification",
                       "coverage": "footprints are nominal bottom-projected areas; fractions use noisy mapping estimates; repeated passes overlap and cannot be summed as unique coverage",
                       "errors": ("size/habitat detection, shore and near-bottom blind zones; occasional non-fish targets; size classification assumed exact within two coarse bins" if method == "sonar" else
                                  "taxon/size/habitat visibility and availability, occasional false labels; no lake fish captured"),
                       "blind_zones": "shore/vegetation and bottom availability are folded into detection; nominal footprint is not perfectly observable habitat",
                       "repeat_warning": "counts may re-detect the same fish across stations/passes/methods; do not add as distinct fish",
                       "calibration_transfer": "fixtures characterize reference conditions, not exact field detectability or unseen habitat availability"}, "rows": rows}


def calibration_data(survey_id, habitats, sites, passes):
    rows = []
    for s in FISH:
        for copies in (0, 2, 20):
            r = rng(survey_id, "calibration", "edna", s, copies)
            chance = 0.004 if copies == 0 else 1 - math.exp(-copies * 0.65)
            rows.append({"instrument": "edna", "fixture": "synthetic single-taxon DNA standard; non-lake material",
                         "taxon": s, "known_copies_per_reaction": copies, "trials": 80,
                         "positive_reactions": binomial(r, 80, chance)})
        for b, size in enumerate(SIZES):
            r = rng(survey_id, "calibration", "camera", s, size)
            rows.append({"instrument": "camera", "fixture": "independent labelled reference video encounters; no lake fish",
                         "taxon": s, "size_bin": size, "known_encounters": 80,
                         "correct_detections": binomial(r, 80, VISIBILITY[s] * (0.55 if b == 0 else 1))})
        for size in SIZES:
            rows.append({"instrument": "camera", "fixture": "fish-free reference videos", "taxon": s,
                         "size_bin": size, "trials": 100,
                         "false_positive_trials": binomial(rng(survey_id, "calibration", "camera-negative", s, size), 100, 1 - math.exp(-0.015))})
    for h in habitats:
        for b, size in enumerate(SIZES):
            rows.append({"instrument": "sonar", "fixture": "known acoustic replay targets in habitat-like test conditions",
                         "habitat": h, "size_bin": size, "known_targets": 100,
                         "detected_targets": binomial(rng(survey_id, "calibration", "sonar", h, size), 100, min(0.98, SONAR_DETECTION[h][b] * 1.1))})
        rows.append({"instrument": "sonar", "fixture": "fish-free acoustic replay strips", "habitat": h,
                     "trials": 100, "false_positive_trials": binomial(rng(survey_id, "calibration", "sonar-negative", h), 100, 1 - math.exp(-0.8))})
    for replicate in range(1, 13):
        r = rng(survey_id, "calibration", "mapping", replicate)
        rows.append({"instrument": "mapping", "fixture": "independent known-area reference polygon",
                     "replicate": replicate, "known_area_m2": 10000, "observed_area_m2": round(10000 * r.lognormvariate(-0.035**2/2, 0.035), 2),
                     "known_depth_m": 3, "observed_depth_m": round(r.gauss(3, 0.12), 3)})
    mock_signal = {s: 20.0 for s in FISH}
    for replicate in range(1, 5):
        rows.append({"instrument": "edna_mock", "fixture": "equimolar eight-taxon synthetic DNA; non-lake material",
                     "replicate": replicate, "known_copies_each_taxon": 20,
                     **sequence_library(survey_id, ("mock", replicate), mock_signal)})
    return {"design": {"independence": "all fixtures and trials are independent of lake field samples and use separate random streams",
                       "panel": "all eight reference taxa tested regardless of lake occurrence",
                       "transfer": "PCR standards do not calibrate natural shedding/transport; camera fixtures omit field visibility/availability; acoustic fixtures differ from lake conditions",
                       "control_unit": "positive or false-positive trials, not known true detection probabilities; finite trials have sampling uncertainty",
                       "no_capture": "DNA standards, labelled video/acoustic replays and instrument fixtures only; no lake fish handled"}, "rows": rows}


GENERATORS = {"habitat": habitat_data, "edna": edna_data, "sonar": lambda *a: count_data("sonar", *a),
              "camera": lambda *a: count_data("camera", *a), "calibration": calibration_data}


def bundle(method="all", survey_id="baseline", habitats=None, sites=3, passes=2):
    if method not in (*METHODS, "all"):
        raise ValueError("unsupported non-capture method")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", survey_id):
        raise ValueError("survey-id must be 1–80 simple letters, digits, dots, underscores or hyphens")
    selected = set(habitats or HABITATS)
    if not selected or not selected <= set(HABITATS) or not 1 <= sites <= 6 or not 1 <= passes <= 4:
        raise ValueError("invalid habitat selection or bounded sampling effort")
    habitats = [h for h in HABITATS if h in selected]
    methods = METHODS if method == "all" else (method,)
    return {"metadata": {"data_origin": "SYNTHETIC", "world_label": "VCS-LK-001", "schema": VERSION,
                         "survey_id": survey_id, "window": "same fixed two-day late-August census",
                         "target": "all living fish, including small juveniles; reference panel is not a presence list",
                         "reference_panel": copy.deepcopy(PANEL), "size_bins": list(SIZES),
                         "selected_habitats": habitats, "stations_per_habitat": sites, "passes": passes,
                         "population_handling": "no capture, removal, births, deaths or population reset; new survey IDs vary observations only",
                         "use": "identical bundle may be given to independent researchers; no inference family or population estimate supplied"},
            "observations": {name: GENERATORS[name](survey_id, habitats, sites, passes) for name in methods}}


def write_export(out, operator_root, data, options):
    out, operator_root = Path(out).resolve(), Path(operator_root).resolve()
    # Neither tree can contain the other; copying a whole export can never include receipts.
    if out == operator_root or out in operator_root.parents or operator_root in out.parents:
        raise ValueError("operator-root and export directory must be separate, non-nested trees")
    if out.exists():
        raise ValueError("output directory already exists; use a new directory")
    payload = encoded(data)
    source = Path(__file__).read_bytes()
    receipt_id = sha(encoded({**options, "export_path": str(out)}) + payload + source)[:24]
    operator_root.mkdir(parents=True, exist_ok=True)
    receipt_dir = operator_root / receipt_id
    receipt_dir.mkdir(exist_ok=False)
    # Source + hidden spec are operator-only; never put their hashes into observations.
    (receipt_dir / "lake.py").write_bytes(source)
    (receipt_dir / "truth.json").write_bytes(encoded(truth()))
    receipt = {"operator_only": True, "options": options, "python": sys.version,
               "source_sha256": sha(source), "options_sha256": sha(encoded(options)), "truth_sha256": sha(encoded(truth())),
               "outputs": {"observations.json": sha(payload)}, "export_path": str(out)}
    out.mkdir(parents=True, exist_ok=False)
    (out / "observations.json").write_bytes(payload)
    (receipt_dir / "receipt.json").write_bytes(encoded(receipt))
    return receipt_dir


@click.group()
def main():
    """Operator-only hidden lake simulator. Export observations separately from truth."""


@main.command("truth")
@click.option("--format", "output_format", type=click.Choice(["json", "markdown"]), default="json")
def truth_command(output_format):
    """Print the designer-selected hidden world. Never provide this to scientists."""
    click.echo(operator_tables() if output_format == "markdown" else encoded(truth()).decode(), nl=output_format == "markdown")


@main.command("survey")
@click.option("--method", type=click.Choice([*METHODS, "all"]), default="all", show_default=True)
@click.option("--survey-id", default="baseline", show_default=True)
@click.option("--habitat", multiple=True, type=click.Choice(list(HABITATS)), help="Repeat to select strata; default all")
@click.option("--sites", default=3, type=click.IntRange(1, 6), show_default=True)
@click.option("--passes", default=2, type=click.IntRange(1, 4), show_default=True, help="Repeated sonar/camera passes; no removal")
@click.option("--out", required=True, type=click.Path(path_type=Path))
@click.option("--operator-root", required=True, type=click.Path(path_type=Path), help="Separate operator-only receipt/source directory")
def survey_command(method, survey_id, habitat, sites, passes, out, operator_root):
    """Generate observations only; this command never contacts scientist clients."""
    try:
        data = bundle(method, survey_id, habitat, sites, passes)
        options = {"method": method, "survey_id": survey_id, "habitats": data["metadata"]["selected_habitats"],
                   "sites": sites, "passes": passes}
        receipt = write_export(out, operator_root, data, options)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Observations: {out / 'observations.json'}\nOperator receipt: {receipt / 'receipt.json'}")


if __name__ == "__main__":
    main()
