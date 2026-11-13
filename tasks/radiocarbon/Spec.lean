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

/-! Conclusions. -/
def goal_age_inverts_decay : Prop := ∀ f : ℝ, 0 < f → fractionLeft (age f) = f
def goal_age_antitone : Prop := ∀ f g : ℝ, 0 < f → f ≤ g → age g ≤ age f
/-- the measured interval [0.24, 0.25] dates the sample to between 11460 and 11940 years -/
def goal_age_interval : Prop := ∀ f : ℝ, 24 / 100 ≤ f → f ≤ 1 / 4 → 11460 ≤ age f ∧ age f ≤ 11940
end Task
