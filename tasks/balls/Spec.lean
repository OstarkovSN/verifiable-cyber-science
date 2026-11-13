namespace Task
/-! Model (assumptions, reviewed by a person, not proved). Source: OSN's question in the external_v1 deck.
  Unknown: K, the INITIAL number of black balls in the box, 0 <= K <= 50.
  Observation: 50 balls in the box; the first ten draws were all black, and those ten stay out (forty remain).
  Reading of "3:1 with SD 0.1": the mean black FRACTION across boxes is 3/4, and the SD 0.1 is the SD of K/50 across
  boxes (not an uncertainty about the mean). This box is representative of those boxes.
  Prior FAMILY (a modelling choice; the two moments alone do not fix it): beta-binomial for K, with
  alpha = a/d = 21.3 and beta = b/d = 7.1, the values that give exactly the stated mean and SD of K/50.
  Draws are uniform, without replacement, and colour does not affect which ball is drawn.
  Every sum below runs over all 51 possible counts. -/
/-! Observations, and explicit model premises. -/
def initialTotal : Nat := 50
def blackDrawn : Nat := 10
def whiteDrawn : Nat := 0
def populationMean : Rat := 3/4
def populationSD : Rat := 1/10

/-- Chosen finite beta-binomial prior: alpha=a/d, beta=b/d. -/
def a : Nat := 213
def b : Nat := 71
def d : Nat := 10

/-! Counting, prior, likelihood, Bayes update, prediction (definitions only). -/

/-- A kernel-efficient binomial coefficient, not a table of precomputed answers. -/
def choose (n k : Nat) : Nat :=
  if k <= n then n.factorial / (k.factorial * (n-k).factorial) else 0


def rising (start step : Nat) : Nat → Nat
  | 0 => 1
  | n+1 => rising start step n * (start + step*n)

def priorWeight (aa bb dd k : Nat) : Nat :=
  choose initialTotal k * rising aa dd k * rising bb dd (initialTotal-k)

def counts : List Nat := List.range (initialTotal+1)
def sumOver (f : Nat → Nat) : Nat := (counts.map f).sum
def priorNormalizer (aa bb dd : Nat) : Nat := rising (aa+bb) dd initialTotal
def priorMass (aa bb dd k : Nat) : Rat :=
  (priorWeight aa bb dd k : Rat) / priorNormalizer aa bb dd

/-- Uniform sampling without replacement; all ten observations were black. -/
def likelihood (k : Nat) : Rat :=
  (choose k blackDrawn : Rat) / choose initialTotal blackDrawn

/-- Unnormalized Bayes weights; omitted factors are constant in K. -/
def posteriorWeight (aa bb dd k : Nat) : Nat :=
  priorWeight aa bb dd k * choose k blackDrawn
def evidenceWeight (aa bb dd : Nat) : Nat := sumOver (posteriorWeight aa bb dd)
def posteriorMass (aa bb dd k : Nat) : Rat :=
  (posteriorWeight aa bb dd k : Rat) / evidenceWeight aa bb dd
def remainingTotal : Nat := initialTotal - blackDrawn - whiteDrawn
def nextGivenCount (k : Nat) : Rat := ((k-blackDrawn : Nat) : Rat) / remainingTotal
def sumR (f : Nat → Rat) : Rat := (counts.map f).foldr (· + ·) 0
def evidence (aa bb dd : Nat) : Rat :=
  sumR (fun k => priorMass aa bb dd k * likelihood k)
/-- Direct finite Bayes formula: joint event probability divided by evidence. -/
def bayesPrediction (aa bb dd : Nat) : Rat :=
  sumR (fun k => priorMass aa bb dd k * likelihood k * nextGivenCount k) /
    evidence aa bb dd
def remainingBlackMoment (aa bb dd : Nat) : Nat :=
  sumOver (fun k => posteriorWeight aa bb dd k * (k-blackDrawn))

/-- E[(K-10)/40 | ten black draws], using the entire discrete posterior. -/
def predictive (aa bb dd : Nat) : Rat :=
  (remainingBlackMoment aa bb dd : Rat) /
    ((remainingTotal : Rat) * evidenceWeight aa bb dd)

def priorMean (aa bb dd : Nat) : Rat :=
  (sumOver (fun k => priorWeight aa bb dd k * k) : Rat) /
    ((initialTotal : Rat) * priorNormalizer aa bb dd)
def priorVariance (aa bb dd : Nat) : Rat :=
  (sumOver (fun k => priorWeight aa bb dd k * k*k) : Rat) /
    ((initialTotal : Rat)^2 * priorNormalizer aa bb dd) - (priorMean aa bb dd)^2

/-! A second prior with the same two moments, to show the family is a real assumption. -/
def otherPrior (k : Nat) : Rat :=
  if k = 25 then 1/32 else if k = 35 then 11/16 else if k = 45 then 9/32 else 0
def meanOf (prior : Nat → Rat) : Rat := sumR (fun k => (k : Rat) / initialTotal * prior k)
def varianceOf (prior : Nat → Rat) : Rat :=
  sumR (fun k => ((k : Rat) / initialTotal - meanOf prior)^2 * prior k)
def otherPrediction : Rat :=
  sumR (fun k => otherPrior k * likelihood k * nextGivenCount k) /
    sumR (fun k => otherPrior k * likelihood k)

/-! Conclusions. -/
/-- the chosen prior has exactly the stated mean fraction and SD -/
def goal_prior_matches_moments : Prop :=
  sumOver (priorWeight a b d) = priorNormalizer a b d ∧ priorMean a b d = populationMean ∧
    priorVariance a b d = populationSD ^ 2
/-- the Bayes posterior predictive probability that the next draw is black -/
def goal_next_black_probability : Prop := bayesPrediction a b d = 313 / 384
/-- the shortcut formula (posterior mean of the remaining black fraction) agrees with the direct Bayes formula -/
def goal_shortcut_matches_bayes : Prop := predictive a b d = bayesPrediction a b d
/-- the moments do not determine the answer: another prior with the same mean and SD predicts differently -/
def goal_moments_do_not_fix_prediction : Prop :=
  sumR otherPrior = 1 ∧ meanOf otherPrior = populationMean ∧ varianceOf otherPrior = populationSD ^ 2 ∧
    otherPrediction ≠ bayesPrediction a b d
end Task
