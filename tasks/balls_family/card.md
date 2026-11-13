# Balls in a box, prior parameters derived (Bayesian statistics)

**Real-world question (OSN, external_v1 deck).** "I have withdrawn 10 black balls from a box potentially containing
black and white ones. There are 50 balls in the box in total. In general, such boxes contain black and white balls in
proportion of 3:1 with SD of 0.1. How do I estimate the probability of withdrawing a black ball from the same box
next using Bayesian statistics?"

**Why a third card.** In `balls_draws` the prior's parameters (alpha 21.3, beta 7.1) are assumptions, and a conclusion
only checks that they reproduce the stated mean and SD. OSN (TG 4952-4954): the mean and variance are the assumption
(given by the person who starts the agent), the beta-binomial family is a second assumption (added by the agent), and
the parameters are an intermediate result that follows from both. Keep the assumptions few, because they are what a
person checks.

**Measurements.** 50 balls; the first ten draws were black, and they stay out.

**Model assumptions (Spec.lean).**
- A1, given: the share K/50 has mean 3/4 and SD 1/10 across such boxes; this box is one of them.
- A2, added by the agent: the prior for K is beta-binomial with positive parameters alpha, beta (not given).
- A3, given: ten black draws, kept out.
- A4, added: `drawOne`: every ball still in the box is equally likely to be drawn; the drawn ball is not put back.
- A5: Bayes' rule over all 51 values of K.

**Formal statement.**
- Intermediate I1: any alpha, beta > 0 whose beta-binomial has the given mean and SD are alpha = 21.3, beta = 7.1.
- From `drawOne`: ten black draws given K have probability C(K,10)/C(50,10); the next ball is then black with
  probability (K-10)/40.
- Main: for any beta-binomial with the given mean and SD, the next ball is black with probability exactly 313/384.

**What Lean checks / does not check.** It checks that the parameters follow from the given moments, the draw
probabilities, and the exact Bayes computation. It does not check the reading of "3:1 with SD 0.1", the choice of
family, or that `drawOne` describes how the balls were really drawn.

**Why harder than balls_draws.** I1 is about all positive rational alpha, beta, so the 51-term sums cannot be
evaluated; the mean and variance must be proved in closed form (alpha/(alpha+beta) and the beta-binomial variance)
and the two equations solved.
