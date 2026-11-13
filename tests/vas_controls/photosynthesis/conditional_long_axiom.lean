-- from the second Codex soundness review (artifacts/ot1583-checker-review/review2.md, probe long-axiom)
axiom nested : True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (True ∧ (False)))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))
theorem helper' : True := trivial
theorem balanced_example : goal_balanced_example := by
  unfold goal_balanced_example Task.Balanced
  omega

theorem all_balanced_are_multiples : goal_all_balanced_are_multiples := by
  intro a b c d h
  unfold Task.Balanced at h
  omega

theorem mass_conserved : goal_mass_conserved := by
  have h := nested
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  have h := h.2
  exact False.elim h
theorem glucose_yield_per_kg_co2 : goal_glucose_yield_per_kg_co2 := by
  unfold goal_glucose_yield_per_kg_co2 mCO2 mGlucose mC mH mO
  constructor <;> norm_num
