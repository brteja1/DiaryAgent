# Current Requirements

This file describes the current implemented behavior of the diary agent in this repository.

## Runtime And Dependencies

- Implementation language: Python.
- Main entry point: `diary_agent.py`.
- Local model integration: uses the Python `ollama` client for text generation, history-answer synthesis, semantic TODO classification, and semantic TODO similarity checks.
- Terminal UI: uses `prompt_toolkit` for multiline input and dialog-based prompts (optional - CLI fallbacks available).
- Expected runtime environment:
  - Ollama must be installed and reachable from the machine running the script when LLM-backed features are enabled.
  - The configured model must already be available in Ollama when `llm_model` is set.
  - `ollama` Python package must be installed for LLM-backed features.
  - `prompt_toolkit` Python package is optional (CLI fallbacks used if unavailable).
  - A user config file at `~/.config/diary_agent/config.txt` is required for normal operation.

## Model Behavior

- The agent uses a configurable Ollama model through:
  - optional config entry: `llm_model=...`
  - optional CLI override: `--model`
- The primary source of truth is the config file, not a hardcoded Python default.
- If `llm_model` is omitted and no CLI override is supplied, the agent runs in no-LLM mode.

## Configuration

- The agent no longer derives diary storage from the folder containing `diary_agent.py`.
- Diary storage is configured through:
  - `~/.config/diary_agent/config.txt`
- Current required config entries:
  - `diary_path=/path/to/diary/folder`
  - `htfs_path=/path/to/htfs/project`
- Current optional config entry:
  - `llm_model=model_name_available_in_ollama`
- If the config file is missing, or a required entry is missing/empty:
  - Interactive terminal run: the agent prompts the user for the diary folder path, optional Ollama model, and HTFS project path, then writes the config file.
  - Non-interactive run: the agent exits with a clear error.

## File Management

- Uses the configured `diary_path` as the diary storage directory.
- Creates the configured diary directory if it does not already exist.
- Stores daily notes in files named `dd_mm_yyyy.md`.
- Appends new content to the current day's file instead of overwriting existing content.
- The filename already carries the date; per-entry headings inside the file carry only time.
- Reads today's existing file before generating new diary output so the model has continuity context.

## Capture Workflow

- Default command behavior is capture mode.
- Interactive capture flow (with prompt_toolkit):
  - Opens a multiline `prompt_toolkit` editor first.
  - Supports standard text entry, cursor movement, backspace, and multiline input.
  - Shows a bottom status toolbar with date/time and current state.
  - `Ctrl+D` explicitly submits the current buffer.
  - `Alt+R` explicitly requests an Ollama rewrite of the current buffer.
  - While the rewrite is in progress, the editor status indicates that it is waiting for the LLM rewrite.
  - When the rewrite finishes, the rewritten text replaces the current editor buffer in place.
  - The exact text present in the editor when `Ctrl+D` is pressed is written to the diary verbatim.
  - After a successful interactive save, the app immediately prompts for tags for the newly written timestamp section.
  - The tag prompt lists existing HTFS tags and accepts new comma-separated tags from the user.
- CLI fallback capture flow (without prompt_toolkit):
  - Prompts for input via stdin.
  - Empty line or Ctrl-D finishes input.
- Non-interactive capture is supported through:
  - `python diary_agent.py capture --text "..."`.
- Capture can target a specific day file through:
  - `python diary_agent.py capture --day "dd_mm_yyyy"`
  - `python diary_agent.py capture --day "dd_mm_yyyy" --text "..."`
- If `--day` is omitted, capture still defaults to today's date.
- If `--day` is provided, it must match `dd_mm_yyyy` or a relative date integer like `-1` (yesterday), `+1` (tomorrow), or `0` (today); other formats are rejected with a clear error.

## Diary Formatting

