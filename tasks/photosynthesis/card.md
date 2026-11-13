# Photosynthesis stoichiometry (chemistry / plant biology)

**Real-world question.** What is the balanced overall equation of photosynthesis? How much sugar does a plant fix per
kilogram of CO₂ it takes up?

**Measurements.** The standard atomic weights of C, H and O (IUPAC conventional values).

**Model assumptions (Spec.lean).**
- The net reaction is CO₂ + H₂O → glucose + O₂. This is an idealisation: real plants make many products, and
  photorespiration loses carbon.
- Atoms are conserved element by element.

**Formal statement.**
- 6 CO₂ + 6 H₂O → C₆H₁₂O₆ + 6 O₂ is balanced.
- Every balanced choice of whole-number coefficients is a multiple of it, so the equation is unique up to scale.
- Mass is conserved.
- 682–683 g of glucose are fixed per kg of CO₂.

**What Lean checks / does not check.** It checks the integer linear algebra and the exact arithmetic. It does not
check that plants follow the net equation, or the values of the atomic weights.

**Relevance.** The carbon budget of plants and crop yield estimates rest on this equation, and every chemistry
course starts from equation balancing.

**Why small.** Linear equations over ℕ (decidable by `omega`) plus rational arithmetic. A minimal "natural law →
conclusion" demo.
