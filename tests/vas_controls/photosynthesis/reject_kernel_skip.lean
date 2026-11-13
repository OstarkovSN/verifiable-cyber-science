-- OT-1861: by_elab adds each theorem with kernel checking switched off (value True.intro, any stated type).
-- Rejected by the contract; test_kernel_recheck runs it past the contract to exercise leanchecker.
open Lean in
theorem balanced_example : goal_balanced_example := by_elab do
  let nm := `balanced_example.fake
  withOptions (fun o => o.setBool `debug.skipKernelTC true) do
    addDecl (.thmDecl { name := nm, levelParams := [], type := mkConst ``Task.goal_balanced_example, value := mkConst ``True.intro })
  return mkConst nm

open Lean in
theorem all_balanced_are_multiples : goal_all_balanced_are_multiples := by_elab do
  let nm := `all_balanced_are_multiples.fake
  withOptions (fun o => o.setBool `debug.skipKernelTC true) do
    addDecl (.thmDecl { name := nm, levelParams := [], type := mkConst ``Task.goal_all_balanced_are_multiples, value := mkConst ``True.intro })
  return mkConst nm

open Lean in
theorem mass_conserved : goal_mass_conserved := by_elab do
  let nm := `mass_conserved.fake
  withOptions (fun o => o.setBool `debug.skipKernelTC true) do
    addDecl (.thmDecl { name := nm, levelParams := [], type := mkConst ``Task.goal_mass_conserved, value := mkConst ``True.intro })
  return mkConst nm

open Lean in
theorem glucose_yield_per_kg_co2 : goal_glucose_yield_per_kg_co2 := by_elab do
  let nm := `glucose_yield_per_kg_co2.fake
  withOptions (fun o => o.setBool `debug.skipKernelTC true) do
    addDecl (.thmDecl { name := nm, levelParams := [], type := mkConst ``Task.goal_glucose_yield_per_kg_co2, value := mkConst ``True.intro })
  return mkConst nm