- Raw informal updates are sent to Ollama and converted into concise Markdown bullets.
- Each appended capture is stored under a Markdown heading containing only the capture time, for example `## 14:30`.
- The LLM decides semantically whether items are TODOs or regular notes.
- Regular notes are generated as `- ...`.
- Action-oriented reminders and TODO-like text are generated as `- [ ] ...`.
- Nested bullet hierarchy is preserved when the generated rewrite contains sub-points.
- LLM-generated section headings are not retained in the stored rewrite.
- The stored rewrite keeps the LLM's bullet hierarchy, but not any LLM-added top-level sections.
- In interactive capture mode, the final editor contents are not post-processed before being appended.
- The generation prompt instructs the model not to repeat unresolved TODOs already present in the diary.

## TODO Management

- Scans all `*.md` files in the configured diary directory for unchecked tasks matching `- [ ] ...`.
- Optional TODO metadata may be added inline on the same line as trailing fields like `[due: 2026-05-01]` and `[priority: high]`.
- Relative date words in TODO text or due metadata are expanded to exact diary dates before the markdown is written.
- Allows marking existing unchecked tasks as complete by rewriting them as `- [x] ...`.
- Preserves optional TODO metadata when toggling task state.
- TODO review flow now happens after note capture, not before it.
- After capture, if pending TODOs exist, the user is asked whether to show them.
- The TODO checklist screen opens only if the user chooses yes.
- CLI fallback (without prompt_toolkit): shows pending count and prompts `y/N` to show them.

## TODO CLI Command

- Dedicated subcommand for viewing/managing todos:
  - `python diary_agent.py todos`
- Lists all pending todos with their source file and line number.
- Shows optional deadline and priority metadata alongside each pending todo when present.
- Allows selecting todos to mark complete by entering numbers.
- Uses the shared checklist UI in the dedicated `todos` command (`prompt_for_task_completion`).

## Duplicate Entry Protection

- All entries (both TODOs and regular notes) are deduplicated against:
  - Existing entries in the target day file
  - Entries within the new content itself
- Uses normalized text comparison (tokenized and lowercased).
- Exact or near-exact TODO duplicates are removed before appending.
- If all generated content is redundant after filtering, the program reports that there is no new diary content to append.

## Semantic TODO Similarity Check

- The agent performs an additional Ollama-backed similarity review for new unchecked TODO items.
- It compares candidate TODOs against existing open TODOs from diary history.
- If a new TODO appears semantically similar to an existing unresolved TODO:
  - Interactive editor flow: the user is shown a dialog asking whether to add it anyway.
  - `--text` flow with a TTY: the user is asked on the command line whether to add it anyway.
  - Fully non-interactive scripted flow: the similar TODO is skipped automatically.
- When a similar TODO is skipped, the script reports that it was skipped and references the existing source entry.

## History Search

- Supports natural-language history search through:
  - `python diary_agent.py search "your question"`
  - `python diary_agent.py search --tags "tag expression or natural-language tag filter" "optional question"`
- Search behavior:
  - Retrieves candidate excerpts from `*.md` files in the configured diary directory using local token-overlap scoring.
  - Includes HTFS section tags alongside each matching excerpt when they are available.
  - Matches against both diary text and section tags.
  - Optionally narrows results to sections matched by a tag expression.
  - When an LLM model is configured, `--tags` can be a natural-language tag description that is translated to an HTFS tag expression using the currently available tags.
  - When no LLM model is configured, `--tags` must already be a syntactically valid HTFS tag expression using `&`, `|`, `~`, and parentheses.
  - Sends the best excerpts to Ollama.
  - Returns a synthesized answer based only on the retrieved excerpts.
  - Prints the relevant excerpts after the answer.
  - If the configured model is unavailable, the command warns the user and falls back to basic text search output using the same local ranking and section tags.

## Show Command

- Supports viewing a day's diary entry through:
  - `python diary_agent.py show`
  - `python diary_agent.py show "dd_mm_yyyy"`
- If `show` is run without an argument, it defaults to today's date.
- If today's diary file does not exist, the command offers to open the most recent available diary entry instead.
- If a day argument is provided, it must match `dd_mm_yyyy` or a relative date integer like `-1` (yesterday), `+1` (tomorrow), or `0` (today); other formats are rejected with a clear error.
- If the target diary file does not exist, the command reports that no entry was found.
- With `prompt_toolkit` available, the entry opens in a full-screen read-only viewer.
- Without `prompt_toolkit`, the stored entry is printed to stdout.

