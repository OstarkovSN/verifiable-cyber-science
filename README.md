# VerifiableCyberScience

Human-in-the-loop Bayesian modeling and Lean verification. The complete workflow is in [PROTOCOL.md](PROTOCOL.md). Scientist instructions and the natural-language task are versioned in [protocols/v1](protocols/v1).

## Setup and operation

The scientist proposes and revises its own Bayesian model. Every candidate requires explicit human review; successful Lean checking does not constitute human scientific acceptance. The protocol contains the user's question and instructions, with no
preset prior, parameters, worked solution or expected answer.

From this checkout, `uv sync --group dev` installs the locked Python dependencies.
Docker, Lean **4.35.0**, the pinned Mathlib cache and an existing native
subscription login are prerequisites. Both Codex **0.166.0** and Claude Code
**2.1.325** are supported; the default client remains Codex. The launcher uses the locally
available image ID
`sha256:c0e8df9380519cf514d5fbb5aeaa7aa5de5f32c50330badcadc05cdabaae5566`
(`python:3.13-slim` when tested); it never pulls an image automatically.

When a scientist run is authorized, this single command starts it:

```sh
uv run vcs-protocol start --run-dir artifacts/balls/run-001 --library-root /path/to/pinned-cache-checkout
```

Choose `--agent codex` (default) or `--agent claude`. The requested model defaults
to `gpt-6.1-sol` for Codex and `claude-sonnet-5-5` for Claude, with `medium`
reasoning. Override with `--model` and `--reasoning-effort`; the client, version,
binary path and hash, requested model and effort are recorded in run state and
review provenance. Client or quota errors stop the workflow.

For an authorized independent Claude run:

```sh
uv run vcs-protocol start --agent claude --run-dir artifacts/balls/claude-run-001 --library-root /path/to/pinned-cache-checkout --model claude-sonnet-5-5 --reasoning-effort medium --initial-feedback-file human-clarification.txt
```

`--initial-feedback-file` is optional and available only for a fresh run. Its exact
UTF-8 text is copied into host `control/initial-feedback.txt`, hashed and appended
to each scientist prompt as human task clarification. It carries no proof approval;
changing the host copy blocks continuation. To keep independent runs independent,
supply current human instructions without previous scientist solutions.

Custom natural-language questions use `--task-file` and `--instructions-file` on
`vcs-protocol start`. Either option may be supplied; the missing input defaults
to its v1 file. Custom runs freeze the exact UTF-8 bytes as
`control/protocol/task.txt` and `instructions.txt`, record source paths and SHA256
hashes, and use those verified snapshots for every prompt and resume. Live source
edits do not change a run; snapshot edits stop it before inference. Only those
two files are mounted read-only at `/protocol`; neighboring tasks, source metadata
and other host control files remain outside the container. Existing v1 runs keep
their original defaults and live-v1 hash checks. V1 scientific instructions are
unchanged. `--memory` (default `8g`, range `128m`–`8g`) and `--cpus` (default `2`,
range `0.1`–`8`) apply to both scientist and independent checker containers and
appear in runtime provenance.

The finite matrix runner takes exactly three `*.txt` question files and launches
one fresh Codex and one fresh Claude run per question. The first wave covers all
three questions with Codex; the Claude runs follow as queue slots open. The models are pinned to
`gpt-6.1-sol` and `claude-sonnet-5-5`, both at `medium` effort. Preview without
creating files or invoking Docker or either client:

```sh
uv run vcs-matrix --task-dir protocols/v2/tasks --instructions-file protocols/v2/instructions.txt --run-root artifacts/three-tasks/run-001 --library-root /path/to/pinned-cache-checkout --max-concurrent 3 --memory 4g --cpus 2 --dry-run
```

For an authorized launch, remove `--dry-run`. The runner refuses an existing
run root. At most three jobs run concurrently, with configured totals capped at
12 GiB memory and six CPUs. Each run's checker uses that same job's slot and
limits. The matrix freezes its inputs once, and passes their expected hashes to
each child so paired runs cannot silently receive different question bytes.
No scientist receives another task, run, answer or previous scientist feedback.

`matrix.json` records the six exact commands, input hashes, per-job exit codes,
current protocol status, requests and review packets. `matrix.log` records queue
events; `logs/JOB.log` retains each child's combined CLI output. Each run under
`runs/JOB` also retains its raw scientist traces and checking evidence. Input and
review checkpoints free a queue slot; **awaiting_review is not scientific
acceptance**. The queue never answers requests, makes reviews or resumes a run.
Use `vcs-protocol status`, `respond`, `review` and explicit `resume` on the
individual run paths after inspecting the manifest.

Authentication and quota errors stop new jobs for that client; its unfinished
jobs remain `queued` with a block reason. Already-running jobs finish normally,
and the other client's eligible jobs continue. Tool, checking and other per-job
failures remain visible without cancelling sibling jobs. There is no automatic
retry of a failed client, API fallback or owner login repair. The matrix exits
nonzero if any job failed or a client requires owner action. Interruption stops
active child processes and their containers and preserves unstarted queue entries.
It runs once, with six jobs and a nine-hour maximum per job; it installs no service.

