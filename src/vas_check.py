"""VAS checker: one bounded Lean call per agent attempt, against a fixed task card, written and frozen before any attempt.

A task lives in tasks/<id>/:
  card.md      the real-world question, measurements, model assumptions, relevance (prose, for the reviewer)
  task.json    {"imports": [...], "required": [agent theorem names], "eval": [optional Lean terms to print]}
  Spec.lean    namespace Task: the model and the data as definitions (the assumptions, nothing proved), and for each
               required name n the target statement as `def goal_n : Prop := ...` (the conclusion)
The checker appends `theorem verifier_n : Task.goal_n := n` for every required n, so the agent's theorem n must prove
exactly that statement.

Added assumptions (OSN, TG 4354). The agent may declare `axiom name : statement` for a premise it thinks the card
lacks, or leave a step as `sorry`. Neither is a pass. Lean itself lists them (LISTER, appended after the body): every
axiom declared in the file with its statement as Lean prints it, and every sorry as the goal it stands for with the
hypotheses in scope, each marked "used" when a verifier theorem depends on it; unused ones are listed too. These go
to "added_assumptions", and "conditional_on" names, per required theorem, the axioms it rests on (sorryAx = a gap).
The verdict is "proved_if": proved on condition that the listed used statements hold, for a person to accept or
reject. An unexpected axiom that the lister did not list, or a lister that did not finish, fails closed.
Verdicts and exit codes: "proved" (ok: true, exit 0), "proved_if" (exit 3), "not_proved" (Lean errors, a required
theorem missing from the audit, or an undisclosed addition; exit 1), "no_verdict" (a time, memory or recursion limit
was hit, nothing can be concluded; exit 2). A contract rejection exits 1. The agent submits only a proof body (definitions, lemmas, the required theorems). It cannot import, open a namespace,
add axioms, or use sorry/native_decide (the restricted contract of src/task_lean.py), and the statement it is checked
against is the goal_ in Spec.lean, not whatever its own theorem says. `#print axioms` on every theorem must show only
propext, Classical.choice and Quot.sound.

Every call is appended to artifacts/vas-trail/<task>/<run>.jsonl (time, source hash, bytes, ok, Lean exit code,
axioms, wall seconds, the first errors) and the full .lean/.log pair is kept, so the trail is inspectable afterwards.

What a pass means: Lean's kernel accepted a derivation of the goal_ statements from the Spec.lean definitions.
The file is compiled to a module and leanchecker, a separate process, re-checks every declaration in it with the
kernel; a pass needs that re-check to exit 0 ("kernel_recheck"), so nothing the body does inside Lean can skip it.
It says nothing about whether Spec.lean describes the world; that is the reviewer's job, on Spec.lean and card.md.

Run: echo '{"task": "hardy_weinberg", "run": "claude-1", "name": "attempt", "lean": "..."}' | python3 src/vas_check.py
     python3 src/vas_check.py --file body.lean --task hardy_weinberg --run claude-1 [--name attempt]
"""
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
# VAS_DRAFTS=1: agent-drafted task cards (claim generation) live apart from the reviewed ones and have their own trail
DRAFTS = os.environ.get("VAS_DRAFTS") == "1"
TASKS = ROOT / ("tasks-drafts" if DRAFTS else "tasks")
TRAIL = ROOT / ("artifacts/vas-trail-drafts" if DRAFTS else "artifacts/vas-trail")
# the toolchain pinned in lean-toolchain, under ELAN_HOME (default ~/.elan); VAS_LEAN overrides
_TOOLCHAIN = (ROOT / "lean-toolchain").read_text().strip().replace("/", "--").replace(":", "---")
LEAN = os.environ.get("VAS_LEAN") or str(Path(os.environ.get("ELAN_HOME", Path.home() / ".elan"))
                                         / "toolchains" / _TOOLCHAIN / "bin/lean")
WALL = 300
# OT-1861: a body that runs code during elaboration can add a declaration with kernel checking switched off, and
# `#print axioms` and the LISTER (same process) do not notice. leanchecker, a separate process, replays every
# declaration of the compiled module through the kernel; a pass requires it to exit 0.
LEANCHECKER = str(Path(LEAN).with_name("leanchecker"))
ALLOWED_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
FORBIDDEN = re.compile(
    r"\b(axioms|native_decide|implemented_by|extern|unsafe|opaque|import|"
    r"macro|macro_rules|syntax|elab|notation|infix|infixl|infixr|prefix|postfix|"
    r"run_cmd|run_tac|run_elab|run_meta|initialize|builtin_initialize|instance|attribute|"
    r"partial|private|local|scoped|namespace|section|end|universe|variable|export|IO|System|"
    r"Lean|native|simproc|dsimproc)\b"
    # any word containing elab (by_elab, elab_rules, run_elab: `\belab\b` misses them, `_` is a word character);
    # backtick name literals and quotations are metaprogramming, which a proof body never needs (OT-1861)
    r"|\w*elab\w*|`|#|@\[|\$|«|»")
