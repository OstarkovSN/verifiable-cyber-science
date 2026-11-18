Supplementary information preparation

supplementary-information.txt is the editable prose source for the SI methods and eight reviewed results. The DOCX export is an editing copy generated under artifacts/si; the text source remains in Git.

inputs/ contains exact frozen task and instruction files for eight selected runs, plus the initial clarification supplied to the Claude balls run. input-manifest.json records their SHA-256 hashes. Repeated files are retained per run so the mapping is explicit.

run-inventory.json is the completion snapshot for the eight selected runs. It records model requests, client versions, resource settings, checking-source hashes and every frozen attempt's formal verdict and review decision. Attempt bindings, decision receipts and all frozen input hashes were checked during export. Four results were personally accepted by the user; four were reviewed by the orchestrating assistant under explicit user delegation. The generic human_decision field preserves the harness schema; the review_authority and decision reasons identify who actually reviewed each accepted result.

The selected evidence package is generated under artifacts/si. It contains original accepted proofs, reports, manifests, checker/extraction records and decisions, plus frozen inputs and synthetic lake observations. An attributed reading copy and editorial diff correct two prose errors in the Claude lake report while preserving its original report and proof. A file-hash manifest and archive readback verify the delivered subset. The original full-attempt bindings refer to the complete host records and cannot be recomputed from this subset alone.

Native credentials, account metadata, raw provider sessions and the hidden simulator census are excluded. The full raw experiment records and literature custody receipts remain preserved separately. Publication preparation still needs a portable container specification and final data/code availability. Simulated observations, chosen scenario assumptions and physical measurements remain distinguished throughout the supplement.
