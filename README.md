# Diary Agent

`Diary Agent` is a local terminal-based diary assistant for capturing daily notes, tracking TODOs, and searching diary history with a local Ollama model.

It stores notes as Markdown files, one file per day, and is designed to run offline on your machine once dependencies and the model are installed.

## Features

- Capture informal updates and convert them into concise Markdown bullets.
- Preserve nested bullet hierarchy when a single update naturally expands into sub-points.
- Store daily notes in `dd_mm_yyyy.md` files.
- Detect and manage open TODO items using Markdown checkboxes.
- Avoid duplicate or near-duplicate TODOs.
- Search past diary entries and ask questions against your diary history.
- Use a local Ollama model instead of a cloud LLM.
- Support both interactive terminal UI and non-interactive CLI usage.

## Project Structure

The code is now split by responsibility:

```text
diary_agent.py              CLI entrypoint and app orchestration
diary_agent_app/
  __init__.py
  models.py                 Shared data models
  core.py                   Core diary, config, search, and TODO logic
  llm.py                    Ollama integration
  ui.py                     prompt_toolkit UI helpers
tests/
  test_diary_agent.py
```

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com/) installed and running locally
- A model already pulled into Ollama
- Python dependencies from `requirements.txt`

## Installation

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Make sure Ollama is installed and running, then pull a model you want to use, for example:

```bash
ollama pull llama3
```

## Configuration

The app uses a config file at:

```text
~/.config/diary_agent/config.txt
```

Required entries:

```text
diary_path=/path/to/your/diary
htfs_path=/path/to/HTFS
```

Example:

```text
diary_path=~/Diary
htfs_path=~/HTFS
```

Notes:

- `diary_path` is where daily Markdown files are stored.
- `llm_model` is optional. When omitted, LLM-backed rewrite, tag suggestion, TODO similarity, and answer synthesis stay disabled.
- If `llm_model` is present, it must match a model available in your local Ollama instance.
- `htfs_path` must point to the local HTFS checkout that provides the Python package.
- If the config file is missing during an interactive run, the app will prompt you and create it.
- In non-interactive mode, missing or invalid config causes the app to exit with an error.

## Usage

Run capture mode:

```bash
python diary_agent.py
```

This defaults to `capture` mode.

### Capture Notes Interactively

```bash
python diary_agent.py capture
python diary_agent.py capture --day "25_03_2026"
```

Behavior:

- Opens a multiline terminal editor.
- `Ctrl+D` submits the current note.
- `Alt+R` rewrites the current buffer with Ollama on demand.
- While a rewrite is running, the editor status shows that it is waiting for the LLM rewrite.
- The rewritten text is applied back into the same editor buffer, where you can keep editing before saving.
- Whatever is in the editor when you press `Ctrl+D` is written to the diary verbatim under the timestamp heading.
- `--day dd_mm_yyyy` writes the capture to that day's file instead of today.
- After a successful interactive save, the app immediately prompts for tags for the newly written timestamp section.
- The tag prompt shows the existing HTFS tags and also accepts new comma-separated tags.
- Nested bullets are preserved when useful, but the rewrite does not introduce new Markdown sections.

TODO review is handled separately through:

```bash
python diary_agent.py todos
```

### Capture Notes Non-Interactively

```bash
python diary_agent.py capture --text "Had a productive day, need to follow up with finance tomorrow"
python diary_agent.py capture --day "25_03_2026" --text "Backfilled a note for that day"
```

This is useful for scripts, aliases, or quick terminal logging.

### Search Diary History

```bash
python diary_agent.py search "What did I note about the login bug?"
python diary_agent.py search --tags "project diary agent" "login bug"
python diary_agent.py search --tags "Project&Topic/Retrieval"
```

Behavior:

- The app retrieves relevant excerpts from diary files and matches against section tags.
- Matching excerpts include HTFS section tags when available.
- `--tags` optionally narrows the search to matching HTFS sections.
- With a configured model, `--tags` can be a natural-language description that is translated into an HTFS tag expression using the current tag inventory.
- Without a configured model, `--tags` must already be a valid HTFS tag expression using `&`, `|`, `~`, and parentheses.
- Ollama answers using only those excerpts.
- Matching excerpts are printed after the answer.
- If the configured model is unavailable, the app warns and falls back to basic text search results with section tags.

### Show A Day

```bash
python diary_agent.py show
python diary_agent.py show "05_03_2026"
```

Behavior:

