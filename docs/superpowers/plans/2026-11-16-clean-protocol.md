# Clean protocol implementation plan

Goal: make the approved human-in-the-loop workflow the only active workflow in the private repository, preserving all Git history and the original lair/vas historical evidence.
Spec: user-approved natural-language task/instructions and methods paragraph; human rejection revises model/assumptions/conclusions/proof. User explicitly says remove legacy from current tree, not Git history; no scientist runs yet.
Architecture: retain tested new Codex/Docker runner at 88facd2 and necessary hardened verification mechanisms, separate those into aptly named modules without obsolete fixed-card entrypoints. Single uv command starts the run to an explicit human checkpoint. Full protocol is plain language and provider-agnostic; implementation docs explicitly say Codex is currently supported.
Tech: uv, click, pytest, Docker, Lean/Mathlib pinned.

### Task 1: cleanup and document current tree
Files: README.md, PROTOCOL.md, protocols/v1, src, tests, tools, agents, tasks, tasks-drafts, SOURCE.json, requirements.txt.
1. Identify runtime dependencies of vcs_protocol.py. Remove obsolete fixed-card runner, old prompts/config, old solved task cards/proofs, unused Lean preludes, old reporting scripts/controls and snapshot metadata from current release tree only. Use ordinary git deletion; no reset, rebase, history rewrite, or changes to /home/claude/lair/vas evidence.
2. Retain hardened compiler/axiom/extractor functionality actually used by the new runner. Rename/refactor vas_check/vas_extract to current-specific modules, removing obsolete fixed-card check/load_task/lint/CLI and unused source. Update imports/tests/mount allowlists. Do not weaken checking or add new restrictions as a side effect.
3. Write clean PROTOCOL.md faithful to approved scheme: natural task, agent proposes model and distinguishes facts/choices; tools incl Internet; additional information requests; iterate real Lean feedback; mechanically extract/recheck assumptions/definitions and exact conclusions; human accepts/rejects; rejection causes revision; every artifact and decision retained. No completed-science claim, no unnecessary compulsory request, no claim of Claude support. Versioned scientist instructions and task must be discoverable. Avoid prior answers/family leaking to scientist.
4. Rewrite README around only current setup/commands, stop points, normal own-auth exception and supported limits. No legacy workflow instructions or old entrypoint commands. Retain versioned dependency pins and uv.lock; remove obsolete requirements if redundant.
5. Run full current pytest controls including real Docker and Lean checks; run CLI help; verify deleted legacy entrypoints/task directories absent, no imports still refer to them. Commit explicit paths only. Do not push; report files/tests/commit.
Record learnings to learnings/learnings-clean-protocol.md using the surfacing-subagent-learnings skill.

After implementation: independent task and whole-branch review, fixes and learnings curation; push only after checks. No scientist model inference or legacy project activity.
