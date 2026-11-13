# Sudoku (pure logic)

**Question (OSN, external_v1 deck).** Does this Sudoku have exactly one solution? The puzzle is the first example of
https://leetcode.com/problems/sudoku-solver/description/ .

**Input.** The 81 cells as given in Spec.lean; 0 marks a blank.

**Rules (Spec.lean).** Every value is in 1..9, and no two different cells in the same row, column or 3x3 box hold
the same value.

**Formal statement.** There is exactly one board that follows the rules and agrees with the givens. The agent has to
find that board and also prove that no other board works, for every possible board, not just the ones a solver
happened to try.

**What Lean checks / does not check.** Lean checks existence and uniqueness. It does not check that the puzzle was
copied correctly from the source; a person compares the grid.

**Relevance.** This is the deck's introductory example of a claim that is easy to state and tedious to check by
hand. It has no physical assumptions at all.

**Why small.** It is one finite puzzle, but uniqueness needs a real argument: propagation lemmas proved sound, not a
solver's report.
