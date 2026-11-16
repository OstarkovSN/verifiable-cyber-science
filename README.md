# VerifiableCyberScience research harness

Local scientist-agent runs with Lean proof checking, assumption extraction and inspectable attempt logs. This is the existing research harness source, not an installable browser or CLI plugin package.

## Setup

Install Python 3 and the requirements with `python3 -m pip install -r requirements.txt`. Install elan, then run `lake update` and `lake exe cache get`. Lean and Mathlib versions are pinned in `lean-toolchain`, `lakefile.toml` and `lake-manifest.json`.

Use your own normal Claude Code or Codex CLI login. This code does not include credentials. The recorded agent models and CLI versions are in `agents/config.json`; those historical pins must be reviewed against your installed versions before new runs.

## Commands

- `python3 src/vas_agent.py --help`: run an agent on a task in an isolated git worktree and retain its attempts.
- `python3 src/vas_check.py --help`: check submitted proofs and record Lean output and added assumptions.
- `python3 src/vas_extract.py --help`: extract assumptions and theorem statements for review.
- `python3 src/vas_trail.py --help`: generate the proof-attempt report.
- `python3 tools/readable_agent_traces.py`: export saved agent transcripts from `artifacts/vas-agent-runs` as readable HTML. Raw transcripts are supplied separately and are not included in this repository.

The code accepts a proof only after its configured checks, including a separate kernel recheck. Conditional results list added assumptions. A researcher still judges whether definitions, assumptions and conclusions express the intended scientific question. The proposed end-to-end experiment workflow and the older task-card runs are different stages of the project.

## Controls

`python3 -m unittest discover -s tests -p 'test_vas_check.py' -v` runs checker controls, including deliberately invalid and conditional proofs. `python3 -m unittest discover -s tests -p 'test_vas_extract.py' -v` exercises extraction. These require the pinned Lean libraries and can be slow.

This private source snapshot excludes unpublished paper text, credentials, session metadata and raw agent transcripts. Original code provenance is recorded in `SOURCE.json`.

## Balls protocol v1 (new workflow)

This workflow implements an agent-written Bayesian model, rather than the fixed
cards used for the original paper runs. It has **not** been run on the scientific
balls task. The protocol contains the user's question and instructions, with no
preset prior, parameters, worked solution or expected answer.

From this checkout, `uv sync --group dev` installs the locked Python dependencies.
Docker, the existing native Codex **0.166.0** subscription login, Lean **4.35.0**,
and the pinned Mathlib cache are prerequisites. The launcher uses the locally
available image ID
`sha256:c0e8df9380519cf514d5fbb5aeaa7aa5de5f32c50330badcadc05cdabaae5566`
(`python:3.13-slim` when tested); it never pulls an image automatically.

When a scientist run is authorized, this single command starts it:

```sh
uv run vcs-protocol start --run-dir artifacts/balls/run-001 --library-root /path/to/pinned-cache-checkout
```

`--library-root` defaults to this checkout. It must have `.lake/packages` built
against the exact release `lake-manifest.json`. On the implementation machine,
`/home/claude/lair/vas` has that cache. Only package build libraries are mounted,
not that checkout's tasks, proofs, instructions, artifacts or source history.
The installed native binary is discovered from the normal npm Codex installation;
`--codex-binary` can supply its path explicitly. `--auth-file` defaults to the
normal CLI's `CODEX_HOME/auth.json` or `~/.codex/auth.json`.

The scientist has a fresh, temporary HOME in Docker. Selected harness files,
protocol, Lean installation, native libraries and Codex binary are read-only;
only its run workspace is writable. No host home, global configuration,
repository checkout, previous task cards, other run, Docker socket or secret
environment variable is mounted. The normal native auth **file alone** is mounted
read-only because the native client requires the existing subscription login.
It is not scientific evidence; credentials are never copied or logged. The native
client checks the login type before starting; API-key fallback is refused.
Expired credentials or token refresh that requires writing the read-only file
must be repaired using the normal host login, then the run resumed. The scientist
container has network access for its subscription client; this is a filesystem
boundary, not a network destination firewall or a sandbox against a malicious
Docker administrator. No additional agents or paid services are started.

The process stops for input or review. These operations do not launch inference:

```sh
uv run vcs-protocol status artifacts/balls/run-001
uv run vcs-protocol respond artifacts/balls/run-001 --request-id REQUEST_ID --response-file response.txt --source 'citation, method or human clarification'
uv run vcs-protocol review artifacts/balls/run-001 --decision reject --binding HASH_FROM_STATUS --reason 'Explain the scientific issue'
uv run vcs-protocol review artifacts/balls/run-001 --decision accept --binding HASH_FROM_STATUS --reason 'Record the human judgment'
```

After supplying input or rejecting a candidate, `uv run vcs-protocol resume
artifacts/balls/run-001` launches a fresh scientist context with the preserved
history and feedback. A rejected candidate must be revised. Run directories are
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
The roles `model`, `update` and `prediction` must name distinct actual theorems,
but their scientific substance cannot be certified by their names: the human
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
```

The opt-in controls exercise real Docker visibility and the native client's
version command, then real Lean/kernel/extraction checks for valid, invalid,
axiom-dependent and `sorry`-dependent files. The small positive control verifies
the checking machinery; it is explicitly not a scientific balls proof.
