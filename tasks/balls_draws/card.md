# Balls in a box, with the draws as a function (Bayesian statistics)

**Real-world question (OSN, external_v1 deck).** "I have withdrawn 10 black balls from a box potentially containing
black and white ones. There are 50 balls in the box in total. In general, such boxes contain black and white balls in
proportion of 3:1 with SD of 0.1. How do I estimate the probability of withdrawing a black ball from the same box
next using Bayesian statistics?"

**Why a second card.** In the `balls` card the sampling protocol ("uniform, without replacement") is a comment, and
the two probabilities that depend on it (ten black draws given K; next ball black given K) are definitions a reader
must check by hand. OSN (TG 4322): nothing in Lean depends on that comment. Here the protocol is a function,
`drawOne`, and both probabilities are computed from it and proved equal to the textbook formulas.

**Measurements.** 50 balls; the first ten draws were black, and they stay out.

**Model assumptions (Spec.lean).**
- "3:1" means a mean black fraction of 3/4; "SD 0.1" is the SD of K/50 across boxes; this box is a typical box.
- The prior family is beta-binomial with alpha = 21.3 and beta = 7.1 (a modelling choice; the moments do not fix it).
- `drawOne`: every ball still in the box is equally likely to be drawn, and the drawn ball is not put back.
- Every sum runs over all 51 possible values of K.

**Formal statement.**
- The prior has the stated mean and SD.
- From `drawOne`: ten black draws from a box with K black balls have probability C(K,10)/C(50,10), for every K.
- From `drawOne`: after those ten, the next ball is black with probability (K-10)/40, for every K >= 10.
- The posterior predictive probability that the next ball is black is exactly 313/384 (about 0.815).

**What Lean checks / does not check.** It checks the exact Bayes computation and that both draw probabilities follow
from `drawOne`. It does not check the reading of "3:1 with SD 0.1", the prior family, or that `drawOne` describes
how the balls were really drawn.

**Why small.** Finite sums and products with exact rational arithmetic.