`--library-root` defaults to this checkout. It must have `.lake/packages` built
against the exact release `lake-manifest.json`. Only package build libraries are mounted,
not that checkout's tasks, proofs, instructions, artifacts or source history.
For Codex, the native CLI and its `codex-code-mode-host` terminal companion are
mounted together and their hashes recorded. The binary is discovered from the
normal npm installation; `--codex-binary` can supply its path explicitly.
`--auth-file` defaults to `CODEX_HOME/auth.json` or `~/.codex/auth.json`.

For Claude, `--claude-binary` supplies the standalone native executable; by
default it is resolved from `claude` on PATH. `--auth-file` defaults to
`~/.claude/.credentials.json`. The credentials file alone is mounted read-only at
`/native-auth/claude-credentials.json` and symlinked into the fresh
`CLAUDE_CONFIG_DIR=/home/scientist/.claude`. A minimal onboarding config is created
there with non-account preferences. Host `~/.claude.json`, settings, plugins,
agent definitions, global instructions and home directories are never mounted.
Each cycle checks native `claude auth status --json` for `loggedIn: true` and
`authMethod: claude.ai`; API-key and third-party auth are refused. Claude runs with
project/local settings only, strict MCP config, no session persistence, an
explicit built-in tool list excluding agents, and a limit of 80 turns. No
`--bare` or fallback-model option is used. Stream result errors, auth/quota errors,
turn-limit results and missing successful terminal results stop even on exit zero.

The scientist has a fresh, temporary HOME in Docker. Selected harness files,
protocol, Lean installation, native libraries and selected client binary are read-only;
only its run workspace is writable. No host home, global configuration,
repository checkout, previous task cards, other run, Docker socket or secret
environment variable is mounted. The normal native auth **file alone** is mounted
read-only because the native client requires the existing subscription login.
It is not scientific evidence; credentials are never copied or logged. The native
client checks the login type before every cycle; API-key fallback is refused.
Expired credentials or token refresh that requires writing the read-only file
must be repaired using the normal host login, then the run resumed. The scientist
container has network access for its subscription client; this is a filesystem
boundary, not a network destination firewall or a sandbox against a malicious
Docker administrator. No additional agents or paid services are started.

Real host verification errors or incomplete submissions automatically return feedback to a fresh scientist context, for at most three cycles per start/resume invocation. The feedback and traces are retained. Exhausting this bound stops for explicit resume; client failures never retry automatically.

The process stops for input or review. These operations do not launch inference:

```sh
uv run vcs-protocol status artifacts/balls/run-001
uv run vcs-protocol respond artifacts/balls/run-001 --request-id REQUEST_ID --response-file response.txt --source 'citation, method or human clarification'
uv run vcs-protocol review artifacts/balls/run-001 --decision reject --binding HASH_FROM_STATUS --reason 'Explain the scientific issue'
uv run vcs-protocol review artifacts/balls/run-001 --decision accept --binding HASH_FROM_STATUS --reason 'Record the human judgment'
```

After supplying input or rejecting a candidate, `uv run vcs-protocol resume
artifacts/balls/run-001` launches a fresh scientist context with the preserved
history and feedback. Resume selects the recorded client; an optional `--agent`
must match it. A rejected candidate must be revised. Run directories are
never reused by `start`. Quota or authentication failures stop the workflow;
there is no paid fallback.

`control/` is host-managed and never mounted in the scientist container. It holds
raw CLI traces, request/response provenance, attempt lineage and frozen submitted
proofs, narratives and manifests. When the scientist exits, a separate container
with no network or authentication independently checks the frozen proof, audits
axioms, runs `leanchecker`, extracts dependencies and exact theorem statements,
then independently compiles and compares the extraction. Each attempt's
`packet.json`, `verification/extracted.lean`, `verification/extracted.json`,
`verification/lean.log` and `checker-trace.log` are the review material. A review
binding hashes **every** attempt artifact. Content changes invalidate that
binding; `status` also checks the decision receipt. The frozen attempt is the
approved result, even if the scientist's working draft later changes.

Both added axioms and `sorry` produce **proved_if**, including unused additions.
Human acceptance retains that conditional verdict. Checker errors, missing
reports and timeouts never become a proof or an accepted scientific result.
The conclusion manifest names one or more distinct actual final theorems; supporting model and update results may remain intermediate lemmas. Scientific substance cannot be certified by theorem names: the human
must reject arithmetic-only, irrelevant or misleading formalizations and inspect
facts versus choices and external evidence. There is no automatic acceptance.

The Lean interface accepts one file with at most 24,000 UTF-8 bytes of proof
body and deliberately restricts executable metaprogramming and custom syntax. Native Mathlib tactics remain available. Conclusions use
`theorem name : statement := proof`, with all binders after the colon; project
imports and namespaces are unsupported. These restrictions are surfaced as actual
checker errors, not silently replaced with a different model or theorem.

Controls (mock candidates, never scientist inference):

```sh
uv run pytest tests/test_protocol.py -q
VCS_TEST_LIBRARY_ROOT=/path/to/pinned-cache-checkout uv run pytest tests/test_protocol.py -q
VCS_TEST_LIBRARY_ROOT=/path/to/pinned-cache-checkout VCS_TEST_CLAUDE=1 uv run pytest -q
```

The opt-in controls exercise real Docker visibility and native client version
commands, stdin transport, Claude profile/auth-file isolation and subscription
status metadata (without printing account fields), then real Lean/kernel/extraction checks for valid, invalid,
axiom-dependent and `sorry`-dependent files. The small positive control verifies
the checking machinery; it is explicitly not a scientific balls proof.
