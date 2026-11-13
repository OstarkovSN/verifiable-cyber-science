import Mathlib.Tactic.Ring
namespace Lake
/-- fish caught per day -/
def catchRate : Nat := 12
structure Season where
  days : Nat
def summer : Season := ⟨90⟩
/-- only used inside a proof, so not an assumption -/
def helper (n : Nat) : Nat := n * 2
end Lake
open Lake
axiom onlyCarp : ∀ s : Season, s.days > 0
def totalCatch (s : Season) : Nat := catchRate * s.days
lemma helper_eq (n : Nat) : helper n = n + n := by unfold helper; omega
theorem summer_catch : totalCatch summer = 1080 ∧ summer.days > 0 := by
  have := helper_eq 3
  exact ⟨by decide, onlyCarp summer⟩
