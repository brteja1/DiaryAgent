# AGENTS

## Purpose and authority

Operational guidance for coding agents in this repository. Diary Agent is a local-first Python CLI for Markdown capture, persistent TODOs, day viewing/tagging and local-model-assisted search.

Subject to direct user instructions, [docs/Specification.md](docs/Specification.md) is the authoritative behavior contract (D-10). Read its applicable IDs and decision/implementation status before editing. [docs/Requirements.md](docs/Requirements.md) is a feature index; [docs/Design.md](docs/Design.md) describes architecture; [README.md](README.md) covers setup/use. They do not define competing requirements. [docs/Future.md](docs/Future.md) contains nonbinding proposals.

## Current work status

D-01 through D-12 are decided in specification v1.0. D-07's mandatory bundled HTFS integration is implemented and tested. D-01, D-04–06, D-08–09 and D-11–12 have implementation gaps recorded in the specification/design. Passing regressions do not establish full conformance.

Follow the decided contract when fixing an affected workflow, rather than treating a known contradiction as a requirement. Keep changes reviewable and identify the pending target they address.

## Module boundaries

- `diary_agent.py`: CLI routing, orchestration and the current domain/storage object.
- `diary_agent_app/core.py`: config/parsing I/O, date/TODO helpers, retrieval and shortlisting.
- `diary_agent_app/models.py`: shared records.
- `diary_agent_app/llm.py`: calls/prompts for LLM-01's five tasks.
- `diary_agent_app/htfs_adapter.py`: the only HTFS integration boundary.
- `diary_agent_app/ui.py`: editor, dialogs, viewer, picker and completion.
- `tests/test_diary_agent.py`: regressions and backend integration.

## Editing workflow

- Prefer the smallest change satisfying the applicable clauses. Avoid abstractions unless they reduce real complexity.
- Preserve module boundaries, readable Markdown and the stable CLI entrypoint. Identity/storage migrations require an explicit contract change.
- Keep strict date validation under DATA-04; do not accept unrelated formats silently.
- Read CAP-04/06/10–13 before capture changes: D-01 consent/verbatim behavior is not implemented everywhere.
- Read DATA-07–09 and VIEW-08–09 before section changes: unique targets and unrelated-byte preservation are decided obligations.
- Read PERSIST-01–05 and TAG-07 before tag replacement/deletion/cancellation changes. Never conflate cancelled and accepted-empty.
- Follow TODO-02/08 for D-11: generated TODO dates use `DD-MM-YYYY`, while existing values and verbatim text are preserved. This does not change diary filename/day-input syntax. Date expansion requires an accepted LLM proposal for an open task; generated priorities are low/medium/high and invalid legacy metadata stays unvalidated.
- Follow TODO-03/09/10 for D-12: unattended `todos` only lists; invalid/out-of-range input changes no tasks; verify affected-file snapshots and selected raw tasks before writing, rejecting stale selections for refresh/reselection.
- Do not reintroduce removed features: an automatic progress screen between two editors or LLM reorganization in the viewer. Follow the capture/viewer contracts.
- Preserve explicit user control. Roadmap ideas do not authorize automatic tagging, new LLM tasks, background content edits or unrelated features.
- Delete dead code/superseded tests after replacement behavior is covered. Historical tests can encode implementation gaps; update them to approved behavior rather than weakening the contract.

## Mandatory HTFS

The pinned `deps/HTFS` submodule supplies the backend:

```bash
git submodule update --init --recursive
```

Use its Python API through the adapter, following DEP-01–02 and [docs/HTFS.md](docs/HTFS.md). Do not discover a `tagfs` executable or restore external checkout/config/environment overrides. Keep diary metadata separate from dependency source. Do not edit upstream files or advance the pin incidentally; explicit updates require integration verification.

## UI and LLM guidance

- Keep prompt_toolkit event-loop-safe. Suspend display for subsidiary prompts and use thread mode when synchronous prompts run from an active asyncio context.
- Execute model work off the active UI loop. Handle read-only transitions, unlock after failure and keep toolbar hints accurate and nonduplicated.
- Keep calls/prompts in the LLM module and use callbacks at the UI boundary. LLM-01 is the allowed task inventory.
- Use target-day history as context, not material to restate. CAP-03 governs heading cleanup/nested bullets; D-01 requires consent to the complete resulting proposal.

## Verification and documentation

Update `tests/test_diary_agent.py` when behavior changes. Use focused assertions for outcomes and preserved data in capture, navigation, TODOs, storage and backend failures. Run at least:

```bash
python -m py_compile diary_agent.py diary_agent_app/core.py diary_agent_app/llm.py diary_agent_app/ui.py
pytest -q tests/test_diary_agent.py
```

For changed contracts/encodings, update model/review and regenerate evidence:

```bash
python3 scripts/specification/check_consistency.py --output docs/specification/evidence.json
```

For an authorized behavior change, update the specification first, then its requirements index and README. Update Design when boundaries/flows change. Keep approved target, current implementation and evidence separate. Reference IDs instead of duplicating long normative passages. Record unresolved product choices rather than inventing assumptions to make a check pass.
