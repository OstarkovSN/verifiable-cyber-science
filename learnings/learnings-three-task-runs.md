
## Runtime reviewer
- Matrix hashes must travel into child launch arguments and be checked against the exact bytes frozen by the child; parent-only prelaunch hashing leaves a runtime-preflight mutation window between paired runs.
- Native auth/quota metadata must be classified even when the client process exits zero; otherwise an old candidate can be checked and same-client queued jobs can launch after a terminal subscription error.
- Native token-refresh failures against intentionally read-only credentials require owner login repair and belong to the authentication stop condition; ordinary tool/scientific text must not trigger that classifier.

## Implementer
- Custom snapshot tests that stub runtime_config during setup must restore it before opt-in Docker visibility probes; otherwise the probe silently uses the mock runtime rather than the pinned native environment.
- Matrix child exit codes alone do not describe checkpoints: vcs-protocol may exit zero with scientist_failed, awaiting_input or awaiting_review, so the queue must read the host-owned terminal state and keep scientific acceptance separate.