- With no argument, `show` opens today's diary entry.
- If today's entry is missing, `show` offers to open the most recent available entry instead.
- If a day is provided, it must use `dd_mm_yyyy` format.
- Any other format is rejected with an error.
- The matching diary entry is shown exactly as stored.
- If `prompt_toolkit` is available, the entry opens in a scrollable terminal viewer.
- The viewer supports arrow keys and page navigation, `[` for the previous entry, `]` for the next entry, `g` to fuzzy-pick another existing entry, `e` to edit the current timestamp section, `t` to manage tags for that section, `d` to delete the current timestamp section (with confirmation), and exits with `q`, `Esc`, or `Ctrl+C`.
- Deleting a timestamp section from the show viewer also removes the corresponding HTFS section resource and its tags.
- If `prompt_toolkit` is unavailable, the stored entry is printed to stdout.

### Show A Specific Day

```bash
python diary_agent.py show "05_03_2026"
```

### Section Tags

Diary sections are identified by day plus the time heading inside that day file.

Examples:

```bash
python diary_agent.py tags show 26_03_2026 14:30
python diary_agent.py tags apply 26_03_2026 14:30 Project/DiaryAgent Topic/Retrieval
python diary_agent.py tags suggest 26_03_2026 14:30
python diary_agent.py tags ls
python diary_agent.py tags tree Project
python diary_agent.py tags delete Project --descendants --unused-only --yes
```

Behavior:

- `tags show` prints the HTFS tags currently attached to one timestamp section.
- `tags apply` ensures the given tags exist in HTFS and applies them to that section.
- `tags suggest` uses the configured model to suggest tags from the existing HTFS tag set.
- `tags ls` prints the flat HTFS tag inventory.
- `tags tree` prints the HTFS hierarchy and can be rooted at a specific tag.
- `tags delete` removes a tag from the whole HTFS taxonomy.
- `tags delete` can recursively include descendants and can be restricted to unused tags only.
- `tags delete` asks for confirmation unless `--yes` is provided.
- Section ids are derived internally in the form `dd_mm_yyyy.md#HH:MM`.
- If multiple updates are captured in the same minute, later sections use `dd_mm_yyyy.md#HH:MM:<serial>` (for example `dd_mm_yyyy.md#14:30:2`).
- The configured diary path is the HTFS boundary.
- If HTFS metadata has not been initialized there yet, Diary Agent initializes it automatically on first tag use.
- Hierarchical tags are passed to HTFS exactly as entered.
- If you enter a tag like `T1/T2/T3`, HTFS is responsible for creating and linking `T1`, `T2`, and `T3`.
- To conform to HTFS resource-tagging rules, Diary Agent assigns the section resource to the leaf tag name only, for example `T3`.

### Override Configured Model

```bash
python diary_agent.py --model mistral capture
```

This only overrides the configured model for the current command.

## Diary Format

Diary files are stored in the configured diary folder like this:

```text
24_03_2026.md
25_03_2026.md
26_03_2026.md
```

Generated notes are grouped under time-based Markdown headings:

```markdown
## 14:30

- Finished the payment reconciliation task.
- [ ] Follow up with the design team about the dashboard mockups.
```

If more than one update lands in the same minute, headings are disambiguated with a serial suffix:

```markdown
## 14:30

- First update in that minute.

## 14:30:2

- Second update in the same minute.
```

If a note naturally contains sub-points, nested bullets are retained:

```markdown
## 16:10

- Project work
  - Finished auth cleanup
  - Added regression coverage
```

## TODO Behavior

The app scans all `*.md` files in the diary directory for unchecked tasks in this format:

```markdown
- [ ] Example task
```

Current behavior:

- Open tasks can be marked complete as `- [x] ...`.
- Exact duplicate TODOs are removed automatically.
- Similar TODOs are checked against existing open tasks.
- In interactive mode, the app asks whether to keep a similar TODO.
- In fully non-interactive mode, similar TODOs are skipped.

## Error Handling

Common failures:

- Missing `ollama` Python package
- Missing `prompt_toolkit` Python package
- Ollama service not running
- Configured model not available in Ollama
- Missing config file in non-interactive mode

The CLI prints clear runtime errors for these cases.

## Running Tests

Run the test suite with:

```bash
pytest -q
```

## Typical Workflow

1. Configure the diary folder and local model.
2. Run `python diary_agent.py capture` during the day to log updates.
3. Let the app format notes and track TODOs.
4. Run `python diary_agent.py search "..."` to query past entries.

## Notes For Developers

- `diary_agent.py` remains the stable entrypoint.
- Internal implementation details are split into the `diary_agent_app` package.
- Tests currently target the public API exposed by `diary_agent.py`.