NAME = re.compile(r"[a-z0-9_-]+")
# One import set for every task (what this box has built): reals, log/exp/rpow, derivatives, binomials, tactics.
COMMON_IMPORTS = ["Mathlib.Analysis.SpecialFunctions.Log.Basic", "Mathlib.Analysis.SpecialFunctions.Pow.Real",
                  "Mathlib.Analysis.SpecialFunctions.ExpDeriv", "Mathlib.Analysis.SpecialFunctions.Log.Deriv",
                  "Mathlib.Analysis.Calculus.MeanValue", "Mathlib.Analysis.Calculus.Deriv.Pow",
                  "Mathlib.Analysis.Calculus.Deriv.Mul", "Mathlib.Analysis.Calculus.Deriv.Add",
                  "Mathlib.Data.Nat.Choose.Basic", "Mathlib.Tactic.Ring", "Mathlib.Tactic.FieldSimp",
                  "Mathlib.Tactic.NormNum", "Mathlib.Tactic.Linarith", "Mathlib.Tactic.Positivity",
                  "Mathlib.Tactic.IntervalCases", "Mathlib.Tactic.GCongr", "Mathlib.Tactic.Push",
                  "Mathlib.Tactic.FinCases", "Mathlib.Tactic.Bound", "Mathlib.Tactic.Abel", "Mathlib.Tactic.Use"]


def strip_comments(source):
    out, i, depth = [], 0, 0
    while i < len(source):
        if source.startswith("/-", i):
            depth += 1
            i += 2
        elif depth and source.startswith("-/", i):
            depth -= 1
            i += 2
        elif depth:
            i += 1
        elif source.startswith("--", i):
            j = source.find("\n", i)
            i = len(source) if j == -1 else j
            out.append("\n")
        else:
            out.append(source[i])
            i += 1
    if depth:
        raise ValueError("Unclosed Lean comment")
    return "".join(out)


def load_task(task):
    if not NAME.fullmatch(task) or not (TASKS / task / "task.json").exists():
        raise ValueError(f"Unknown task {task!r}; tasks: {sorted(p.name for p in TASKS.iterdir() if p.is_dir())}")
    d = TASKS / task
    meta = json.loads((d / "task.json").read_text())
    meta["imports"] = COMMON_IMPORTS + [m for m in meta.get("imports", []) if m not in COMMON_IMPORTS]
    verify = "".join(f"theorem verifier_{n} : Task.goal_{n} := {n}\n" for n in meta["required"])
    return meta, (d / "Spec.lean").read_text(), verify


def validate(source, required):
    if not isinstance(source, str) or not 0 < len(source.encode()) <= 24000:
        raise ValueError("Lean body must contain at most 24000 UTF-8 bytes")
    code = strip_comments(source)
    if '"' in code:
        raise ValueError("Put prose in comments; executable strings are outside this contract")
    code = re.sub(r"^\s*set_option (maxRecDepth|maxHeartbeats) \d+\s*$", "", code, flags=re.M)
    if re.search(r"\bset_option\b", code):
        raise ValueError("Only maxRecDepth/maxHeartbeats options are available")
    if "VAS_" in code:
        raise ValueError("Names containing VAS_ are reserved for the checker's own report")
    bad = FORBIDDEN.search(code)
    if bad:
        raise ValueError(f"Outside the restricted Lean contract: {bad.group()}")
    if re.search(r"\b(?:def|abbrev|theorem|lemma|structure|inductive|class)\s+[^\s:(]+\.", code):
        raise ValueError("Declare plain top-level names; the Task namespace is immutable")
    theorems = re.findall(r"^\s*(?:theorem|lemma)\s+([A-Za-z_][A-Za-z_0-9']*)", code, re.M)
    missing = [n for n in required if n not in theorems]
    if missing:
        raise ValueError(f"Missing required theorems: {missing} (their statements are the goal_ definitions in Spec.lean)")
    if re.search(r"\baxiom\b(?!\s+[A-Za-z_][A-Za-z_0-9']*\s*[:({\[])", code):
        raise ValueError("Declare an added assumption as `axiom name : statement` at the start of a line")
    return theorems


