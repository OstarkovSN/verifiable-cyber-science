namespace Task
/-! Model (assumptions, reviewed by a person, not proved). Source: OSN's question in the external_v1 deck; this card
  is the balls card with the sampling protocol written as code (OSN, TG 4322), not as a comment.
  Unknown: K, the INITIAL number of black balls in the box, 0 <= K <= 50.
  Observation: 50 balls in the box; the first ten draws were all black, and those ten stay out (forty remain).
  Reading of "3:1 with SD 0.1": the mean black FRACTION across boxes is 3/4, and the SD 0.1 is the SD of K/50 across
  boxes (not an uncertainty about the mean). This box is representative of those boxes.
  Prior FAMILY (a modelling choice; the two moments alone do not fix it): beta-binomial for K, with
  alpha = a/d = 21.3 and beta = b/d = 7.1, the values that give exactly the stated mean and SD of K/50.
  The draws are the function `drawOne` below; every probability of a draw is computed from it.
  Every sum below runs over all 51 possible counts. -/
/-! Observations, and explicit model premises. -/
def initialTotal : Nat := 50
def blackDrawn : Nat := 10
def populationMean : Rat := 3/4
def populationSD : Rat := 1/10

/-- Chosen finite beta-binomial prior: alpha=a/d, beta=b/d. -/
def a : Nat := 213
def b : Nat := 71
def d : Nat := 10

/-! Counting and prior (definitions only). -/

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
def sumR (f : Nat → Rat) : Rat := (counts.map f).foldr (· + ·) 0
def priorNormalizer (aa bb dd : Nat) : Nat := rising (aa+bb) dd initialTotal
def priorMass (aa bb dd k : Nat) : Rat :=
  (priorWeight aa bb dd k : Rat) / priorNormalizer aa bb dd

/-! The draws (an assumption, written as code). -/

/-- The balls still in the box. -/
structure Box where
  black : Nat
  white : Nat

def total (box : Box) : Nat := box.black + box.white

/-- One draw. Every ball still in the box is equally likely to be picked, so the drawn ball is black with probability
  (black balls left)/(balls left). The drawn ball is not put back: the box afterwards has one ball fewer of that
  colour. Each entry is (probability, colour drawn, box afterwards); `true` means black. -/
def drawOne (box : Box) : List (Rat × Bool × Box) :=
  [((box.black : Rat) / total box, true, ⟨box.black - 1, box.white⟩),
   ((box.white : Rat) / total box, false, ⟨box.black, box.white - 1⟩)]

/-- Probability that successive draws from `box` show exactly the colours `seq`, in that order. -/
def probSeq : Box → List Bool → Rat
  | _, [] => 1
  | box, c :: rest =>
    ((drawOne box).map (fun e => if e.2.1 = c then e.1 * probSeq e.2.2 rest else 0)).foldr (· + ·) 0

/-- The box before any draw, if it held k black balls. -/
def boxWith (k : Nat) : Box := ⟨k, initialTotal - k⟩
/-- What was seen: ten draws, all black. -/
def observed : List Bool := List.replicate blackDrawn true

/-- Probability of what was seen, given k black balls at the start. -/
def likelihood (k : Nat) : Rat := probSeq (boxWith k) observed
/-- Probability of what was seen AND a black eleventh ball, given k black balls at the start. -/
def seenThenBlack (k : Nat) : Rat := probSeq (boxWith k) (observed ++ [true])

/-- Bayes' rule over all 51 counts: P(eleventh black and seen) / P(seen). -/
def bayesPrediction (aa bb dd : Nat) : Rat :=
  sumR (fun k => priorMass aa bb dd k * seenThenBlack k) / sumR (fun k => priorMass aa bb dd k * likelihood k)

def priorMean (aa bb dd : Nat) : Rat :=
  (sumOver (fun k => priorWeight aa bb dd k * k) : Rat) /
    ((initialTotal : Rat) * priorNormalizer aa bb dd)
def priorVariance (aa bb dd : Nat) : Rat :=
  (sumOver (fun k => priorWeight aa bb dd k * k*k) : Rat) /
    ((initialTotal : Rat)^2 * priorNormalizer aa bb dd) - (priorMean aa bb dd)^2

/-! Conclusions. -/
/-- the chosen prior has exactly the stated mean fraction and SD -/
def goal_prior_matches_moments : Prop :=
  sumOver (priorWeight a b d) = priorNormalizer a b d ∧ priorMean a b d = populationMean ∧
    priorVariance a b d = populationSD ^ 2
/-- from the draw function: ten black draws from a box with k black balls have probability C(k,10)/C(50,10) -/
def goal_ten_black_probability : Prop :=
  ∀ k ∈ counts, likelihood k = (choose k blackDrawn : Rat) / choose initialTotal blackDrawn
/-- from the draw function: after ten black draws, the next ball is black with probability (k-10)/40 -/
def goal_next_black_given_count : Prop :=
  ∀ k ∈ counts, blackDrawn ≤ k →
    seenThenBlack k = likelihood k * (((k - blackDrawn : Nat) : Rat) / (initialTotal - blackDrawn : Nat))
/-- the Bayes posterior predictive probability that the next draw is black -/
def goal_next_black_probability : Prop := bayesPrediction a b d = 313 / 384
end Task
