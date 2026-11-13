-- from the Codex soundness review of 0fb41be (artifacts/ot1583-checker-review/review.md, probe heartbeats)
set_option maxHeartbeats 1
theorem balanced_example : goal_balanced_example := by
  unfold goal_balanced_example Task.Balanced
  omega
theorem all_balanced_are_multiples : goal_all_balanced_are_multiples := by
  intro a b c d h
  unfold Task.Balanced at h
  omega
theorem mass_conserved : goal_mass_conserved := by
  unfold goal_mass_conserved mCO2 mH2O mGlucose mO2 mC mH mO
  norm_num
theorem glucose_yield_per_kg_co2 : goal_glucose_yield_per_kg_co2 := by
  unfold goal_glucose_yield_per_kg_co2 mCO2 mGlucose mC mH mO
  constructor <;> norm_num
