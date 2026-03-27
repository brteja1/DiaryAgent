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
- Reduce accidental TODO duplication with both deterministic filtering and LLM-backed similarity checks.
- Degrade clearly when dependencies or local model connectivity are missing.

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

Current supported config entry:

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

### Interactive Path

1. Resolve config.
2. Ensure the diary storage directory exists.
3. Open a multiline `prompt_toolkit` editor.
4. Submit the current buffer with `Ctrl+D`.
5. Send the raw text to Ollama for Markdown bullet generation.
6. Remove duplicate TODOs deterministically.
7. Review semantically similar TODOs against unresolved historical tasks.
8. Append the surviving entry to today's file.
9. If open TODOs exist, ask whether the user wants to see them.
10. If the user says yes, open the TODO checklist and allow completion updates.

### Non-Interactive Path

The `capture --text "..."` path skips the editor and uses the provided text as input. Similar TODO confirmations fall back to a plain CLI prompt when stdin is a TTY. In fully scripted mode, similar TODOs are skipped automatically.

## LLM Integration

The system uses Ollama for three separate tasks.

Model selection comes from the config file by default, with `--model` available as an explicit runtime override.

### 1. Diary Entry Synthesis

Input:

- timestamp
- today's existing diary context
- raw user update
- lightweight TODO intent hints

Output:

- concise Markdown bullet points

The prompt tells the model to:

- preserve factual content
- keep continuity with today's notes
- format actionable items as TODO checkboxes
- avoid headings or commentary
- avoid repeating unresolved TODOs already in the diary

### 2. TODO Similarity Decision

For each candidate unchecked TODO that survives exact dedupe, the system can ask Ollama whether it is effectively the same unresolved task as an existing open TODO. The model is instructed to answer only `YES` or `NO`.

This is used as a second-stage filter after lexical shortlisting.

### 3. History Answer Synthesis

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
- It displays open TODOs in a `prompt_toolkit` checkbox dialog.
- Selected TODOs are updated in place in their source files.

### Duplicate Prevention

There are two layers:

1. Exact and near-exact dedupe
   - normalizes text by tokenization and removes repeats against existing open TODOs and repeats within the same generated entry
2. Semantic dedupe
   - uses a lexical shortlist plus an Ollama yes/no similarity decision
   - requires user confirmation before adding a semantically similar TODO in interactive flows

This hybrid approach keeps the deterministic path fast while reserving model calls for ambiguous cases.

## Search Design

Search is intentionally lightweight.

### Retrieval

- Tokenize the user query.
- Scan all Markdown files in the configured diary directory.
- Split file content into paragraph-like chunks.
- Score chunks using substring hits and token overlap.
- Keep the top-ranked excerpts.

### Answering

- Provide the top excerpts to Ollama.
- Ask for a concise answer grounded only in those excerpts.
- Print the synthesized answer and the matched excerpts.

This is simpler than embedding-based retrieval, but adequate for a local-first, dependency-light design.

## Terminal UI Design

The UI is built with `prompt_toolkit`.

### Editor

- multiline buffer
- status toolbar with date/time and state
- explicit `Ctrl+D` binding for submission

### Dialogs

- TODO checklist
- post-capture yes/no TODO prompt
- similar-TODO confirmation
- completion confirmation

Dialogs use a custom black-background style instead of the prompt_toolkit default dialog theme.

## Error Handling Strategy

The CLI treats dependency and environment failures as runtime errors with explicit user-facing messages.

Examples:

- missing `ollama` Python package
- missing `prompt_toolkit` Python package
- Ollama service not reachable
- configured model unavailable
- missing/invalid config in non-interactive mode

Keyboard interrupt is handled separately and exits cleanly.

## Tradeoffs

### Why A Single-File Implementation

- simpler distribution
- fewer moving parts for a local utility
- faster iteration while requirements are still evolving

The downside is growing file size and tighter coupling between UI, storage, and model logic.

### Why Lexical Retrieval Instead Of Embeddings

- no extra infrastructure
- no vector store dependency
- easier offline/local operation

The downside is weaker recall for semantically distant phrasing.

### Why Use Ollama For TODO Similarity

- catches paraphrased duplicates better than normalization alone
- aligns with the local-model-first architecture

The downside is additional model calls and dependency on local model quality.

## Current Limitations

- The project is implemented in one module, so future growth may justify splitting into config, UI, search, and model modules.
- Search quality depends on lexical retrieval before synthesis.
- Semantic duplicate detection depends on local model availability and judgment quality.
- Terminal rendering still depends on the user terminal dimensions and capabilities.

## Future Refactoring Directions

- split the code into dedicated modules
- add automated tests around config, TODO scanning, and duplicate filtering
- support richer config entries such as model name and UI preferences
- support richer config entries beyond the current `diary_path` and `llm_model`
- add search caching or more advanced retrieval
- add structured logging for operational troubleshooting
