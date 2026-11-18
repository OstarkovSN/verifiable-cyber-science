"""Restricted Lean validation and kernel-environment assumption audit."""
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
_TOOLCHAIN = (ROOT / "lean-toolchain").read_text().strip().replace("/", "--").replace(":", "---")
LEAN = os.environ.get("VAS_LEAN") or str(Path(os.environ.get("ELAN_HOME", Path.home() / ".elan")) / "toolchains" / _TOOLCHAIN / "bin/lean")
LEANCHECKER = str(Path(LEAN).with_name("leanchecker"))
ALLOWED_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
FORBIDDEN = re.compile(
    r"\b(axioms|native_decide|implemented_by|extern|unsafe|opaque|import|"
    r"macro|macro_rules|syntax|elab|notation|infix|infixl|infixr|prefix|postfix|"
    r"run_cmd|run_tac|run_elab|run_meta|initialize|builtin_initialize|instance|attribute|"
    r"partial|private|local|scoped|namespace|section|end|universe|variable|export|IO|System|"
    r"Lean|native|simproc|dsimproc)\b"
    # any word containing elab (by_elab, elab_rules, run_elab: `\belab\b` misses them, `_` is a word character);
    # Backtick name literals and quotations are metaprogramming, which a proof body never needs.
    r"|\w*elab\w*|`|#|@\[|\$|«|»")


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
        raise ValueError("Declare plain top-level names; namespaces are outside this contract")
    theorems = re.findall(r"^\s*(?:theorem|lemma)\s+([A-Za-z_][A-Za-z_0-9']*)", code, re.M)
    missing = [n for n in required if n not in theorems]
    if missing:
        raise ValueError(f"Missing required theorems: {missing}")
    if re.search(r"\baxiom\b(?!\s+[A-Za-z_][A-Za-z_0-9']*\s*[:({\[])", code):
        raise ValueError("Declare an added assumption as `axiom name : statement` at the start of a line")
    return theorems


# Lean itself lists what the proof adds: every axiom declared in the file and every sorry (by its elaborated goal with
# the hypotheses in scope), each marked used when a conclusion theorem reaches it. Read from the checked kernel
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
