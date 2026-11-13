namespace Task
/-! Model (assumptions, reviewed by a person, not proved):
  Archimedes: a floating body displaces a volume of liquid whose mass equals its own mass, so ice of mass m floating
  in a liquid of density rho displaces the volume m / rho. Melting conserves mass, and the melt is fresh water of
  density rhoW. The melt does not mix in a way that changes the liquid's volume (ideal mixing: the volumes add).
  Densities in kg/m^3: fresh water 1000, sea water 1027, glacier ice 917 (typical values, taken as given). -/
noncomputable def displaced (m rho : ℝ) : ℝ := m / rho
noncomputable def meltVolume (m rhoW : ℝ) : ℝ := m / rhoW
/-- the change in liquid level, expressed as a volume, when ice floating in a liquid of density rho melts -/
noncomputable def levelChange (m rhoW rho : ℝ) : ℝ := meltVolume m rhoW - displaced m rho
def rhoFresh : ℝ := 1000
def rhoSea : ℝ := 1027
def rhoIce : ℝ := 917
/-- fraction of a floating ice block's volume above the water line: (V - displaced) / V, with V = m / rhoIce -/
noncomputable def aboveFraction (rhoI rho : ℝ) : ℝ := 1 - rhoI / rho

/-! Conclusions. -/
/-- ice cubes in a glass of water: melting leaves the level unchanged -/
def goal_glass_level_unchanged : Prop := ∀ m rhoW : ℝ, 0 < rhoW → levelChange m rhoW rhoW = 0
/-- floating ice in denser sea water: melting raises the level -/
def goal_sea_level_rises : Prop :=
  ∀ m rhoW rho : ℝ, 0 < m → 0 < rhoW → rhoW < rho → 0 < levelChange m rhoW rho
/-- the rise is (rho - rhoW) / rhoW of the displaced volume: 2.7 % for sea water -/
def goal_sea_rise_fraction : Prop :=
  ∀ m : ℝ, 0 < m → levelChange m rhoFresh rhoSea = (27 / 1000) * displaced m rhoSea
/-- about a tenth of an iceberg shows above sea level: between 10 % and 11 % -/
def goal_iceberg_tip : Prop := 1 / 10 < aboveFraction rhoIce rhoSea ∧ aboveFraction rhoIce rhoSea < 11 / 100
end Task
