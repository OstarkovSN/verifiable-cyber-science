namespace Task
/-! Model. Source: OSN's question in the external_v1 deck; this card is the balls_draws card with the prior's
  parameters derived instead of assumed (OSN, TG 4952-4954): the person reads as few assumptions as possible, and the
  parameters become an intermediate result that Lean proves from them.
  Unknown: K, the INITIAL number of black balls in the box, 0 <= K <= 50.
  Observation: 50 balls in the box; the first ten draws were all black, and those ten stay out (forty remain).
  Assumption A1 (GIVEN by the person who starts the agent): across boxes like this one, the black share K/50 has mean
  3/4 and standard deviation 1/10; this box is one of them.
  Assumption A2 (ADDED by the agent, a modelling choice): the prior for K is beta-binomial with some positive
  parameters alpha and beta. Its mass, mean and variance below are computed from the mass function, not quoted.
  Assumption A3 (GIVEN): what was seen, ten black draws.
  Assumption A4 (ADDED): the draws are the function `drawOne` below; every probability of a draw is computed from it.
  Assumption A5: Bayes' rule, written out as `bayesPrediction`.
  Every sum below runs over all 51 possible counts. -/
def initialTotal : Nat := 50
def blackDrawn : Nat := 10
def populationMean : Rat := 3/4
def populationSD : Rat := 1/10

/-- A kernel-efficient binomial coefficient, not a table of precomputed answers. -/
def choose (n k : Nat) : Nat :=
  if k <= n then n.factorial / (k.factorial * (n-k).factorial) else 0

/-- Rising factorial x (x+1) ... (x+n-1). -/
def risingQ (x : Rat) : Nat → Rat
  | 0 => 1
  | n+1 => risingQ x n * (x + n)

def counts : List Nat := List.range (initialTotal+1)
def sumR (f : Nat → Rat) : Rat := (counts.map f).foldr (· + ·) 0

/-- A2: the beta-binomial mass of K = k with parameters alpha, beta. -/
def priorMass (α β : Rat) (k : Nat) : Rat :=
  (choose initialTotal k : Rat) * risingQ α k * risingQ β (initialTotal - k) / risingQ (α + β) initialTotal

/-- Mean and variance of the share K/50 under that prior, computed from the mass function. -/
def priorMean (α β : Rat) : Rat := sumR (fun k => priorMass α β k * ((k : Rat) / initialTotal))
def priorVariance (α β : Rat) : Rat :=
  sumR (fun k => priorMass α β k * ((k : Rat) / initialTotal) ^ 2) - priorMean α β ^ 2

/-- A1 and A2 together: the family's mean and SD are the given ones. -/
def matchesGiven (α β : Rat) : Prop :=
  0 < α ∧ 0 < β ∧ priorMean α β = populationMean ∧ priorVariance α β = populationSD ^ 2

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

/-- A5, Bayes' rule over all 51 counts: P(eleventh black and seen) / P(seen). -/
def bayesPrediction (α β : Rat) : Rat :=
  sumR (fun k => priorMass α β k * seenThenBlack k) / sumR (fun k => priorMass α β k * likelihood k)

/-! Intermediate and conclusions. -/
/-- intermediate I1: the given mean and SD fix the family's parameters, alpha = 21.3 and beta = 7.1 -/
def goal_parameters_from_moments : Prop :=
  ∀ α β : Rat, matchesGiven α β → α = 213 / 10 ∧ β = 71 / 10
/-- from the draw function: ten black draws from a box with k black balls have probability C(k,10)/C(50,10) -/
def goal_ten_black_probability : Prop :=
  ∀ k ∈ counts, likelihood k = (choose k blackDrawn : Rat) / choose initialTotal blackDrawn
/-- from the draw function: after ten black draws, the next ball is black with probability (k-10)/40 -/
def goal_next_black_given_count : Prop :=
  ∀ k ∈ counts, blackDrawn ≤ k →
    seenThenBlack k = likelihood k * (((k - blackDrawn : Nat) : Rat) / (initialTotal - blackDrawn : Nat))
/-- main conclusion: for the family with the given mean and SD, the next draw is black with probability 313/384 -/
def goal_next_black_probability : Prop :=
  ∀ α β : Rat, matchesGiven α β → bayesPrediction α β = 313 / 384
end Task
