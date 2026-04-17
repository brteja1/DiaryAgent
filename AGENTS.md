# AGENTS

## Purpose

This file gives coding agents project-specific guidance for working in this repository.
It should be treated as the operational companion to `README.md`, `docs/Requirements.md`, and `docs/Design.md`.

## Project Summary

Diary Agent is a local-first Python CLI for:

- capturing diary updates into daily Markdown files
- managing persistent TODOs across diary history
- showing and navigating stored day entries
- searching diary history with a local Ollama model

## Current Status

As of 2026-04-04, the implementation is aligned with the current requirements and the test suite is passing.

Recent fixes already verified:

- nested prompt_toolkit editor calls now run in thread mode when launched from an active asyncio context
- `show` tag editing now initializes the HTFS adapter before wiring `t`-key callbacks
- the current focused behavior is covered by `tests/test_diary_agent.py`

The current code lives primarily in:

- `diary_agent.py`
- `diary_agent_app/core.py`
- `diary_agent_app/llm.py`
- `diary_agent_app/ui.py`
- `tests/test_diary_agent.py`

## Architecture

- `diary_agent.py`
  CLI entrypoint, command routing, and the main `DiaryAgent` domain object.
- `diary_agent_app/core.py`
  Pure helpers for config parsing, tokenization, local retrieval, and shortlist logic.
- `diary_agent_app/htfs_adapter.py`
  Adapter for the HTFS (Hierarchical Tagging File System) backend, managing tag relationships and resource tagging.
- `diary_agent_app/llm.py`
  Ollama-backed synthesis, search answer generation, and TODO similarity checks.
- `diary_agent_app/ui.py`
  `prompt_toolkit` editor, dialogs, show-screen UI, and hierarchical tag selection.
- `docs/Requirements.md`
  Source of truth for implemented behavior.
- `docs/Design.md`
  Higher-level design description of the current implementation.

## Key Product Rules

- Daily diary files are stored as `dd_mm_yyyy.md`.
- Each appended capture is grouped under a time-only heading like `## 14:30`.
- In interactive capture:
  - the user edits in a single prompt_toolkit editor
  - `Alt+R` explicitly requests an LLM rewrite of the current buffer
  - the buffer is locked while rewrite is in progress
  - whatever is in the buffer when `Ctrl+D` is pressed is written verbatim
- After capture, the user is prompted to apply HTFS tags:
  - Tag suggestion is NOT automatic; the user must explicitly request suggestions using `Alt+S` in the editor.
  - Top-level tags are displayed for context.
  - Autocompletion supports both atomic tag names and full hierarchical paths.
  - New tags require explicit confirmation before creation.
- LLM-generated section headings must not be retained in rewritten capture output.
- Nested bullet hierarchy should be preserved when the LLM rewrite naturally contains sub-points.
- `show` is read-only and defaults to today when no date is provided.
- `show` supports:
  - `[` previous existing entry
  - `]` next existing entry
  - `g` fuzzy picker over existing entries
  - `Space` toggle TODO state
  - `e` edit the section under the cursor
  - `t` manage tags for the section under the cursor
- End-of-history navigation in `show` is a no-op, not an error.

## Editing Guidance

- Prefer changing the smallest surface that satisfies the requirement.
- Preserve the split of responsibilities across `diary_agent.py`, `core.py`, `htfs_adapter.py`, `llm.py`, and `ui.py`.
- Do not reintroduce removed features unless explicitly asked.
  Examples:
  - no automatic rewrite-progress screen between two editors
  - no LLM-based reorganize action in the show viewer
- Avoid adding new abstractions unless they reduce real complexity.
- Keep Markdown storage human-readable.
- Do not silently weaken validation for date input; explicit day input remains `dd_mm_yyyy` or a relative date integer like `-1`, `+1`, `0`.

## Tagging System (HTFS)

- Integration with HTFS is managed via `HTFSAdapter`.
- Tags are hierarchical and stored in an SQLite database (`.tagfs.db`) and an RDF Turtle file (`.tagfs.ttl`).
- Supported operations include:
  - Listing all tags and top-level tags.
  - Building full hierarchical paths (e.g., `Project/DiaryAgent`).
  - Suggesting tags based on section content using LLM.
  - Applying tags to specific diary sections (mapped as HTFS resources).
- All HTFS-related operations must be performed through the adapter to maintain boundary separation.

## UI Guidance

- Interactive editor behavior lives in `diary_agent_app/ui.py`.
- Keep prompt_toolkit interactions simple and event-loop-safe.
- Avoid nested prompt_toolkit applications inside an already running application.
- If background work updates UI state, be careful about read-only buffer transitions and timing.
- Toolbar messaging should reflect actual behavior and avoid duplicate hints.

## LLM Guidance

- Use Ollama only for the currently implemented tasks:
  - capture rewrite
  - TODO similarity decision
  - search answer synthesis
- Treat today's existing notes as context, not material to restate.
- The rewrite prompt must avoid headings and preserve bullet hierarchy when useful.
- Do not add new LLM tasks unless explicitly requested.

## Testing Expectations

- When behavior changes, update `tests/test_diary_agent.py`.
- Prefer focused tests for:
  - capture flow
  - show navigation
  - TODO handling
  - storage format
- Run at least:

```bash
python -m py_compile diary_agent.py diary_agent_app/core.py diary_agent_app/llm.py diary_agent_app/ui.py
pytest -q tests/test_diary_agent.py
```

- If docs behavior changes, update:
  - `README.md`
  - `docs/Requirements.md`
  - `docs/Design.md` when the implementation model changes materially

## Cleanup Guidance

- Prefer deleting dead code over leaving stale helpers behind.
- If a feature is no longer in the requirements, remove its code and tests unless there is a clear reason to keep it.
- Keep the implementation aligned with `docs/Requirements.md`.

## When Unsure

- Treat `docs/Requirements.md` as the behavior contract.
- Treat `docs/Design.md` as the current intended implementation model.
- Preserve user control in interactive flows.
