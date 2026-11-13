namespace Task
/-! Model (assumptions, reviewed by a person, not proved):
  Newton's law of cooling: the coffee temperature T(t) (°C, t in minutes after pouring) obeys
  T'(t) = -c * (T(t) - 20), room temperature 20 °C, constant coefficient c (per minute, unknown a priori).
  Measurements: T(0) = 90, T(10) = 70 (exact, no measurement error). -/
def roomTemp : ℝ := 20
def T0 : ℝ := 90
def T10 : ℝ := 70
/-- the cooling coefficient implied by the data: exp(-10 c) = (70-20)/(90-20) = 5/7 -/
noncomputable def coeff : ℝ := Real.log (7 / 5) / 10
/-- the closed-form solution of the cooling law through the two measurements -/
noncomputable def temp (t : ℝ) : ℝ := roomTemp + (T0 - roomTemp) * Real.exp (-(coeff * t))

/-- temp satisfies Newton's law with coefficient coeff, at every time -/
def goal_newton_law : Prop := ∀ t : ℝ, HasDerivAt temp (-coeff * (temp t - roomTemp)) t
/-- temp matches both measurements -/
def goal_matches_data : Prop := temp 0 = T0 ∧ temp 10 = T10
/-- the coefficient is positive (the coffee cools toward the room) -/
def goal_coeff_pos : Prop := 0 < coeff
/-- any differentiable solution of Newton's law (any constant coefficient c) through the two measurements is temp -/
def goal_unique : Prop :=
  ∀ (f : ℝ → ℝ) (c : ℝ), (∀ t, HasDerivAt f (-c * (f t - roomTemp)) t) → f 0 = T0 → f 10 = T10 → ∀ t, f t = temp t
/-- the coffee is at 50 °C at exactly one time, and that time is between 25 and 25.5 minutes after pouring -/
def goal_time_interval : Prop :=
  ∃ t : ℝ, temp t = 50 ∧ 25 ≤ t ∧ t ≤ 51 / 2 ∧ ∀ s : ℝ, temp s = 50 → s = t
end Task
