# Hardy–Weinberg equilibrium (population genetics)

**Real-world question.** In a large, randomly mating population, do the genotype frequencies at one gene settle down,
and how fast? A related question: is an observed sample of genotypes consistent with that equilibrium?

**Measurements.** Genotype counts (AA, Aa, aa) in a sample. The counts here are ILLUSTRATIVE (298, 489, 213 out of 1000).
Real examples are MN blood-group surveys.

**Model assumptions (Spec.lean, for the reviewer).** One locus with two alleles. A large population. Random mating.
No selection, mutation, migration or drift. Non-overlapping generations. The offspring genotype frequencies are
p², 2pq, q², where p is the parental frequency of allele A. Data convention: Pearson's chi-square, and the 5% critical
value 3.841 for 1 degree of freedom is taken from tables.

**Formal statement (Verify.lean).**
- The allele frequency is conserved.
- The offspring frequencies sum to 1.
- From any starting genotype frequencies, the population reaches equilibrium after one generation of random mating:
  applying the map twice gives the same result as applying it once.
- For the sample, the chi-square statistic is below 3.841.

**What Lean checks / does not check.** It checks the algebra from the stated mating model, and the exact rational
arithmetic of the statistic. It does not check that a real population mates at random, that 3.841 is the right
quantile, or that a statistic below the critical value "confirms" equilibrium. The last is a statistical
interpretation, not a theorem.

**Relevance.** Hardy (1908) and Weinberg (1908) give the null model of population genetics. It is used for genotyping
quality control and to detect selection or population structure.

**Why small.** Polynomial identities over ℝ plus one rational computation. A good first demo.
