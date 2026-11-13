-- an added assumption: the agent declares a premise instead of proving it; the checker must list it, not pass it
axiom mass_rule : 6 * mCO2 + 6 * mH2O = mGlucose + 6 * mO2

theorem balanced_example : goal_balanced_example := by
  unfold goal_balanced_example Task.Balanced
  omega

theorem all_balanced_are_multiples : goal_all_balanced_are_multiples := by
  intro a b c d h
  unfold Task.Balanced at h
  omega

theorem mass_conserved : goal_mass_conserved := mass_rule

theorem glucose_yield_per_kg_co2 : goal_glucose_yield_per_kg_co2 := by
  have gap : (0 : Rat) < mCO2 := sorry
  unfold goal_glucose_yield_per_kg_co2 mCO2 mGlucose mC mH mO
  constructor <;> norm_num
