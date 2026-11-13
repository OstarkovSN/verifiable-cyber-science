namespace Task
/-! Model: room 20 C, coffee starts at 90 C, dT/dt = -k (T - 20) with constant k; closed form below. Minutes, Celsius. -/
def room : ℝ := 20
def T0 : ℝ := 90
noncomputable def temp (k t : ℝ) : ℝ := room + (T0 - room) * Real.exp (-(k * t))

/-! Conclusions. -/
/-- the function satisfies Newton's law of cooling at every time, for every coefficient -/
def goal_newton : Prop := ∀ k t : ℝ, HasDerivAt (temp k) (-k * (temp k t - room)) t
/-- it starts at 90 C; exactly one coefficient gives 70 C at ten minutes, and it is positive -/
def goal_fit : Prop := (∀ k : ℝ, temp k 0 = 90) ∧ (∃! k : ℝ, temp k 10 = 70) ∧ (∀ k : ℝ, temp k 10 = 70 → 0 < k)
/-- whenever the coefficient matches the 70 C reading, the coffee is at 50 C exactly between 25 and 26 minutes in -/
def goal_time : Prop :=
  (∀ k t : ℝ, temp k 10 = 70 → temp k t = 50 → 25 ≤ t ∧ t ≤ 26) ∧
  (∀ k : ℝ, temp k 10 = 70 → ∃ t : ℝ, temp k t = 50)
end Task
