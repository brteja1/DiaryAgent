# Current Requirements

This file describes the current implemented behavior of the diary agent in this repository.

## Runtime And Dependencies

- Implementation language: Python.
- Main entry point: `diary_agent.py`.
- Local model integration: uses the Python `ollama` client for text generation, history-answer synthesis, and semantic TODO similarity checks.
- Terminal UI: uses `prompt_toolkit` for multiline input and dialog-based prompts.
- Expected runtime environment:
  - Ollama must be installed and reachable from the machine running the script.
  - The configured model must already be available in Ollama.
  - `prompt_toolkit` and `ollama` Python packages must be installed.
  - A user config file at `~/.config/diary_agent/config.txt` is required for normal operation.

## Model Behavior

- The agent uses a configurable Ollama model through:
  - required config entry: `llm_model=...`
  - optional CLI override: `--model`
- The primary source of truth is the config file, not a hardcoded Python default.

## Configuration

- The agent no longer derives diary storage from the folder containing `diary_agent.py`.
- Diary storage is configured through:
  - `~/.config/diary_agent/config.txt`
- Current required config entries:
  - `diary_path=/path/to/diary/folder`
  - `llm_model=model_name_available_in_ollama`
- If the config file is missing, or either required entry is missing/empty:
  - Interactive terminal run: the agent prompts the user for the diary folder path and writes the config file.
  - Non-interactive run: the agent exits with a clear error.

## File Management

- Uses the configured `diary_path` as the diary storage directory.
- Creates the configured diary directory if it does not already exist.
- Stores daily notes in files named `dd_mm_yyyy.md`.
- Appends new content to the current day's file instead of overwriting existing content.
- Reads today's existing file before generating new diary output so the model has continuity context.

## Capture Workflow

- Default command behavior is capture mode.
- Interactive capture flow:
  - Opens a multiline `prompt_toolkit` editor first.
  - Supports standard text entry, cursor movement, backspace, and multiline input.
  - Shows a bottom status toolbar with date/time and current state.
  - `Ctrl+D` explicitly submits the current buffer.
- If the submitted update is empty:
  - The program reports that no update was captured.
  - The TODO follow-up prompt can still appear afterward.
- Non-interactive capture is supported through:
  - `python diary_agent.py capture --text "..."`.

## Diary Formatting

- Raw informal updates are sent to Ollama and converted into concise Markdown bullets.
- Regular notes are generated as `- ...`.
- Action-oriented reminders and TODO-like text are encouraged as `- [ ] ...`.
- The generation prompt instructs the model not to repeat unresolved TODOs already present in the diary.

## TODO Management

- Scans all `*.md` files in the configured diary directory for unchecked tasks matching `- [ ] ...`.
- Allows marking existing unchecked tasks as complete by rewriting them as `- [x] ...`.
- TODO review flow now happens after note capture, not before it.
- After capture, if pending TODOs exist, the user is asked whether to show them.
- The TODO checklist screen opens only if the user chooses yes.

## TODO UI Behavior

- TODO dialogs use a black-background custom style instead of the default blue prompt_toolkit dialog look.
- The checklist action buttons currently use:
  - `Complete`
  - `Skip`
- The initial yes/no prompt for showing TODOs currently uses:
  - `Yes`
  - `No`

## Duplicate TODO Protection

- Exact or near-exact TODO duplicates are removed before appending by normalized-text comparison.
- Duplicate TODOs within the same newly generated entry are also removed.
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
- Search behavior:
  - Retrieves candidate excerpts from `*.md` files in the configured diary directory using local token-overlap scoring.
  - Sends the best excerpts to Ollama.
  - Returns a synthesized answer based only on the retrieved excerpts.
  - Prints the relevant excerpts after the answer.

## Error Handling

- If `ollama` or `prompt_toolkit` Python packages are missing, the script exits with a clear runtime error.
- If Ollama is not reachable or the configured model is unavailable, the script exits with a clear runtime error.
- Keyboard interrupt is handled gracefully.

## Current File Structure

```text
~/.config/diary_agent/config.txt

config.txt:
diary_path=/path/to/Diary
llm_model=llama3

/Project_Root
|
`-- diary_agent.py

/path/to/Diary
|-- 24_03_2026.md
|-- 25_03_2026.md
`-- 26_03_2026.md
```

## Current Known Constraints

- Semantic TODO similarity depends on Ollama availability and model quality.
- The search retrieval step uses lightweight lexical scoring before model synthesis; it is not embedding-based retrieval.
- Terminal dialog rendering still depends on the user's terminal size and capabilities, though the styling and button labels have been improved.
