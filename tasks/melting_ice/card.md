# Melting floating ice (physics / climate)

**Real-world question.** When ice cubes melt in a glass, does the water level change? When floating sea ice or ice
shelves melt, does sea level change? And how much of an iceberg shows above the water?

**Measurements.** Densities: fresh water 1000, sea water 1027, glacier ice 917 kg/m³. These are typical values and
vary with temperature and salinity.

**Model assumptions (Spec.lean).**
- Archimedes' principle for a floating body.
- Mass is conserved on melting.
- The melt is fresh water.
- Volumes add on mixing. This is ideal mixing, and it is the assumption a physical-oceanography reviewer should
  question: the real rise is slightly different, because mixing fresh and salt water changes the volume.

**Formal statement.**
- In fresh water the level is unchanged.
- In any denser liquid the level rises.
- For sea water the rise is exactly 2.7% of the displaced volume, i.e. (1027 − 1000)/1000.
- Between 10% and 11% of an iceberg's volume is above the water line.

**What Lean checks / does not check.** It checks the algebraic chain from Archimedes to the sign and size of the
level change. It does not check the density values, the ideal-mixing assumption, or anything about grounded ice:
melting land ice raises sea level for a different reason.

**Relevance.** This is a common misconception ("melting sea ice does not raise sea level"). The sea-water correction
appears in the sea-level budget literature; the citation must be verified before use.

**Why small.** Field algebra with sign conditions. It is the most "everyday" of the candidates.
