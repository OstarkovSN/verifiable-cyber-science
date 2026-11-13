namespace Task
/-! Model (assumptions, reviewed by a person, not proved). Source: OSN's question (TG 4180): 1 L of water at 20 °C is
  put on the stove to make boiling salted water; when should the salt go in so that it boils soonest?
  * Lumped heating: the pot contents have one temperature T. The stove delivers a constant power P (W) to them, and
    they lose heat to the room at the rate k (T - roomT), k ≥ 0 (Newton's law of cooling). No evaporation before
    boiling; the pot's own heat capacity is ignored.
  * State: H, the enthalpy (J) of water plus salt relative to "everything at room temperature, salt undissolved",
    so dH/dt = P - k (T - roomT) throughout.
  * Before the salt goes in it waits on the shelf at room temperature: T = roomT + H / waterC.
  * Adding the salt is instantaneous at constant H; it dissolves at once. Afterwards T = roomT + (H - Hd) / Cb, with
    a CONSTANT brine heat capacity Cb = waterC + n phiCp and Hd = n dH20, the enthalpy of dissolving the salt at
    room temperature. Constant phiCp is a simplification: the real value changes with temperature.
  * The data are uncertain, so Cb and Hd are not fixed numbers but range over `Plausible`: phiCp in [-95, -40]
    J/(mol K) and dH20 in [3500, 6000] J/mol. Each pair is a constant EFFECTIVE value; the range encloses the
    temperature-dependent tabulated values from 20 to 100 °C, at infinite dilution and near 0.17 mol/kg (Pitzer,
    Peiper and Busey 1984, Tables A-4 and A-11: -93 J/(mol K) at 20 °C, -84 at 25 °C; Archer 1992, Table 8).
  * Goal state: the brine at its normal boiling point, 100 °C + Kb 2 n (Kb = 0.512 K kg/mol, 1 kg of water). Pure
    water cannot pass 100 °C, so the salt must go in at some H in [0, maxAddH].
  * Fixed data: 1 kg of water, c = 4184 J/(kg K); 10 g of NaCl, molar mass 58.44 g/mol (an ILLUSTRATIVE amount). -/
def roomT : ℝ := 20
def waterC : ℝ := 4184
noncomputable def saltMol : ℝ := 10 / 58.44
noncomputable def brineBoil : ℝ := 100 + 0.512 * 2 * saltMol
noncomputable def maxAddH : ℝ := waterC * (100 - roomT)
/-- the uncertain salt data, as brine heat capacity Cb and room-temperature dissolving enthalpy Hd -/
def Plausible (Cb Hd : ℝ) : Prop :=
  waterC + saltMol * (-95) ≤ Cb ∧ Cb ≤ waterC + saltMol * (-40) ∧ saltMol * 3500 ≤ Hd ∧ Hd ≤ saltMol * 6000
noncomputable def tempWater (H : ℝ) : ℝ := roomT + H / waterC
noncomputable def tempBrine (Cb Hd H : ℝ) : ℝ := roomT + (H - Hd) / Cb

/-- for k > 0, the temperature path of a phase with heat capacity C started at T0: the solution of
    C T' = P - k (T - roomT). (At k = 0 this formula is meaningless; the lossless case is handled in phaseTime.) -/
noncomputable def path (C P k T0 t : ℝ) : ℝ := roomT + P / k + (T0 - roomT - P / k) * Real.exp (-(k / C) * t)
/-- the time a phase with heat capacity C takes from T1 to T2 (closed form; k = 0 is the lossless case) -/
noncomputable def phaseTime (C P k T1 T2 : ℝ) : ℝ :=
  if k = 0 then C * (T2 - T1) / P else C / k * Real.log ((P - k * (T1 - roomT)) / (P - k * (T2 - roomT)))
/-- total time to boiling brine when the salt goes in at enthalpy Hs -/
noncomputable def totalTime (Cb Hd P k Hs : ℝ) : ℝ :=
  phaseTime waterC P k roomT (tempWater Hs) + phaseTime Cb P k (tempBrine Cb Hd Hs) brineBoil
/-- the enthalpy at which adding the salt neither cools nor warms the water (the "neutral" moment) -/
noncomputable def neutralH (Cb Hd : ℝ) : ℝ := waterC * Hd / (waterC - Cb)

/-! Conclusion. -/
/-- for a kitchen stove (1-3 kW into the water), heat loss up to 10 W/K and any plausible salt data, any two
    moments of adding the salt give times to boiling that differ by at most three seconds -/
def goal_at_most_three_seconds : Prop :=
  ∀ Cb Hd P k H1 H2 : ℝ, Plausible Cb Hd → 1000 ≤ P → P ≤ 3000 → 0 < k → k ≤ 10 →
    0 ≤ H1 → H1 ≤ maxAddH → 0 ≤ H2 → H2 ≤ maxAddH → |totalTime Cb Hd P k H1 - totalTime Cb Hd P k H2| ≤ 3
end Task