# Lean itself lists what the proof adds: every axiom declared in the file and every sorry (by its elaborated goal with
# the hypotheses in scope), each marked used when a verifier theorem reaches it. Read from the checked kernel
# environment, as #print axioms does. Never part of an agent body (run_cmd is outside the contract).
LISTER = """
/-- true if `sorryAx` occurs anywhere other than as the head of an application that states its goal -/
private partial def VAS_unstated : Lean.Expr → Bool
  | e@(.app ..) =>
    let f := e.getAppFn
    (if f.isConstOf ``sorryAx then false else VAS_unstated f) || e.getAppArgs.any VAS_unstated
  | .const n _ => n == ``sorryAx
  | .lam _ t b _ | .forallE _ t b _ => VAS_unstated t || VAS_unstated b
  | .letE _ t v b _ => VAS_unstated t || VAS_unstated v || VAS_unstated b
  | .mdata _ b | .proj _ _ b => VAS_unstated b
  | _ => false

set_option format.width 100000 in
set_option pp.deepTerms true in
set_option pp.proofs true in
set_option pp.maxSteps 100000000 in
open Lean Elab Command Meta in
run_cmd do
  let kenv := (← getEnv).checked.get
  let locals := kenv.constants.map₂.toList
  let localSet : NameSet := locals.foldl (fun s (n, _) => s.insert n) {}
  let exprsOf (ci : ConstantInfo) : Array Expr :=
    #[ci.type] ++ (match ci with
      | .defnInfo v => #[v.value] | .thmInfo v => #[v.value] | .opaqueInfo v => #[v.value] | _ => #[])
  let mut used : NameSet := {}
  let mut todo : List Name := ROOTS
  while !todo.isEmpty do
    let n := todo.head!
    todo := todo.tail!
    if used.contains n then continue
    used := used.insert n
    if let some ci := kenv.find? n then
      for e in exprsOf ci do
        for c in e.getUsedConstants do
          if localSet.contains c && !used.contains c then todo := c :: todo
  for (n, ci) in locals do
    if let .axiomInfo _ := ci then
      logInfo m!"VAS_AXIOM {n} used={used.contains n} : {← liftTermElabM <| ppExpr ci.type} VAS_END"
    -- every declaration kind, type and value: a gap may sit in an axiom's type as well as in a proof
    for e in exprsOf ci do
      -- hasSorry is cached and linear; VAS_unstated walks the term as a tree, exponential on shared proofs
      if e.hasSorry && VAS_unstated e then
        logInfo m!"VAS_GAP {n} used={used.contains n} : (sorry with no stated goal: it can assert anything) VAS_END"
        logInfo m!"VAS_UNSTATED {n} used={used.contains n}"
    if (exprsOf ci).any (·.hasSorry) then
      let seen ← IO.mkRef ({} : Std.HashSet String)
      liftTermElabM do
        for e in exprsOf ci do
          forEachExpr' e fun sub => do
            if sub.isAppOf ``sorryAx && sub.getAppNumArgs ≥ 1 then
              let mut t ← instantiateMVars (sub.getArg! 0)
              if t.isForall && t.bindingDomain!.isConstOf ``Lean.Name then t := t.bindingBody!
              let hyps ← (← getLCtx).foldlM (init := m!"") fun acc d => do
                if d.isImplementationDetail then return acc
                match d.value? with
                | some v => return acc ++ m!"({d.userName} : {← ppExpr d.type} := {← ppExpr v}) "
                | none => return acc ++ m!"({d.userName} : {← ppExpr d.type}) "
              let line ← (m!"VAS_GAP {n} used={used.contains n} : {hyps}⊢ {← ppExpr t} VAS_END").toString
              unless (← seen.get).contains line do
                seen.modify (·.insert line)
                logInfo line
            return true
  logInfo "VAS_LISTED"
"""


def listed(text):
    """Parse the lister's output into added_assumptions entries; None if the lister did not finish."""
    if not re.search(r"^VAS_LISTED\s*$", text, re.M):  # the marker line itself, not a substring of other output
        return None
    out = []
    for kind, name, used, stmt in re.findall(r"VAS_(AXIOM|GAP) (\S+) used=(true|false) : (.*?) VAS_END", text, re.S):
        out.append({"kind": kind.lower(), "in" if kind == "GAP" else "name": name, "used": used == "true",
                    "statement": " ".join(stmt.split())})
    return out


