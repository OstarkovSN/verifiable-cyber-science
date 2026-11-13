# Balls in a box (Bayesian statistics)

**Real-world question (OSN, external_v1 deck).** "I have withdrawn 10 black balls from a box potentially containing
black and white ones. There are 50 balls in the box in total. In general, such boxes contain black and white balls in
proportion of 3:1 with SD of 0.1. How do I estimate the probability of withdrawing a black ball from the same box
next using Bayesian statistics?"

**Measurements.** 50 balls; the first ten draws were black, and they stay out.

**Model assumptions (Spec.lean).** These are the deck's reading, carried over unchanged.
- "3:1" means a mean black fraction of 3/4.
- "SD 0.1" is the SD of K/50 across boxes, where K is the box's number of black balls.
- This box is a typical box.
- The prior family is beta-binomial with alpha = 21.3 and beta = 7.1. Those are the values that give exactly the
  stated mean and SD. The family itself is a modelling choice: the two moments do not determine it.
- Draws are uniform without replacement, so the likelihood of ten blacks is C(K,10)/C(50,10).
- Every sum runs over all 51 possible values of K.

**Formal statement.**
- The prior has the stated mean and SD.
- The posterior predictive probability that the next ball is black is exactly 313/384 (about 0.815).
- The shortcut formula agrees with the direct Bayes formula.
- A second prior with the same mean and SD gives a different answer. This shows the family is an assumption.

**What Lean checks / does not check.** It checks the exact Bayes computation, done with exact fractions and
including every case. It does not check the reading of "3:1 with SD 0.1", the prior family, or the sampling
protocol.

**Relevance.** This is the textbook Bayesian update, and the deck's opening example.

**Why small.** Finite sums with exact rational arithmetic. It shows how the conclusion depends on the assumptions;
it is not hard mathematics.
