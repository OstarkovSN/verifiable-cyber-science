"""Extract statement dependencies and conclusions; independently compile and compare."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import sys

import click

ROOT = Path(__file__).resolve().parents[1]
from vcs_lean import LEAN, LEANCHECKER, LISTER, listed  # noqa: E402

# Display text omits implicit arguments, types and sometimes whole subterms.
# Compare the complete kernel expressions instead. Binder names and metadata do
# not affect meaning; remove them so source positions and fresh binder names do
# not make an otherwise identical extraction fail. All constants, universe
# levels, implicit arguments and binder information remain in the identity.
IDENTITY = """
private partial def VAS_identityExpr : Lean.Expr → Lean.Expr
  | .mdata _ value => VAS_identityExpr value
  | .app fn arg => .app (VAS_identityExpr fn) (VAS_identityExpr arg)
  | .lam _ typ body info => .lam .anonymous (VAS_identityExpr typ) (VAS_identityExpr body) info
  | .forallE _ typ body info => .forallE .anonymous (VAS_identityExpr typ) (VAS_identityExpr body) info
  | .letE _ typ value body flag => .letE .anonymous (VAS_identityExpr typ) (VAS_identityExpr value) (VAS_identityExpr body) flag
  | .proj owner idx value => .proj owner idx (VAS_identityExpr value)
  | value => value

private def VAS_declarationIdentity (ci : Lean.ConstantInfo) : String :=
  let kind := match ci with
    | .axiomInfo _ => "axiom"
    | .defnInfo _ => "definition"
    | .thmInfo _ => "theorem"
    | .opaqueInfo _ => "opaque"
    | .quotInfo _ => "quotient"
    | .inductInfo info => s!"inductive {info.numParams} {info.numIndices} {reprStr info.ctors}"
    | .ctorInfo info => s!"constructor {info.induct} {info.cidx} {info.numParams} {info.numFields}"
    | .recInfo info => s!"recursor {info.numParams} {info.numIndices} {info.numMotives} {info.numMinors}"
  let value := match ci.value? with
    | some body => reprStr (VAS_identityExpr body)
    | none => "no value"
  s!"{kind}|levels={reprStr ci.levelParams}|type={reprStr (VAS_identityExpr ci.type)}|value={value}"
