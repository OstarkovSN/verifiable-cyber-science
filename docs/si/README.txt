Supplementary information preparation

supplementary-information.txt is the editable prose source for the first SI methods draft. The DOCX export is an editing copy generated under artifacts/si; the text source remains in Git.

inputs/ contains exact frozen task and instruction files for eight selected runs, plus the initial clarification supplied to the Claude balls run. input-manifest.json records their SHA-256 hashes. Repeated files are retained per run so the mapping is explicit.

run-inventory.json is a dated snapshot, not a live status display or final results table. It records model requests, client versions, resource settings when present, checking-source hashes and every frozen attempt's verification verdict and human review decision. Attempt bindings and decision receipts were rehashed during export. An accepted run has an explicit human acceptance; awaiting_review does not.

The export intentionally excludes native credentials, account metadata, host paths, raw provider sessions and the hidden simulator census. The full experiment records remain in their original host-managed run directories. This folder is not yet the complete reproducibility archive.

Remaining SI work: finalize the lake and salt reviews; package the chosen Lean proofs, extraction and checker records, external responses and decisions; add the portable container specification; and complete data/code availability. Preserve the distinction between simulated observations, chosen scenario assumptions and physical measurements throughout editing.
