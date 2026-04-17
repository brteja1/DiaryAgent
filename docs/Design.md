# Diary Agent Design

## Overview

The diary agent is a local-first Python CLI for capturing daily notes, managing persistent TODOs, viewing prior entries, and querying diary history using a locally reachable Ollama model. The current implementation is organized around four user-facing workflows:

- capture a free-form update into today's diary file or an explicitly requested day file
- review and complete open TODOs across diary history
- view a day entry and navigate to other existing entries
- search historical diary content with a natural-language question

The implementation currently lives in [`diary_agent.py`](/linuxdev/github/DiaryAgent/diary_agent.py) plus small supporting modules under [`diary_agent_app/`](/linuxdev/github/DiaryAgent/diary_agent_app).

## Design Goals

- Keep diary storage outside the source tree and make it user-configurable.
- Use a local terminal workflow without requiring a GUI application.
- Preserve continuity by showing the target day's existing notes to the LLM as background context.
- Keep TODO handling persistent across all diary files, not just the current day.
- Reduce accidental TODO duplication with deterministic filtering plus semantic similarity checks.
- Let the user retain final control over interactive capture output before it is written.
- Degrade clearly when dependencies or local model connectivity are missing.
- Work with or without `prompt_toolkit` where feasible.

## High-Level Architecture

The current code is split into a thin CLI/orchestration layer and three small support modules:

1. [`diary_agent.py`](/linuxdev/github/DiaryAgent/diary_agent.py)
   Handles CLI parsing, command routing, and the main `DiaryAgent` domain object.
2. [`diary_agent_app/core.py`](/linuxdev/github/DiaryAgent/diary_agent_app/core.py)
   Holds shared parsing, config, tokenization, and local search helpers.
3. [`diary_agent_app/llm.py`](/linuxdev/github/DiaryAgent/diary_agent_app/llm.py)
   Holds Ollama-backed synthesis, answer generation, and TODO similarity checks.
4. [`diary_agent_app/ui.py`](/linuxdev/github/DiaryAgent/diary_agent_app/ui.py)
   Holds `prompt_toolkit` editor, dialogs, and show-viewer interactions.

This keeps deployment simple while still separating terminal behavior, LLM behavior, and file/domain logic.

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
- The filename carries the date; individual captures within the file are grouped under time-only headings like `## 14:30`.
- Existing content is preserved and new captures are appended with blank-line separation.
- The system treats all `*.md` files in the configured diary directory as part of history for TODO scanning, show navigation, and search.

The on-disk format is intentionally Markdown-first. A typical day file looks like:

```markdown
## 09:15

- Reviewed deployment logs
- [ ] Follow up on the retry spike

## 14:30

- Project work
  - Finished auth cleanup
  - Added regression coverage
```

## Core Domain Objects

The implementation currently uses four small data objects:

- `PendingTask`
  - represents an unchecked task line and its source file/line
- `SimilarTodoMatch`
  - represents a new candidate TODO and the existing open TODO it resembles
- `AppConfig`
  - represents resolved user configuration, currently `diary_dir` and `llm_model`
- `DiaryEntryOption`
  - represents a selectable diary file in the show-screen fuzzy picker

These objects are deliberately narrow and map directly to operational workflows.

## Capture Flow

The capture path is the default CLI behavior.

### Interactive Path (with prompt_toolkit)

1. Resolve config.
2. Ensure the diary storage directory exists.
3. Open a multiline `prompt_toolkit` editor.
4. The user may press `Alt+R` at any point to request an Ollama rewrite of the current buffer.
5. While the rewrite is running, the buffer is locked read-only and the toolbar shows that the editor is waiting for the LLM rewrite.
6. When the rewrite finishes, the rewritten text replaces the current editor buffer in place.
7. The user may keep editing, trigger another rewrite, or press `Ctrl+D` to submit whatever is currently in the buffer.
8. The submitted text is appended to the target day file verbatim under a time heading.

Important current behavior:

- The interactive final buffer is not post-processed before save.
- This means user-authored headings or manual structure edits are preserved as entered.
- The LLM rewrite path itself removes LLM-added section headings and filters out lines already present in the target day file before putting the rewritten draft back into the editor.

### CLI Fallback Path (without prompt_toolkit)

1. Resolve config.
2. Ensure the diary storage directory exists.
3. Prompt for input via stdin (empty line or Ctrl-D to finish).
4. Send the raw text to Ollama for Markdown bullet generation.
5. Remove duplicate entries deterministically against the target day file.
6. Review semantically similar TODOs against unresolved historical tasks.
7. Append the surviving entry to the target day file under a time heading.

Timestamp heading disambiguation:

