namespace Task
/-! Model (assumptions, reviewed by a person, not proved):
  net photosynthesis a CO2 + b H2O -> c C6H12O6 + d O2 with whole-number coefficients; atoms are conserved
  (no nuclear change), element by element: carbon, hydrogen, oxygen.
  Molar masses from the IUPAC conventional standard atomic weights (taken as given): C 12.011, H 1.008, O 15.999 g/mol. -/
def Balanced (a b c d : ℕ) : Prop :=
  a = 6 * c ∧              -- carbon
  2 * b = 12 * c ∧         -- hydrogen
  2 * a + b = 6 * c + 2 * d -- oxygen
def mC : ℚ := 12011 / 1000
def mH : ℚ := 1008 / 1000
def mO : ℚ := 15999 / 1000
def mCO2 : ℚ := mC + 2 * mO
def mH2O : ℚ := 2 * mH + mO
def mGlucose : ℚ := 6 * mC + 12 * mH + 6 * mO
def mO2 : ℚ := 2 * mO

/-! Conclusions. -/
def goal_balanced_example : Prop := Balanced 6 6 1 6
/-- every balanced equation is a whole multiple of 6 CO2 + 6 H2O -> C6H12O6 + 6 O2 -/
def goal_all_balanced_are_multiples : Prop :=
  ∀ a b c d : ℕ, Balanced a b c d → a = 6 * c ∧ b = 6 * c ∧ d = 6 * c
def goal_mass_conserved : Prop := 6 * mCO2 + 6 * mH2O = mGlucose + 6 * mO2
/-- grams of glucose fixed per kilogram of CO2 taken up -/
def goal_glucose_yield_per_kg_co2 : Prop := 682 < 1000 * mGlucose / (6 * mCO2) ∧ 1000 * mGlucose / (6 * mCO2) < 683
end Task