def shown(path):
    """Repository-relative when inside the checkout (the trail), absolute otherwise (a test's temporary trail)."""
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def first_errors(text, k=3):
    errs = [ln for ln in text.splitlines() if ": error" in ln]
    return errs[:k]


def check(task, source, run, name="attempt"):
    if not NAME.fullmatch(run) or not NAME.fullmatch(name):
        raise ValueError("run and name must match [a-z0-9_-]+")
    meta, spec, verify = load_task(task)
    folder = TRAIL / task / run
    folder.mkdir(parents=True, exist_ok=True)
    trail = TRAIL / task / f"{run}.jsonl"
    seq = sum(1 for _ in trail.open()) if trail.exists() else 0
    rec = {"task": task, "run": run, "seq": seq, "name": name, "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "sha256": hashlib.sha256(source.encode() if isinstance(source, str) else b"").hexdigest()[:16],
           "bytes": len(source.encode()) if isinstance(source, str) else 0}
    try:
        theorems = validate(source, meta["required"])
    except ValueError as e:
        rec |= {"ok": False, "stage": "contract", "error": str(e), "wall_s": 0.0}
        with trail.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        return rec
    imports = "".join(f"import {m}\n" for m in meta["imports"])
    head = imports + "set_option maxRecDepth 100000\nset_option maxHeartbeats 4000000\n\n" + spec + "\n"
    tail = "\n" + verify + "\n" + "".join(f"#eval IO.println (toString ({t}))\n" for t in meta.get("eval", []))
    checked = theorems + re.findall(r"^\s*theorem\s+(verifier_[A-Za-z_0-9']*)", verify, re.M)
    tail += "".join(f"#print axioms {n}\n" for n in checked)
    roots = re.findall(r"^\s*theorem\s+(verifier_[A-Za-z_0-9']*)", verify, re.M)
    tail += LISTER.replace("ROOTS", "[" + ", ".join(f"``{n}" for n in roots) + "]")
    path = folder / f"{seq:03d}-{name}.lean"
    path.write_text(head + "open Task\n\n" + source + "\n" + tail)
    libs = sorted((ROOT / ".lake/packages").glob("*/.lake/build/lib/lean"))
    env = dict(os.environ, LEAN_PATH=":".join(map(str, libs)), LEAN_NUM_THREADS="1")
    for key in list(env):
        if any(t in key.upper() for t in ("TOKEN", "SECRET", "API_KEY", "BOT_KEY")):
            env.pop(key)

    def limits():
        resource.setrlimit(resource.RLIMIT_AS, (16 * 1024**3, 16 * 1024**3))
        resource.setrlimit(resource.RLIMIT_CPU, (WALL - 10, WALL - 10))

    log = path.with_suffix(".log")
    t0 = time.time()
    build = tempfile.TemporaryDirectory(prefix="vas-olean-")
    olean = Path(build.name) / "VasAttempt.olean"
    recheck = {"exit_code": None, "output": ""}
    with log.open("w") as out:
        try:
            status = subprocess.run([LEAN, "-j1", "-M6144", f"--root={path.parent}", "-o", str(olean), str(path)], cwd=ROOT, env=env,
                                    stdout=out, stderr=subprocess.STDOUT, timeout=WALL, preexec_fn=limits).returncode
        except subprocess.TimeoutExpired:
            status = 124
            out.write(f"\nLean exceeded the {WALL}-second wall limit.\n")
    if status == 0:
        renv = dict(env, LEAN_PATH=env["LEAN_PATH"] + ":" + build.name,
                    PATH=str(Path(LEAN).parent) + ":" + env.get("PATH", ""))
        try:
            r = subprocess.run([LEANCHECKER, "VasAttempt"], cwd=ROOT, env=renv, capture_output=True, text=True,
                               timeout=WALL, preexec_fn=limits)
            recheck = {"exit_code": r.returncode, "output": (r.stdout + r.stderr)[-1500:]}
        except (subprocess.TimeoutExpired, OSError) as e:
            recheck = {"exit_code": -1, "output": f"leanchecker did not complete: {e}"}
        with log.open("a") as out:
            out.write(f"\nleanchecker exit {recheck['exit_code']}\n{recheck['output']}\n")
    build.cleanup()
    wall = time.time() - t0
    text = log.read_text()
    axioms = {}
    # one #print axioms line per theorem; names may contain apostrophes, so anchor on the line, not on quotes
    for n, group in re.findall(r"^'(.+)' depends on axioms: \[([^\]]*)\]", text, re.M):
        axioms[n] = [a.strip() for a in group.split(",") if a.strip()]
    no_axioms = re.findall(r"^'(.+)' does not depend on any axioms", text, re.M)
    unexpected = sorted({a for g in axioms.values() for a in g if a not in ALLOWED_AXIOMS})
    seen = set(axioms) | set(no_axioms)
    unreported = [n for n in checked if n not in seen and f"Task.{n}" not in seen]
    added = listed(text)
    used_axioms = {a["name"] for a in added or [] if a["kind"] == "axiom" and a["used"]}
    used_gaps = [a for a in added or [] if a["kind"] == "gap" and a["used"]]
    # an addition counts as disclosed only if Lean listed it: sorryAx needs a listed used gap, every other
    # unexpected axiom a listed used axiom; anything else fails closed
    # every applied sorry in a reachable declaration is enumerated; a sorry used without a stated goal, or a
    # statement Lean printed with an elision mark, cannot be disclosed, so it fails closed
    unstated = re.findall(r"VAS_UNSTATED (\S+) used=true", text)
    elided = any("⋯" in a["statement"] for a in added or [] if a["used"])
    disclosed = (all(a in used_axioms or (a == "sorryAx" and used_gaps) for a in unexpected)
                 and not unstated and not elided)
    limit_hit = re.search(r"maximum memory|out of memory|\(deterministic\) timeout|maximum recursion depth", text)
    if status == 124 or status < 0 or status == 137 or limit_hit:
        verdict = "no_verdict"
    elif status != 0 or unreported or added is None or recheck["exit_code"] != 0:
        verdict = "not_proved"
    elif not unexpected:
        verdict = "proved"
    elif disclosed:
        verdict = "proved_if"
    else:
        verdict = "not_proved"
    ok = verdict == "proved"
    conditional = {n: [a for a in axioms.get(f"verifier_{n}", []) if a not in ALLOWED_AXIOMS] for n in meta["required"]}
    rec |= {"ok": ok, "verdict": verdict, "stage": "lean", "exit_code": status, "kernel_recheck": recheck["exit_code"],
            "wall_s": round(wall, 1),
            "unexpected_axioms": unexpected, "added_assumptions": added or [],
            "conditional_on": {n: c for n, c in conditional.items() if c},
            "unreported_theorems": unreported, "errors": first_errors(text), "lean_file": shown(path), "log_file": shown(log)}
    with trail.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    rec["output"] = text if len(text) <= 6000 else text[:4000] + "\n[... middle omitted; full log saved ...]\n" + text[-1800:]
    return rec


