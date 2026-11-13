# Radiocarbon dating (physics / archaeology)

**Real-world question.** How old is a bone, if it keeps 24–25% of the modern ¹⁴C/¹²C ratio?

**Measurements.** The remaining fraction f is in [0.24, 0.25]. The value is ILLUSTRATIVE; real AMS measurements give
f with an uncertainty, which is what an interval represents. The half-life is 5730 years.

**Model assumptions (Spec.lean).**
- Exponential decay with a fixed half-life.
- Carbon exchange stops at death.
- The initial ratio equals the modern atmospheric ratio. Real practice replaces this with a calibration curve
  (IntCal) and reservoir corrections; the reviewer must judge it.

**Formal statement.**
- The age formula inverts the decay law.
- Age decreases as the measured fraction increases.
- Every fraction in [0.24, 0.25] gives an age between 11 460 and 11 940 years.

**What Lean checks / does not check.** It checks the inversion, the monotonicity, and the interval bound. The bound
needs inequalities for log 2 and log(25/24); a computer-algebra system would give a float instead. It does not check
the half-life value, the decay model, or the calibration.

**Relevance.** This is the standard dating method of archaeology and Quaternary science. It also shows how a
measurement uncertainty propagates to a conclusion, which is exactly the kind of claim reviewers re-derive by hand.

**Why small.** One exponential law with three short theorems, but the numerical bound needs genuine real-analysis
inequalities.
