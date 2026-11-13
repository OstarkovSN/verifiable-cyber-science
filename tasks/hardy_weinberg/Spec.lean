namespace Task
/-! Model (assumptions, reviewed by a person, not proved):
  one autosomal locus with two alleles A and a; a large population; random mating; no selection, mutation,
  migration or drift; generations do not overlap. x, y, z are the frequencies of the genotypes AA, Aa, aa.
  The frequency of allele A is x + y/2, because AA carries two copies and Aa one. -/
noncomputable def alleleA (x y z : ℝ) : ℝ := x + y / 2
/-- random union of gametes: offspring genotype frequencies from parental genotype frequencies -/
noncomputable def nextAA (x y z : ℝ) : ℝ := (alleleA x y z) ^ 2
noncomputable def nextAa (x y z : ℝ) : ℝ := 2 * alleleA x y z * (1 - alleleA x y z)
noncomputable def nextaa (x y z : ℝ) : ℝ := (1 - alleleA x y z) ^ 2

/-! Data (an ILLUSTRATIVE sample of 1000 genotyped individuals, not a published data set) and the test convention:
  Pearson's statistic with expected counts from the sample allele frequency; the 5 % critical value of chi-square with
  1 degree of freedom, 3.841, is taken from tables (a stated constant, not proved here). -/
def obsAA : ℚ := 298
def obsAa : ℚ := 489
def obsaa : ℚ := 213
def total : ℚ := obsAA + obsAa + obsaa
def pHat : ℚ := (2 * obsAA + obsAa) / (2 * total)
def expAA : ℚ := total * pHat ^ 2
def expAa : ℚ := total * 2 * pHat * (1 - pHat)
def expaa : ℚ := total * (1 - pHat) ^ 2
def chiSq : ℚ := (obsAA - expAA) ^ 2 / expAA + (obsAa - expAa) ^ 2 / expAa + (obsaa - expaa) ^ 2 / expaa
def chiCrit : ℚ := 3841 / 1000

/-! Conclusions (the target statements). -/
def goal_allele_conserved : Prop := ∀ x y z : ℝ, x + y + z = 1 →
  alleleA (nextAA x y z) (nextAa x y z) (nextaa x y z) = alleleA x y z
def goal_offspring_sum_one : Prop := ∀ x y z : ℝ, x + y + z = 1 → nextAA x y z + nextAa x y z + nextaa x y z = 1
/-- equilibrium after one generation: a second round of random mating changes nothing -/
def goal_equilibrium_after_one_generation : Prop := ∀ x y z : ℝ, x + y + z = 1 →
  nextAA (nextAA x y z) (nextAa x y z) (nextaa x y z) = nextAA x y z ∧
  nextAa (nextAA x y z) (nextAa x y z) (nextaa x y z) = nextAa x y z ∧
  nextaa (nextAA x y z) (nextAa x y z) (nextaa x y z) = nextaa x y z
def goal_sample_chi2_below_critical : Prop := chiSq < chiCrit
end Task