## Show Viewer Navigation

- The show viewer is read-only; it no longer offers an LLM-based reorganize action.
- Standard scrolling/navigation is provided by the `prompt_toolkit` text area and terminal paging keys.
- `[` moves to the previous existing diary file in filename/date order.
- `]` moves to the next existing diary file in filename/date order.
- If there is no previous or next entry, that navigation key is a no-op.
- `g` opens an in-place fuzzy picker for existing diary entries.
- `e` edits the timestamp section under the cursor in a nested prompt_toolkit editor.
- `t` opens HTFS tag management for the timestamp section under the cursor.
- `d` deletes the timestamp section under the cursor after explicit confirmation.
- Deleting a timestamp section from the show viewer also removes the corresponding HTFS resource and section tags.
- The fuzzy picker:
  - lists existing diary files only
  - orders them newest first
  - shows a human-readable date label plus a preview line
  - filters incrementally using date-oriented search text
  - updates the current viewer in place when an entry is selected
  - cancels cleanly with `Esc` without leaving the current entry

## Section Identity

- Timestamp sections are treated as first-class units inside a day file.
- A stable section id is derived as:
  - `dd_mm_yyyy.md#HH:MM`
  - or `dd_mm_yyyy.md#HH:MM:<serial>` when multiple sections share the same minute.
- Section parsing currently uses `## HH:MM` and `## HH:MM:<serial>` headings as boundaries.
- During capture, if a section for the current minute already exists, the new section heading is suffixed with `:<serial>` (for example `## 14:30:2`).
- Text before the first timestamp heading is ignored for section parsing.

## HTFS Tag Commands

- Supports section-level HTFS tagging through:
  - `python diary_agent.py tags show <day> <time>`
  - `python diary_agent.py tags apply <day> <time> <tag...>`
  - `python diary_agent.py tags suggest <day> <time>`
  - `python diary_agent.py tags ls`
  - `python diary_agent.py tags tree [tag]`
  - `python diary_agent.py tags delete <tag>`
- `tags show` prints the HTFS tags for one timestamp section.
- `tags apply` ensures the provided tags exist in HTFS and then applies them to the section.
- `tags suggest` asks the configured model to suggest tags from the currently available HTFS tag set.
- `tags ls` prints the current HTFS tag inventory in flat form.
- `tags tree` prints the HTFS taxonomy as a hierarchy, optionally rooted at a specific tag.
- `tags delete` removes a tag from the whole HTFS taxonomy.
- `tags delete` supports two independent considerations:
  - whether descendant tags should also be deleted
  - whether deletion should only proceed when the tags are unused by diary resources
- `tags delete` requires explicit confirmation before any deletion is performed.
- HTFS integration operates on timestamp sections, not whole day files.
- The configured diary path is the HTFS boundary.
- If `.tagfs.db` is not present in the diary path yet, HTFS metadata is initialized there automatically on first tag use.
- Hierarchical tags are forwarded to HTFS exactly as entered.
- For a tag like `T1/T2/T3`, HTFS owns the creation of the hierarchy and intermediate nodes.
- To conform to HTFS resource-tagging behavior, Diary Agent assigns the timestamp section to the leaf tag name only, for example `T3`.

## Error Handling

- If `ollama` Python package is missing, the script exits with a clear runtime error.
- If `prompt_toolkit` is missing, CLI fallbacks are used automatically.
- If Ollama is not reachable or the configured model is unavailable, the script exits with a clear runtime error when an LLM-backed path is used.
- Keyboard interrupt is handled gracefully.

## Current File Structure

```text
~/.config/diary_agent/config.txt

config.txt:
diary_path=/path/to/Diary
# llm_model=llama3   # optional

/Project_Root
|
`-- diary_agent.py

/path/to/Diary
|-- 24_03_2026.md
|-- 25_03_2026.md
`-- 26_03_2026.md
```

## Current Known Constraints

- Semantic TODO classification depends on Ollama availability and model quality.
- The search retrieval step uses lightweight lexical scoring before model synthesis; it is not embedding-based retrieval.
- Terminal dialog rendering still depends on the user's terminal size and capabilities, though the styling and button labels have been improved.
