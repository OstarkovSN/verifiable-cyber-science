-- only one of the four required theorems
theorem balanced_example : goal_balanced_example := by
  unfold goal_balanced_example Task.Balanced
  omega
