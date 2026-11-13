namespace Task
/-! Model (assumptions, reviewed by a person, not proved). Source: OSN's Sudoku in the external_v1 deck, the first
  example at https://leetcode.com/problems/sudoku-solver/description/ . Cells are numbered 0..80 row by row; 0 marks a
  blank in the puzzle. The rules: every value is in 1..9, and no two different cells that share a row, a column or a
  3x3 box hold the same value. Since each such unit has nine cells, these are the usual Sudoku rules.
  The puzzle (dots are blanks):
    5 3 . . 7 . . . .
    6 . . 1 9 5 . . .
    . 9 8 . . . . 6 .
    8 . . . 6 . . . 3
    4 . . 8 . 3 . . 1
    7 . . . 2 . . . 6
    . 6 . . . . 2 8 .
    . . . 4 1 9 . . 5
    . . . . 8 . . 7 9 -/
abbrev Board := Fin 81 → Nat
def row (i : Fin 81) : Nat := i.val / 9
def col (i : Fin 81) : Nat := i.val % 9
def box (i : Fin 81) : Nat := i.val / 27 * 3 + i.val % 9 / 3
abbrev Peer (i j : Fin 81) : Prop := row i = row j ∨ col i = col j ∨ box i = box j
abbrev Valid (board : Board) : Prop :=
  (∀ i, 1 ≤ board i ∧ board i ≤ 9) ∧
  (∀ i j, i ≠ j → Peer i j → board i ≠ board j)
def puzzle : Board := fun i =>
  ([5, 3, 0, 0, 7, 0, 0, 0, 0, 6, 0, 0, 1, 9, 5, 0, 0, 0, 0, 9, 8, 0, 0, 0, 0, 6, 0, 8, 0, 0, 0, 6, 0, 0, 0, 3, 4, 0, 0, 8, 0, 3, 0, 0, 1, 7, 0, 0, 0, 2, 0, 0, 0, 6, 0, 6, 0, 0, 0, 0, 2, 8, 0, 0, 0, 0, 4, 1, 9, 0, 0, 5, 0, 0, 0, 0, 8, 0, 0, 7, 9] : List Nat)[i.val]!
abbrev MatchesGivens (board : Board) : Prop :=
  ∀ i, puzzle i ≠ 0 → board i = puzzle i
abbrev Solves (board : Board) : Prop := Valid board ∧ MatchesGivens board

/-! Conclusion. -/
/-- the puzzle has exactly one solution (the agent must find it and prove that no other board works) -/
def goal_exactly_one : Prop := ∃! board : Board, Solves board
end Task
