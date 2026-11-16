# VerifiableCyberScience

Human-in-the-loop Bayesian modeling and Lean verification. The complete workflow is in [PROTOCOL.md](PROTOCOL.md). Scientist instructions and the natural-language task are versioned in [protocols/v1](protocols/v1).

## Setup and operation

The scientist proposes and revises its own Bayesian model. Every candidate requires explicit human review; successful Lean checking does not constitute human scientific acceptance. The protocol contains the user's question and instructions, with no
preset prior, parameters, worked solution or expected answer.

From this checkout, `uv sync --group dev` installs the locked Python dependencies.
Only the native Codex launcher is implemented; there is no Claude launcher. Docker, the existing native Codex **0.166.0** subscription login, Lean **4.35.0**,
and the pinned Mathlib cache are prerequisites. The launcher uses the locally
available image ID
`sha256:c0e8df9380519cf514d5fbb5aeaa7aa5de5f32c50330badcadc05cdabaae5566`
(`python:3.13-slim` when tested); it never pulls an image automatically.

When a scientist run is authorized, this single command starts it:

```sh
uv run vcs-protocol start --run-dir artifacts/balls/run-001 --library-root /path/to/pinned-cache-checkout
```

The requested model defaults to `gpt-6.1-sol` with `medium` reasoning. Override with `--model` and `--reasoning-effort`; both are recorded in run state and review provenance. Subscription authentication and provider availability are checked by an authorized run; client or quota errors stop the workflow.

`--library-root` defaults to this checkout. It must have `.lake/packages` built
against the exact release `lake-manifest.json`. Only package build libraries are mounted,
not that checkout's tasks, proofs, instructions, artifacts or source history.
The native CLI and its `codex-code-mode-host` terminal companion are mounted together and their hashes recorded. The installed native binary is discovered from the normal npm Codex installation;
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
```

The opt-in controls exercise real Docker visibility and the native client's
version command, then real Lean/kernel/extraction checks for valid, invalid,
axiom-dependent and `sorry`-dependent files. The small positive control verifies
the checking machinery; it is explicitly not a scientific balls proof.
