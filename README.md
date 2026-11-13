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
