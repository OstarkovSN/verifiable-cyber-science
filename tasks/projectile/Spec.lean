namespace Task
/-! Model (assumptions, reviewed by a person, not proved):
  a point mass launched from the ground with velocity components vx (horizontal) and vy (vertical); uniform gravity
  g > 0 downward; no air resistance; flat ground; Newton's second law: the horizontal acceleration is 0 and the
  vertical acceleration is -g. Launch speed v satisfies v^2 = vx^2 + vy^2 (launch at 45 degrees means vx = vy). -/
noncomputable def posX (vx t : ℝ) : ℝ := vx * t
noncomputable def posY (vy g t : ℝ) : ℝ := vy * t - g * t ^ 2 / 2
noncomputable def landingTime (vy g : ℝ) : ℝ := 2 * vy / g

/-! Conclusions: the derivation chain, step by step. -/
/-- 1. the trajectory satisfies Newton's law: velocities vx and vy - g t, vertical acceleration -g -/
def goal_satisfies_newton : Prop := ∀ g vx vy t : ℝ,
  HasDerivAt (fun s => posX vx s) vx t ∧ HasDerivAt (fun s => posY vy g s) (vy - g * t) t ∧
  HasDerivAt (fun s => vy - g * s) (-g) t
/-- 2. and it is the only motion with that acceleration and these initial conditions (height 0, vertical speed vy) -/
def goal_motion_unique : Prop := ∀ (g vy : ℝ) (f v : ℝ → ℝ),
  (∀ t, HasDerivAt f (v t) t) → (∀ t, HasDerivAt v (-g) t) → f 0 = 0 → v 0 = vy → ∀ t, f t = posY vy g t
/-- 3. it returns to the ground exactly once after launch, at t = 2 vy / g -/
def goal_landing_time : Prop := ∀ g vy t : ℝ, 0 < g → 0 < vy → 0 < t → (posY vy g t = 0 ↔ t = landingTime vy g)
/-- 4. the range -/
def goal_range_formula : Prop := ∀ g vx vy : ℝ, 0 < g → posX vx (landingTime vy g) = 2 * vx * vy / g
/-- 5. for a given launch speed the range is at most v^2 / g -/
def goal_range_bound : Prop := ∀ g vx vy : ℝ, 0 < g → posX vx (landingTime vy g) ≤ (vx ^ 2 + vy ^ 2) / g
/-- 6. and the bound is reached exactly at 45 degrees -/
def goal_range_optimal_iff : Prop := ∀ g vx vy : ℝ, 0 < g →
  (posX vx (landingTime vy g) = (vx ^ 2 + vy ^ 2) / g ↔ vx = vy)
/-- 7. the highest point is vy^2 / (2 g) -/
def goal_apex_height : Prop := ∀ g vy t : ℝ, 0 < g → posY vy g t ≤ vy ^ 2 / (2 * g)
end Task
