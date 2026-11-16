# Project learnings

## Key Gotchas

- `vcs_extract.main` explicitly raises `SystemExit(0)` even with Click `standalone_mode=False`; `vcs_protocol.verify_candidate` catches it and still validates `extracted.json`.
- Docker creates bind-mount parents as root; keep native auth mounted at `/native-auth/auth.json` and symlink it into the independently writable fresh `$HOME/.codex`, as `src/protocol_entrypoint.sh` does.
- `vcs_protocol.native_codex` locates the standalone binary under `@openai/codex-linux-x64/vendor/*/bin/codex`; the npm `codex` entrypoint itself is a JavaScript wrapper unsuitable for the Python container.
- `--library-root` must match the release `lake-manifest.json` byte-for-byte; `docker_base` mounts only `.lake/packages/*/.lake/build/lib/lean`, keeping cache-checkout source and history outside the scientist container.
- `VAS_` markers in `src/vcs_lean.py` and `src/vcs_extract.py` preserve recorded evidence compatibility; they are reserved checker names despite the current `vcs_*` module names.
- Extraction identity must compare normalized complete kernel expressions and reached local declarations' types and values; pretty-printed statements and same-named proposition aliases can hide changes (`tests/test_extraction_identity.py`).
- `vcs_extract.run_lean` must map every nonzero `leanchecker` status to failure; signal statuses are negative, so adding an exit-code offset can accidentally produce success.
- Host writes into scientist-controlled `work/` need `directory_fd`/`atomic_write`: read-only container mounts and candidate-path checks do not prevent destination, parent-directory or predictable temporary-file symlink attacks.
- `execute_cycle` generates retry feedback under host-owned `control/feedback-NNN` first and copies only generated files into `work/check-feedback`; archiving agent-writable feedback can forge diagnostic provenance.
- Every `_execute_once`, including resume and automatic retries, must recheck explicit ChatGPT subscription login and validate prior attempt bindings and decision receipts; mounted auth and reviewed evidence can change during pauses.
