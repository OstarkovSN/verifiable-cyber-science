
## Fleet reviewer
- Camera false-positive calibration must retain the taxon×size-bin observation unit: per-bin Poisson false counts correspond to an at-least-one trial probability of 1-exp(-rate), not an unlabeled per-species video probability.
- Observation replay can share one fixed truth fingerprint across survey IDs while retaining separate, verified per-export output hashes; keep that evidence in operator receipts rather than researcher exports.

## Implementer
- The operator-only lake.py lives at repository root while pytest config adds only src/; focused tests load the root module explicitly with importlib rather than changing runtime packaging or global PYTHONPATH.
- Deterministic survey replays to different export paths need separate operator receipt identities; export-path metadata belongs in receipt hashing, never in observation bytes.
