# Human-in-the-loop scientific protocol

1. The human supplies a scientific question in natural language, observations and available background information. The agent receives the question and scientist instructions as frozen, hashed input files. The default files are protocols/task-balls.txt and protocols/instructions.txt; --task-file and --instructions-file select other inputs.

2. The agent formulates a mathematical model. It distinguishes supplied facts from additional assumptions, definitions, modeling choices and external evidence. It prefers deriving model parameters from observations over choosing values that reproduce them. It states and justifies the model family and observation process. When the information does not identify a unique answer, it exposes the ambiguity and develops a scientifically useful conditional conclusion for human review.

3. The agent uses its workspace, shell commands, Internet research and Lean. It may request literature, calculations, experiments or clarification. A request stops execution until an operator supplies a response with provenance and explicitly resumes the run. Simulated data and calculations are identified as such; unperformed measurements cannot be reported as observations.

4. The agent writes a substantive Lean proof connecting supplied information and explicit modeling choices to the answer. Assumptions, scientifically meaningful definitions and final conclusions stay readable and direct. Derivable algebra, normalization, parameter calculations and technical details belong in intermediate lemmas or the proof. Scientific assumptions cannot be hidden in helpers, and arithmetic for a number obtained elsewhere cannot substitute for the scientific inference.

5. The agent invokes the check tool, reads the actual diagnostic output and revises its proof or model. Failed host checks and incomplete submissions can trigger up to three cycles per start or resume invocation. Client, authentication and quota failures stop execution. The record retains proof attempts and feedback.

6. The host freezes a submitted proof, narrative and conclusion manifest, then checks them in a separate container without network or credentials. Lean compiles the proof, an audit exposes added axioms and gaps, and a separate leanchecker process rechecks it. The extractor follows the exact conclusion declarations through local definitions and assumptions, writes a standalone review file, recompiles it and compares kernel expressions and reached declarations with the checked submission. Pinned imported libraries form the trust base.

7. The human receives the assumptions, necessary definitions, exact conclusions, scientific explanation, external sources and checking evidence. Successful formal checking does not replace this review. Added axioms or sorry produce the conditional verdict proved_if; other completed proofs receive proved. Missing, failed or interrupted checks do not establish a result.

8. The human accepts or rejects the frozen attempt with a reason. The decision refers to a hash binding of every attempt artifact, with a separately hashed decision receipt. Altering an artifact invalidates that decision. Rejection supplies feedback to revise the model, assumptions, conclusions or proof; explicit resume starts a fresh context with the run's work and recorded feedback. The agent cannot approve itself or resubmit an unchanged rejected candidate.

9. The host retains raw scientist traces, submitted proofs and reports, manifests, extraction and checking records, external responses with provenance, and human decisions. Request responses and reviews do not launch inference. A run's task and instruction snapshots remain fixed.

The scientist's filesystem contains its own work and the selected read-only tools and inputs. Host global instructions, other runs and repository contents are excluded. The native subscription credential file is mounted read-only for client authentication and excluded from scientific evidence. Network access supports the provider client and literature research. API-key fallback and additional scientist agents are disabled.

The supported Lean interface uses a single file with explicit Mathlib imports and a proof body of at most 24,000 UTF-8 bytes. Final conclusion declarations have their binders after the colon. Executable metaprogramming, custom syntax, namespaces, native_decide, IO and unsafe code are restricted; supported Mathlib tactics remain available. The checker reports unsupported constructs as errors.

The optional vcs-matrix command queues exactly three questions with both native clients, using frozen common inputs and independent workspaces. It stops each run at its input or review checkpoint. It never supplies answers, makes human decisions or resumes a run automatically. See [README.md](README.md) for commands, prerequisites and resource limits.
