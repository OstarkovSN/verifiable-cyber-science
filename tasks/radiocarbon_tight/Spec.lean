namespace Task
/-! Model (assumptions, reviewed by a person, not proved):
  after death an organism stops exchanging carbon, and its 14C decays exponentially with half-life T = 5730 years
  (the Cambridge half-life, a measured constant taken as given). The fraction f of the original 14C/12C ratio that
  remains after t years is exp(-lambda t), with lambda = log 2 / T. The initial ratio is assumed equal to today's
  atmospheric value (no calibration-curve correction, no reservoir effect).
  Measurement (ILLUSTRATIVE): a bone sample retains between 24 % and 25 % of the modern ratio, uncertainty included. -/
def halfLife : ℝ := 5730
noncomputable def decayRate : ℝ := Real.log 2 / halfLife
noncomputable def fractionLeft (t : ℝ) : ℝ := Real.exp (-(decayRate * t))
/-- the age read off a measured fraction -/
noncomputable def age (f : ℝ) : ℝ := -Real.log f / decayRate

/-! Conclusion: the same measurement, with the upper end of the age interval within a year of its exact value
(the exact age at f = 0.24 is about 11797.5 years). -/
def goal_age_interval_tight : Prop := ∀ f : ℝ, 24 / 100 ≤ f → f ≤ 1 / 4 → 11460 ≤ age f ∧ age f ≤ 11798
end Task
