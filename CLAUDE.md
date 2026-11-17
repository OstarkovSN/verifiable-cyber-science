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
- Every `_execute_once`, including resume and automatic retries, must recheck the selected client's subscription login (`ChatGPT` for Codex, `claude.ai` for Claude) and validate prior attempt bindings and decision receipts; mounted auth and reviewed evidence can change during pauses.
- Claude Code 2.1.325 `--bare` disables OAuth/keychain authentication; subscription runs use a fresh HOME, `--setting-sources project,local` and `--strict-mcp-config` instead (`vcs_protocol.scientist_command`).
- With `CLAUDE_CONFIG_DIR` set, fresh onboarding preferences belong at `$CLAUDE_CONFIG_DIR/.claude.json`; `src/protocol_entrypoint.sh` symlinks only the read-only credential file to `$CLAUDE_CONFIG_DIR/.credentials.json`, without copying host profile state.
- Claude stream-json may exit zero for `error_max_turns` or client errors; `vcs_protocol.claude_result_failure` requires successful `type=result`, `subtype=success`, `is_error=false` completions; background-tool notifications may produce multiple completions for the same session, but any failed result, mixed session or structured auth/quota error stops the run.
- `vcs_matrix.job_command` passes `--expected-task-sha256` and `--expected-instructions-sha256` into each child; `vcs_protocol.freeze_protocol` checks the exact bytes it freezes, closing the mutation window after parent input verification.
- `vcs_protocol.client_failure_kind` must inspect native auth/quota metadata even on exit zero before checking a candidate; `vcs_matrix.run_queue` blocks queued jobs for that client on those failures, independently of other clients.
- Token-refresh errors against intentionally read-only credentials are authentication failures requiring owner login repair; `client_failure_kind` must ignore ordinary scientific/tool text mentioning authentication or quota.
- `tests/test_custom_protocol.py:custom_run` scopes setup-only `runtime_config` stubs with `monkeypatch.context()` so opt-in Docker visibility checks use the real pinned native runtime.
- Matrix children can exit zero with `scientist_failed`, `awaiting_input` or `awaiting_review`; read host-owned `control/state.json` through `current_state`/`status_result` to identify checkpoints, which still require explicit human scientific review.
- `lake.py:calibration_data` camera false-positive trials are per taxon × size bin: a Poisson false-count rate λ corresponds to at-least-one probability `1 - exp(-λ)` in that same observation unit.
- `lake.py:write_export` includes the export path in operator receipt identity while keeping replayed observation bytes identical; survey IDs change observations over one fixed truth, whose fingerprint and per-export output hashes remain operator-only.
- Root-level operator module `lake.py` is outside pytest's `src/` import path; `tests/test_lake.py` loads it with `importlib.util.spec_from_file_location` without changing runtime packaging or global `PYTHONPATH`.
