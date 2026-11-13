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

/-! Conclusions. -/
/-- the path solves the cooling law -/
def goal_path_solves_law : Prop :=
  ∀ C P k T0 t : ℝ, 0 < C → 0 < k → HasDerivAt (path C P k T0) ((P - k * (path C P k T0 t - roomT)) / C) t
/-- the closed-form phase time is when the path reaches T2 -/
def goal_phase_time_correct : Prop :=
  ∀ C P k T1 T2 : ℝ, 0 < C → 0 < k → T1 ≤ T2 → k * (T2 - roomT) < P →
    0 ≤ phaseTime C P k T1 T2 ∧ path C P k T1 (phaseTime C P k T1 T2) = T2
/-- without heat loss the moment does not matter at all -/
def goal_lossless_no_difference : Prop :=
  ∀ Cb Hd P Hs : ℝ, Plausible Cb Hd → 0 < P → 0 ≤ Hs → Hs ≤ maxAddH → totalTime Cb Hd P 0 Hs = totalTime Cb Hd P 0 0
/-- at the neutral moment the salt changes nothing; before it the salt cools the water, after it warms it -/
def goal_neutral_moment : Prop :=
  ∀ Cb Hd : ℝ, Plausible Cb Hd →
    0 < neutralH Cb Hd ∧ tempBrine Cb Hd (neutralH Cb Hd) = tempWater (neutralH Cb Hd) ∧
    (∀ H, H < neutralH Cb Hd → tempBrine Cb Hd H < tempWater H) ∧
    (∀ H, neutralH Cb Hd < H → tempWater H < tempBrine Cb Hd H)
/-- with heat loss, delaying the salt costs time up to the neutral moment and saves time after it: the worst
    admissible moment is min neutralH maxAddH (the neutral moment if it comes before boiling), and the best is at one
    of the two ends -/
def goal_neutral_is_worst : Prop :=
  ∀ Cb Hd P k : ℝ, Plausible Cb Hd → 0 < k → k * (brineBoil - roomT) < P →
    MonotoneOn (totalTime Cb Hd P k) (Set.Icc 0 (min (neutralH Cb Hd) maxAddH)) ∧
    AntitoneOn (totalTime Cb Hd P k) (Set.Icc (neutralH Cb Hd) maxAddH)
/-- if the salt cools the water at every temperature it can still be added at, the start is the best moment -/
def goal_earliest_best_if_salt_always_cools : Prop :=
  ∀ Cb Hd P k Hs : ℝ, Plausible Cb Hd → 0 < k → k * (brineBoil - roomT) < P → maxAddH ≤ neutralH Cb Hd →
    0 ≤ Hs → Hs ≤ maxAddH → totalTime Cb Hd P k 0 ≤ totalTime Cb Hd P k Hs
end Task
