namespace Task
/-! Model (assumptions, reviewed by a person, not proved):
  a closed population of N fish in a lake (no births, deaths or migration between the two samples). M fish are
  caught, marked and released, and they mix completely. A second sample of C fish is drawn at random without
  replacement, and every fish is equally catchable; marks are not lost. Under these assumptions the number of marked
  fish in the second sample is hypergeometric: P(R | N) = choose(M, R) * choose(N - M, C - R) / choose(N, C).
  Data (ILLUSTRATIVE): M = 50 marked, C = 40 in the second sample, R = 7 of them marked. -/
def M : ℕ := 50
def C : ℕ := 40
def R : ℕ := 7
/-- likelihood of the observed recapture count as a function of the unknown population size N -/
def L (N : ℕ) : ℚ := ((Nat.choose M R : ℚ) * (Nat.choose (N - M) (C - R) : ℚ)) / (Nat.choose N C : ℚ)
/-- population sizes compatible with the data: at least the M marked plus the C - R unmarked fish seen -/
def Admissible (N : ℕ) : Prop := M + (C - R) ≤ N

/-! Conclusions: N = 285 is the unique maximum-likelihood population size, and it is the integer part of the
Lincoln-Petersen estimate M * C / R = 2000 / 7 = 285.7... -/
def goal_mle : Prop := ∀ N : ℕ, Admissible N → L N ≤ L 285
def goal_mle_unique : Prop := ∀ N : ℕ, Admissible N → N ≠ 285 → L N < L 285
def goal_lincoln_petersen_floor : Prop := (285 : ℚ) ≤ (M * C : ℚ) / R ∧ (M * C : ℚ) / R < 286
end Task
