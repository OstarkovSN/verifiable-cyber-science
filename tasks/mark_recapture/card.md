# Mark–recapture estimate of a fish population (ecology)

**Real-world question.** How many fish live in a lake? Fishery biologists mark M fish, release them, later catch C
fish and count the R marked ones among them. This is the setting of the existing carp demo, recast as the standard
field method.

**Measurements.** M = 50, C = 40, R = 7. The numbers are ILLUSTRATIVE.

**Model assumptions (Spec.lean).**
- The population is closed between the two samples.
- The marked fish mix completely, every fish is equally catchable, and marks are not lost.
- The second sample is drawn without replacement.
- These assumptions make R hypergeometric in N.

**Formal statement (Verify.lean).** Over all integer population sizes consistent with the data, the likelihood has a
unique maximum at N = 285. That value is the integer part of the Lincoln–Petersen ratio MC/R = 285.7.

**What Lean checks / does not check.** It checks that 285 is the exact maximiser of the stated likelihood, over
infinitely many candidate N, not only a scanned range. It does not check the ecological assumptions. In real lakes,
trap-shyness, mortality and immigration violate them; that is where the reviewer looks. It also does not claim that
the maximum-likelihood estimate is a good estimator (it is biased; Chapman's correction exists).

**Relevance.** Lincoln–Petersen and its variants are the standard abundance estimators in ecology and fisheries.

**Why small.** It needs one ratio identity for binomial coefficients, L(N+1)/L(N) = (N+1−M)(N+1−C)/((N+1)(N+1−M−C+R)),
and a monotonicity argument. This is harder than Hardy–Weinberg, so it tests whether the agent can handle a genuine
argument over all N.