- The first update in a minute uses `## HH:MM`.
- If that minute already exists in the same day file, the next update uses `## HH:MM:<serial>` (for example `## 14:30:2`, then `## 14:30:3`).
- This keeps section ids unique for edit/tag/delete and HTFS resource mapping.

### Non-Interactive Path

The `capture --text "..."` path skips the editor and uses the provided text as input. In this path the rewritten entry still goes through deterministic dedupe and TODO similarity review before append. Similar TODO confirmations fall back to a plain CLI prompt when stdin is a TTY. In fully scripted mode, similar TODOs are skipped automatically. `capture --day dd_mm_yyyy` (or a relative date like `-1`) uses that day's file as the append and dedupe target for either interactive or `--text` capture.

## LLM Integration

The system currently uses Ollama for three tasks.

Model selection comes from the config file by default, with `--model` available as an explicit runtime override.

### 1. Diary Entry Synthesis

Input:

- timestamp
- the target day's existing diary context
- raw user update

Output:

- concise Markdown bullets, optionally with nested sub-bullets

The synthesis prompt instructs the LLM to:

- preserve factual content
- use today's file only as background context
- rewrite only the new raw update
- decide semantically whether items are TODOs or regular notes
- format actionable items as `- [ ] ...`
- avoid headings, commentary, or section structure
- preserve hierarchy with nested bullets when appropriate
- avoid repeating unresolved TODOs already in the diary

The implementation also strips any Markdown headings the LLM still produces before presenting rewritten output back to the user.

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
- It displays open TODOs in a `prompt_toolkit` checkbox dialog (or numbered list in CLI fallback).
- Selected TODOs are updated in place in their source files.

### CLI Subcommand

The `todos` subcommand provides dedicated TODO management:

```bash
python diary_agent.py todos
```

This reuses the same completion logic as the checklist dialog path.

### Duplicate Prevention

There are two active dedupe layers:

1. Entry-level dedupe
   - All entry lines are compared against today's existing file
   - Duplicates within the candidate entry itself are also removed
   - The comparison is normalized and near-duplicate tolerant, not exact-string only

2. TODO-specific dedupe and similarity review
   - Open and completed TODO text is tracked across all diary files
   - Exact duplicate TODOs are removed before append
   - Candidate TODOs are then checked for semantic similarity against unresolved tasks
   - Interactive confirmation is available when the flow supports it

## Show Flow

The `show` command supports both direct lookup and in-view navigation:

```bash
python diary_agent.py show
python diary_agent.py show "05_03_2026"
```

Behavior:

- With no argument, `show` defaults to today's date.
- With a `dd_mm_yyyy` or relative date argument (e.g., `-1`), it opens that specific day.
- The `prompt_toolkit` viewer is read-only.
- `[` and `]` move to the previous or next existing diary file in filename/date order.
- At the ends of history, navigation is a no-op.
- `g` opens an in-place fuzzy picker over existing diary files.
- The picker lists newest first and shows a human-readable date plus a preview line.
- `e` opens a nested editor for the timestamp section under the cursor and writes the edited section back into the current file.
- `t` opens HTFS tag management for the timestamp section under the cursor.
- `d` confirms and deletes the timestamp section under the cursor from the current file.
- Section deletion also removes the corresponding HTFS section resource and associated tags.
- Without `prompt_toolkit`, the file contents are printed to stdout.

Implementation note:

- The nested editor and tag-management dialogs are launched in an event-loop-safe way so the show screen can invoke them without tripping over the active prompt_toolkit application context.

## HTFS Tag Commands

The `tags` command covers both section-level inspection and taxonomy management:

```bash
python diary_agent.py tags show 26_03_2026 14:30
python diary_agent.py tags apply 26_03_2026 14:30 Project/DiaryAgent Topic/Retrieval
python diary_agent.py tags suggest 26_03_2026 14:30
python diary_agent.py tags ls
python diary_agent.py tags tree Project
python diary_agent.py tags delete Project --descendants --unused-only --yes
```

Deletion behavior is intentionally explicit:

- `tags delete` removes a tag from the whole HTFS taxonomy.
- `--descendants` makes deletion recursive over child tags.
- `--unused-only` blocks deletion if the selected tags are still used by diary resources.
- `--yes` skips the final confirmation prompt for scripted use.

Inspection helpers are intentionally lightweight:

- `tags ls` prints the flat HTFS tag inventory.
- `tags tree` prints the hierarchy, and can be rooted at a specific tag to inspect a subtree before deletion.

## Search Flow

The `search` command retrieves local text excerpts using token overlap scoring and then asks the LLM to answer using only those excerpts.

```bash
python diary_agent.py search "What did I note about the login bug?"
```

The design intentionally keeps retrieval local and cheap before invoking the model.