"""

REACH = """
open Lean Elab Command Meta in
run_cmd do
  let kenv := (← getEnv).checked.get
  let localSet : NameSet := kenv.constants.map₂.toList.foldl (fun s (n, _) => s.insert n) {}
  -- statements only: from each conclusion's type, through definitions' types and values
  let mut seen : NameSet := {}
  let mut todo : List Name := []
  for t in TARGETS do
    let some ci := kenv.find? t | throwError m!"no theorem {t}"
    todo := ci.type.getUsedConstants.toList ++ todo
    logInfo m!"VAS_CONCLUSION {t} : {← liftTermElabM <| ppExpr ci.type} VAS_END"
    logInfo m!"VAS_ORIGINAL_IDENTITY {t} : {reprStr (VAS_identityExpr ci.type)} VAS_END"
  while !todo.isEmpty do
    let n := todo.head!
    todo := todo.tail!
    if seen.contains n || !localSet.contains n then continue
    seen := seen.insert n
    let some ci := kenv.find? n | continue
    logInfo m!"VAS_DEPENDENCY_IDENTITY {n} : {VAS_declarationIdentity ci} VAS_END"
    let more := ci.type.getUsedConstants ++ (match ci with
      | .defnInfo v => v.value.getUsedConstants | .thmInfo v => v.value.getUsedConstants
      | .opaqueInfo v => v.value.getUsedConstants
      | .inductInfo v => v.ctors.toArray | .ctorInfo v => #[v.induct] | _ => #[])
    todo := more.toList ++ todo
    -- auxiliary constants (matchers, constructors, projections, equation lemmas) map to the nearest ancestor
    -- whose source range Lean recorded
    let mut m := n
    let mut r ← findDeclarationRanges? m
    while r.isNone && !m.isAnonymous do
      m := m.getPrefix
      r ← findDeclarationRanges? m
    match r with
    | some rg => logInfo m!"VAS_DECL {m} {rg.range.pos.line} {rg.range.endPos.line}"
    | none => logInfo m!"VAS_UNRANGED {n}"
  logInfo "VAS_REACHED"
"""

COMPARE = """
set_option format.width 100000 in
open Lean Elab Command Meta in
run_cmd do
  for n in NAMES do
    let some ci := (← getEnv).find? n | throwError m!"no {n}"
    let some v := ci.value? | throwError m!"no value {n}"
    logInfo m!"VAS_EXTRACTED {n} : {← liftTermElabM <| ppExpr v} VAS_END"
    logInfo m!"VAS_EXTRACTED_IDENTITY {n} : {reprStr (VAS_identityExpr v)} VAS_END"
  for n in DEPENDENCIES do
    let some ci := (← getEnv).find? n | throwError m!"missing extracted dependency {n}"
    logInfo m!"VAS_EXTRACTED_DEPENDENCY_IDENTITY {n} : {VAS_declarationIdentity ci} VAS_END"
"""


def run_lean(path):
    """Lean, then leanchecker on the compiled module (OT-1861): a nonzero status if either fails."""
    libs = sorted((ROOT / ".lake/packages").glob("*/.lake/build/lib/lean"))
    env = dict(os.environ, LEAN_PATH=":".join(map(str, libs)), LEAN_NUM_THREADS="1")
    with tempfile.TemporaryDirectory(prefix="vcs-olean-") as build:
        r = subprocess.run([LEAN, "-j1", f"--root={Path(path).resolve().parent}", "-o", str(Path(build) / "VasExtract.olean"), str(path)], cwd=ROOT,
                           env=env, capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            return r.returncode, r.stdout + r.stderr
        c = subprocess.run([LEANCHECKER, "VasExtract"], cwd=ROOT, capture_output=True, text=True, timeout=900,
                           env=dict(env, LEAN_PATH=env["LEAN_PATH"] + ":" + build,
                                    PATH=str(Path(LEAN).parent) + ":" + env.get("PATH", "")))
        note = f"\nleanchecker exit {c.returncode}\n{(c.stdout + c.stderr)[-1500:]}\n"
        return (0 if c.returncode == 0 else 10), r.stdout + r.stderr + note


def expression_identities(text, marker):
    """Read complete expression records; duplicate/missing records fail closed."""
    records = re.findall(r"^" + re.escape(marker) + r" (\S+) : (.*?) VAS_END", text, re.M | re.S)
    result = {}
    for name, value in records:
        if name in result:
            raise ValueError(f"duplicate expression identity for {name}")
        result[name] = " ".join(value.split())
    return result


def statement_text(lines, start, name):
    """The source of theorem `name`'s statement: from after `name :` to the `:=` that opens its proof."""
    text = "\n".join(lines[start - 1:])
    m = re.match(r"\s*(?:theorem|lemma)\s+" + re.escape(name) + r"\s*:(.*?):=", text, re.S)
    if not m:
        raise ValueError(f"cannot read the statement of {name}")
    return " ".join(m.group(1).split())


@click.command()
@click.argument("lean_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--theorem", "theorems", multiple=True, required=True, help="a conclusion theorem (repeatable)")
@click.option("--out", "out_stem", required=True, help="output stem: writes <out>.lean and <out>.json")
def main(lean_file, theorems, out_stem):
    src = Path(lean_file).read_text()
    lines = src.splitlines()
    out = Path(out_stem)
    probe = out.with_name(out.name + ".probe.lean")
    targets = "[" + ", ".join(f"``{t}" for t in theorems) + "]"
    body = re.sub(r"(?m)^#print axioms.*\n?", "", src)
    # a file written by the current checker already ends with its own LISTER; drop it, the probe appends one
    head = next(ln for ln in LISTER.splitlines() if ln.strip())
    if head in body:
        body = body[:body.index(head)]
    probe.write_text(body + "\nset_option format.width 100000\n" + IDENTITY + REACH.replace("TARGETS", targets)
                     + LISTER.replace("ROOTS", targets))
    status, text = run_lean(probe)
    report = {"file": lean_file, "conclusions": list(theorems), "lean_exit": status}
    if status != 0 or "VAS_REACHED" not in text:
        report |= {"ok": False, "error": "the source did not compile with the extractor",
                   "errors": [ln for ln in text.splitlines() if ": error" in ln][:5]}
        print(json.dumps(report, indent=1))
        sys.exit(1)
    decls = {}
    for name, a, b in re.findall(r"VAS_DECL (\S+) (\d+) (\d+)", text):
        decls[name] = (int(a), int(b))
    unranged = re.findall(r"VAS_UNRANGED (\S+)", text)
    concl = dict(re.findall(r"VAS_CONCLUSION (\S+) : (.*?) VAS_END", text, re.S))
    original_identities = expression_identities(text, "VAS_ORIGINAL_IDENTITY")
    dependency_identities = expression_identities(text, "VAS_DEPENDENCY_IDENTITY")
    added = [a for a in listed(text) or [] if a["used"]]
    # the extracted file: imports, then each assumption's source in file order, inside its namespace. A range
    # inside another one (a structure's fields and constructor) is part of it and is not copied twice.
    imports = [ln for ln in lines if ln.startswith("import ")]
    spans = sorted(set(decls.values()))
    keep = [s for s in spans if not any(o != s and o[0] <= s[0] and s[1] <= o[1] for o in spans)]
    for x, y in zip(keep, keep[1:]):
        if y[0] <= x[1]:
            raise ValueError(f"overlapping declaration ranges {x} and {y}")
    owner = {}
    for name, rng in decls.items():
        if rng in keep and (rng not in owner or len(name) < len(owner[rng])):
            owner[rng] = name
    head = re.compile(r"^\s*(?:@\[[^\]]*\]\s*)?(?:noncomputable\s+|private\s+|protected\s+)*"
                      r"(?:def|theorem|lemma|abbrev|structure|inductive|class|axiom|instance|opaque)\s+([^\s:({\[]+)")
    # top-level `open X` lines of the source go along, in file order, so names resolve as they did there
    opens = [(i + 1, i + 1) for i, ln in enumerate(lines)
             if re.match(r"open\s+[\w.]+(\s+[\w.]+)*\s*$", ln) and not any(a <= i + 1 <= b for a, b in keep)]
    parts, current = [], None
    for rng in sorted(keep + opens):
        a, b = rng
        if rng in opens and rng not in owner:
            if current:
                parts.append(f"end {current}\n")
                current = None
            parts.append(lines[a - 1])
            continue
        name = owner[rng]
        short = next((m.group(1) for ln in lines[a - 1:b] if (m := head.match(ln))), None)
        if short is None or not (name == short or name.endswith("." + short)):
            raise ValueError(f"cannot match the source of {name} at lines {a}-{b}")
        ns = name[: -len(short) - 1] if name != short else ""
        if ns != current:
            if current:
                parts.append(f"end {current}\n")
            if ns:
                parts.append(f"namespace {ns}")
            current = ns
        parts.append("\n".join(lines[a - 1:b]) + "\n")
    if current:
        parts.append(f"end {current}\n")
    starts = {}
    for t in theorems:
        m = re.search(r"(?m)^\s*(?:theorem|lemma)\s+" + re.escape(t) + r"\b", src)
        starts[t] = src[:m.start()].count("\n") + 1 if m else None
    stmts = {t: statement_text(lines, starts[t], t) for t in theorems}
    conclusions = "".join(f"def conclusion_{t} : Prop := {stmts[t]}\n" for t in theorems)
    extracted = ("\n".join(imports) + "\n\n" + "\n".join(parts) + "\n\n"
                 "/-! Conclusions (statements of the proved theorems). -/\n" + conclusions)
    out.with_suffix(".lean").write_text(extracted)
    # step 5: the extracted file compiles alone, and its conclusions are the proved statements
    check = out.with_name(out.name + ".check.lean")
    names = "[" + ", ".join(f"``conclusion_{t}" for t in theorems) + "]"
    dependencies = "[" + ", ".join(f"``{name}" for name in dependency_identities) + "]"
    check.write_text(extracted + IDENTITY + COMPARE.replace("NAMES", names).replace("DEPENDENCIES", dependencies))
    status2, text2 = run_lean(check)
    extracted_identities = expression_identities(text2, "VAS_EXTRACTED_IDENTITY")
    same = {t: bool(original_identities.get(t)) and
            original_identities[t] == extracted_identities.get("conclusion_" + t)
            for t in theorems}
    extracted_dependencies = expression_identities(text2, "VAS_EXTRACTED_DEPENDENCY_IDENTITY")
    dependencies_same = {name: value == extracted_dependencies.get(name)
                         for name, value in dependency_identities.items()}
    identity_hashes = {
        t: {"original_sha256": hashlib.sha256(original_identities[t].encode()).hexdigest()
            if t in original_identities else None,
            "extracted_sha256": hashlib.sha256(extracted_identities["conclusion_" + t].encode()).hexdigest()
            if "conclusion_" + t in extracted_identities else None}
        for t in theorems}
    dependency_hashes = {
        name: {"original_sha256": hashlib.sha256(value.encode()).hexdigest(),
               "extracted_sha256": hashlib.sha256(extracted_dependencies[name].encode()).hexdigest()
               if name in extracted_dependencies else None}
        for name, value in dependency_identities.items()}
    report |= {"ok": status2 == 0 and all(same.values()) and all(dependencies_same.values())
               and set(dependency_identities) == set(extracted_dependencies) and not unranged,
               "compiles_alone": status2 == 0,
               "faithful": same, "assumption_declarations": [owner[r] for r in keep],
               "identity_method": "kernel-expression-repr-v1", "conclusion_identities": identity_hashes,
               "dependency_faithful": dependencies_same, "dependency_identities": dependency_hashes,
               "unranged": unranged, "added_assumptions": added,
               "conclusions_as_proved": {t: " ".join(concl[t].split()) for t in theorems},
               "extracted_file": str(out.with_suffix(".lean")),
               "errors": [ln for ln in text2.splitlines() if ": error" in ln][:5]}
    out.with_suffix(".json").write_text(json.dumps(report, indent=1))
    probe.unlink()
    check.unlink()
    print(json.dumps(report, indent=1))
    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
