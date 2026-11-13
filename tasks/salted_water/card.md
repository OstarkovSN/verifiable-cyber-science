# Salted water: when should the salt go in? (thermodynamics, kitchen physics)

**Real-world question (OSN, TG 4180).** "Suppose you want boiled saline water. You've poured 1 L of 20-degree water
into a can and started the oven. At which temperature / after what time should you add salt in order to boil the
water faster?"

**Measurements and data.**
- 1 kg of water at 20 °C, with c = 4184 J/(kg K).
- 10 g of NaCl, about 0.17 mol/kg. This is an ILLUSTRATIVE kitchen amount; OSN gave none.
- The two salt quantities that decide the answer are uncertain, so they enter as RANGES, not as fixed values:
  - the apparent molar heat capacity φCp of NaCl in water: −95 to −40 J/(mol K), as a constant effective value;
  - the dissolving enthalpy at 20 °C: 3500 to 6000 J/mol.
- These ranges cover the tabulated values at infinite dilution and near 0.17 mol/kg. Sources are in
  `docs/preprint/salted_water_data.md`.

**Model assumptions (Spec.lean).**
- The pot has one temperature.
- The stove delivers a constant power P, and the pot loses heat at k·(T − 20 °C). No evaporation before boiling. The
  pot's own heat capacity is ignored.
- The salt waits at room temperature and dissolves at once when added.
- The brine heat capacity is constant within each choice of data. That is a simplification, which is why the data
  enter as ranges.
- "Boiled" means the brine reaches its own boiling point, about 0.18 °C above 100 °C. Pure water cannot get past 100
  °C, so the salt must go in before then.

**The physics in one line.** The energy needed is fixed by the start and end states, so the moment can matter only
through heat loss, and heat loss depends on the temperature on the way.
- Below a "neutral" temperature, adding room-temperature salt cools the water.
- Above it, the salt warms the water, because brine holds less heat per degree (φCp < 0).

**Formal statement.**
1. The temperature path solves the cooling law: a derivative statement.
2. The closed-form phase time is exactly when that path reaches its target.
3. Without heat loss the moment makes no difference.
4. At the neutral moment the salt changes nothing. Before it the salt cools the water; after it, it warms it.
5. With heat loss, the worst admissible moment is the neutral one (or just before boiling, if the neutral point
   lies above 100 °C), and the best is at one end.
6. If the salt cools the water at every temperature up to 100 °C (the neutral point lies above 100 °C), the best
   moment is the very start.

The stretch card `salted_water_negligible` adds the practical answer. For a 1–3 kW stove, losses up to 10 W/K and any
data in the ranges, any two moments give times within three seconds of each other. A numerical check over the
ranges gives at most 2.5 s; with central values it is under half a second.

**Which end wins, by the data.** It depends on where the neutral point lies.
- At infinite dilution, the temperature-dependent tables put it at about 87 °C, so either end could be best.
- At a kitchen concentration of about 0.17 mol/kg, the same tables give no neutral point below 100 °C. Then item 6
  applies: put the salt in first.
- These data estimates are outside Lean. A constant 25 °C φCp would wrongly suggest 74 °C.

**What Lean checks / does not check.** It checks the calculus and the inequalities, for every power, every loss rate
and every data value in the ranges. It does not check the ranges themselves, ideal mixing and instant dissolving, or
the neglect of the pot and of evaporation.

**Relevance.** This is a common kitchen question. The folk answers ("add it at the end, salt raises the boiling
point" or "add it early, it boils faster") both miss the point: the effect is at most a few seconds.

**Why small.** One linear ODE and logarithms. The worst-moment statement needs a real derivative-sign argument, and
the three-second bound needs log inequalities that hold uniformly over the data ranges.
