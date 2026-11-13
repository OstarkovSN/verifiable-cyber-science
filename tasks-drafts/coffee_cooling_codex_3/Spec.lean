namespace Task
noncomputable def roomTemp : ℝ := 20
noncomputable def initialTemp : ℝ := 90
noncomputable def measuredTemp : ℝ := 70
noncomputable def measurementTime : ℝ := 10
noncomputable def targetTemp : ℝ := 50
noncomputable def coolingRate : ℝ := Real.log (7 / 5 : ℝ) / 10
noncomputable def temperature (t : ℝ) : ℝ :=
  roomTemp + (initialTemp - roomTemp) * Real.exp (-coolingRate * t)
noncomputable def drinkingTime : ℝ := Real.log (7 / 3 : ℝ) / coolingRate

def goal_newton_law : Prop := ∀ t : ℝ, HasDerivAt temperature
  (-coolingRate * (temperature t - roomTemp)) t

def goal_measurements : Prop :=
  temperature 0 = initialTemp ∧ temperature measurementTime = measuredTemp

def goal_drinking_interval : Prop :=
  25 ≤ drinkingTime ∧ drinkingTime ≤ 26 ∧
  temperature drinkingTime = targetTemp ∧
  ∀ t : ℝ, 0 ≤ t → temperature t = targetTemp → t = drinkingTime
end Task
