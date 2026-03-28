# Diary Agent Design

## Overview

The diary agent is a local-first Python CLI for capturing daily notes, managing persistent TODOs, and querying diary history using a locally reachable Ollama model. It is designed around three primary workflows:

- capture a free-form daily update and append a polished Markdown entry
- review and complete open TODO items across diary history
- search historical diary content with a natural-language question

The implementation lives in [diary_agent.py](/linuxdev/code_snippets/diary_agent/diary_agent.py).

## Design Goals

- Keep diary storage outside the source tree and make it user-configurable.
- Use a local terminal workflow without requiring a GUI application.
- Preserve diary continuity by conditioning new note generation on today's existing file.
- Keep TODO handling persistent across all diary files, not just the current day.
- Reduce accidental TODO duplication with deterministic filtering, semantic similarity checks, and LLM-based TODO classification.
- Degrade clearly when dependencies or local model connectivity are missing.
- Work with or without prompt_toolkit (CLI fallbacks for both editor and TODO prompts).

## High-Level Architecture

The system is intentionally implemented as a single-file CLI with small internal layers:

1. Configuration layer
2. Core diary domain logic
3. LLM integration
4. Terminal interaction layer
5. CLI entrypoint and command routing

This keeps deployment simple while still separating concerns inside the code.

## Configuration Model

The diary path is not derived from the project directory. Instead, startup requires:

- `~/.config/diary_agent/config.txt`

Current supported config entries:

- `diary_path=/path/to/Diary`
- `llm_model=model_name_available_in_ollama`

Startup behavior:

- If the config file exists and contains both `diary_path` and `llm_model`, those values are used.
- If the config file is missing or invalid and the process is interactive, the user is prompted to populate it.
- If the config file is missing or invalid and the process is non-interactive, startup fails with a clear runtime error.

This design allows the code and the diary data to live independently.

## Storage Design

The configured diary directory contains one Markdown file per day:

- `dd_mm_yyyy.md`

Properties:

- The directory is created lazily on demand.
- The current day's file is created only when something is appended.
- Existing content is preserved and new entries are appended with blank-line separation.
- Duplicate entries (both TODOs and regular notes) are filtered out before appending.

The system treats all `*.md` files in the configured diary directory as part of history for TODO scanning and search.

## Core Domain Objects

The implementation currently uses three small data objects:

- `PendingTask`
  - represents an unchecked task line and its source file/line
- `SimilarTodoMatch`
  - represents a new candidate TODO and the existing open TODO it resembles
- `AppConfig`
  - represents resolved user configuration, currently `diary_dir` and `llm_model`

These objects are deliberately narrow and map directly to operational workflows.

## Capture Flow

The capture path is the default CLI behavior.

### Interactive Path (with prompt_toolkit)

1. Resolve config.
2. Ensure the diary storage directory exists.
3. Open a multiline `prompt_toolkit` editor.
4. Submit the current buffer with `Ctrl+D`.
5. Send the raw text to Ollama for Markdown bullet generation.
6. Remove duplicate entries deterministically (both TODOs and regular notes).
7. Review semantically similar TODOs against unresolved historical tasks.
8. Append the surviving entry to today's file.
9. If open TODOs exist, ask whether the user wants to see them.
10. If the user says yes, open the TODO checklist and allow completion updates.

### CLI Fallback Path (without prompt_toolkit)

1. Resolve config.
2. Ensure the diary storage directory exists.
3. Prompt for input via stdin (empty line or Ctrl-D to finish).
4. Send the raw text to Ollama for Markdown bullet generation.
5. Remove duplicate entries deterministically.
6. Review semantically similar TODOs against unresolved historical tasks.
7. Append the surviving entry to today's file.
8. If open TODOs exist, prompt `y/N` to show them.
9. If yes, show numbered list and allow selecting to mark complete.

### Non-Interactive Path

The `capture --text "..."` path skips the editor and uses the provided text as input. Similar TODO confirmations fall back to a plain CLI prompt when stdin is a TTY. In fully scripted mode, similar TODOs are skipped automatically.

## LLM Integration

The system uses Ollama for four separate tasks.

Model selection comes from the config file by default, with `--model` available as an explicit runtime override.

### 1. Diary Entry Synthesis

Input:

- timestamp
- today's existing diary context
- raw user update

Output:

- concise Markdown bullet points

The prompt instructs the LLM to:

- preserve factual content
- keep continuity with today's notes
- decide semantically whether items are TODOs or regular notes
- format actionable items as TODO checkboxes
- avoid headings or commentary
- avoid repeating unresolved TODOs already in the diary

### 2. TODO Classification

For programmatic classification needs, the `classify_as_todo()` function uses LLM inference to determine whether text represents an actionable TODO or a regular note. Returns `YES` or `NO`.

### 3. TODO Similarity Decision

For each candidate unchecked TODO that survives exact dedupe, the system can ask Ollama whether it is effectively the same unresolved task as an existing open TODO. The model is instructed to answer only `YES` or `NO`.

This is used as a second-stage filter after lexical shortlisting.

### 4. History Answer Synthesis

For natural-language search, the system retrieves candidate text excerpts first and only then asks Ollama to answer based on those excerpts.

This avoids sending the full diary corpus to the model on every query.

## TODO Management Design

TODO support is global across diary history.

### Detection

Unchecked TODOs are recognized by the Markdown pattern:

- `- [ ] ...`

Completed TODOs are recognized by:

- `- [x] ...`

### Completion Flow

- The system scans all configured diary Markdown files.
- It displays open TODOs in a `prompt_toolkit` checkbox dialog (or numbered list in CLI fallback).
- Selected TODOs are updated in place in their source files.

### CLI Subcommand

The `todos` subcommand provides dedicated TODO management:

```
python diary_agent.py todos
```

Uses the shared `prompt_for_task_completion` function from the dedicated `todos` command, ensuring consistent behavior.

### Duplicate Prevention

There are multiple layers of deduplication:

1. Entry-level dedupe
   - All entries (TODOs + regular notes) are checked against existing content
   - Uses normalized text comparison via `normalize_todo_text()`
   - Also filters duplicates within the new entry itself

2. Completed TODO tracking
   - `open_todo_keys()` checks ALL todos (pending + completed)
   - Prevents re-adding completed todos as new

3. Exact and near-exact dedupe
   - normalizes text by tokenization and removes repeats against existing open TODOs

4. Semantic similarity check
   - LLM-backed check for semantically similar TODOs
   - Prompts user (interactive) or skips (non-interactive)