def lint(task):
    """Card check for the task author: Spec.lean and every goal_ elaborate (sorry stubs; never an agent path)."""
    meta, spec, _ = load_task(task)
    body = "".join(f"theorem {n} : Task.goal_{n} := sorry\n" for n in meta["required"])
    path = TRAIL / task / "lint.lean"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"import {m}\n" for m in meta["imports"]) + "\n" + spec + "\nopen Task\n" + body +
                    "".join(f"#eval IO.println (toString ({t}))\n" for t in meta.get("eval", [])))
    libs = sorted((ROOT / ".lake/packages").glob("*/.lake/build/lib/lean"))
    r = subprocess.run([LEAN, str(path)], cwd=ROOT, env=dict(os.environ, LEAN_PATH=":".join(map(str, libs))),
                       capture_output=True, text=True, timeout=WALL)
    errs = [ln for ln in r.stdout.splitlines() if ": error" in ln]
    return {"task": task, "elaborates": not errs, "errors": errs, "output": r.stdout[-3000:]}


if __name__ == "__main__":
    args = sys.argv[1:]
    try:
        if args and args[0] == "--lint":
            print(json.dumps(lint(args[1]), indent=1))
            sys.exit()
        if args and args[0] == "--file":
            opts = dict(zip(args[::2], args[1::2]))
            req = {"lean": Path(opts["--file"]).read_text(), "task": opts["--task"], "run": opts["--run"],
                   "name": opts.get("--name", "attempt")}
        else:
            req = json.load(sys.stdin)
        rec = check(req["task"], req["lean"], req["run"], req.get("name", "attempt"))
        print(json.dumps(rec, indent=1))
        sys.exit({"proved": 0, "proved_if": 3, "no_verdict": 2}.get(rec.get("verdict"), 1))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
        sys.exit(1)
