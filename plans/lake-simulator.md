# Lake simulator implementation plan

1. Read primary sources for survey motivation; document the fixed fictional lake and explicitly separate designer truth from observations.
2. Implement one authoritative Python world specification, deterministic independent observation streams, habitat/eDNA/sonar/camera/calibration methods, and a Click interface.
3. Keep exports free of hidden counts, identities, seeds and nuisance parameters. Write operator receipts with source/config/output hashes outside the export directory. Refuse output reuse.
4. Add focused pytest controls for fixed truth, method/design validity, repeatability, absent-taxon panels, controls and output separation. Generate and inspect an ignored example bundle.
5. Run an independent fleet-reviewer pass over the actual CLI outputs, fix material findings, record learnings, and commit explicit deliverables/tests/plan only. Do not deliver survey responses or resume scientist runs.
