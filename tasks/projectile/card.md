# OPTIONAL — projectile range, a chain of equation transformations (classical mechanics)

**Real-world question.** At what angle should a ball, a stone or a jet of water be thrown to go furthest on flat
ground, ignoring air drag? And how far does it go?

**Measurements.** None beyond the launch velocity and g. This is the "derivation" candidate OSN asked for (brief item 3).

**Model assumptions (Spec.lean).**
- A point mass in uniform gravity, with no air resistance, on flat ground.
- Newton's second law, with the stated accelerations.

**The chain the reviewer would otherwise re-derive by hand.**
1. The proposed trajectory satisfies Newton's law: derivatives in Lean, via `HasDerivAt`.
2. It is the only such motion with these initial conditions (a mean-value-theorem argument).
3. The landing time is 2 v_y/g.
4. The range is 2 v_x v_y/g.
5. The range is at most v²/g.
6. Equality holds exactly when v_x = v_y, i.e. at 45°.
7. The apex height is v_y²/(2g).

The reviewer checks the start (Newton plus the initial conditions) and the end (statements 4–7). Lean checks the
seven links in between.

**What Lean checks / does not check.** It checks every algebraic and calculus step from the stated model. It does
not check that drag is negligible. For a real ball it is not, and the true optimum is below 45°. That gap is the
point of separating the model from the derivation.

**Relevance / why optional.** It is textbook physics, so it is not a research result. It shows the "start / end
review" argument on a multi-step derivation that is still small. The kinetic-energy work (OT-1442) is the
heavier alternative. It is kept out of the preprint route, as the brief asks.
