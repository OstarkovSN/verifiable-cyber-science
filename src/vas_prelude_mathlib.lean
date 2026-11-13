import Mathlib.Data.Nat.Choose.Basic
import Mathlib.Data.Nat.Factorial.Basic
/- VAS prelude: fixed definitions the verifier puts before every agent model. Reviewed once by a human;
   the agent cannot change them. Counting comes from Mathlib: Nat.choose n k (ways to choose k of n things),
   Nat.descFactorial n k (ordered choices of k of n) and Nat.factorial n.
   P k is the probability that exactly k of the next 5 fish are carp. -/

/-- The distribution of the number of carp among the next 5 fish, as a list for k = 0..5. -/
def VAS.dist (P : Nat → Rat) : List Rat := [P 0, P 1, P 2, P 3, P 4, P 5]

/-- The expected number of carp among the next 5 fish. -/
def VAS.mean (P : Nat → Rat) : Rat := 0 * P 0 + 1 * P 1 + 2 * P 2 + 3 * P 3 + 4 * P 4 + 5 * P 5
