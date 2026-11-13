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

/-! Conclusion as often stated ("floating ice displaces its own melt water, so melting changes nothing"), applied to
sea ice in sea water. Under the model above it is false; this task is a control: no accepted proof should exist. -/
def goal_sea_level_unchanged : Prop := ∀ m : ℝ, 0 < m → levelChange m rhoFresh rhoSea = 0
end Task
