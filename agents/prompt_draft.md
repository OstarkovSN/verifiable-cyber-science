You are the scientist agent in a verifiable-science experiment. This time you also write the formal claim yourself (claim generation). A human reviewer will later judge whether your formal statement faithfully captures the question; that judgment is not yours.

The question, as a scientist would pose it:
"A cup of coffee is poured at 90 °C in a room at 20 °C. Ten minutes later it is at 70 °C. Assuming Newton's law of cooling (the rate of cooling is proportional to the difference between the coffee and room temperatures, with a constant coefficient), when will it reach 50 °C, a comfortable drinking temperature? Give the answer as a guaranteed interval, in minutes."

Working directory: {workdir}. Read ONLY the docstring at the top of src/vas_check.py, this prompt, tasks/radiocarbon/Spec.lean and tasks/radiocarbon/task.json (as format examples only; do not read any other task, artifacts/, proofs/, git history), and Mathlib sources under .lake/packages/mathlib/Mathlib/ for lemma names (search them with grep -rn and an explicit path).

Step 1 (claim): create tasks-drafts/{draft}/ with
- card.md: the question, the measurements, every model assumption in plain words, what Lean will and will not check;
- Spec.lean: `namespace Task` ... `end Task`, with the model as definitions (mark real-valued defs noncomputable), the data, and one `def goal_<name> : Prop := ...` per conclusion. Include at least: that your temperature function satisfies Newton's law (a HasDerivAt statement), that it matches the two measurements, and the time interval for 50 °C. Choose an interval width you think you can prove;
- task.json: {"title": ..., "imports": [], "required": [the goal names without the goal_ prefix]}.
Then lint it: VAS_DRAFTS=1 python3 src/vas_check.py --lint {draft} (the goals must elaborate). Once the lint passes, do not change Spec.lean again. If you must change it later, say so explicitly in your final report.

Step 2 (proof): prove it through the checker exactly as described in the docstring, with VAS_DRAFTS=1 set:
  mkdir -p artifacts/vas-runs-drafts/{draft}/{run}
  VAS_DRAFTS=1 python3 src/vas_check.py --file artifacts/vas-runs-drafts/{draft}/{run}/attemptK.lean --task {draft} --run {run} --name attemptK
The body must contain `theorem n : goal_n := ...` for each required n. Forbidden: native_decide, import, namespace/section/end, `#` commands, strings, meta-programming. At most {cap} checker calls. Never claim success unless the checker printed "ok": true. An `axiom` or `sorry` is allowed but is not a pass: the checker returns "verdict": "proved_if" and lists each one for a person to accept or reject.

Final message (short): STATUS; checker calls; the Spec as you froze it (paste the goal_ definitions); whether you changed Spec after the lint; the interval you proved; anything you simplified relative to the question.
