# Diary Agent

A local-first Python terminal diary with daily Markdown notes, persistent TODOs, section tags and local Ollama-assisted search. HTFS is a mandatory bundled dependency; LLM assistance is optional.

[Specification](docs/Specification.md) is the authoritative behavior contract. [Requirements](docs/Requirements.md) indexes its features and [implementation status](docs/Requirements.md#implementation-status). [Design](docs/Design.md) describes architecture; [AGENTS.md](AGENTS.md) provides contributor guidance. [Future](docs/Future.md) contains nonbinding proposals.

## Setup

Requires Python 3.10+, Git, the pinned HTFS source, and Python packages from `requirements.txt`. Ollama and a pulled model are needed only for LLM-backed operations. Terminal presentation uses `prompt_toolkit` with CLI fallbacks where available.

From the repository root:

```bash
git submodule update --init --recursive
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

For a new clone, use `git clone --recurse-submodules <DiaryAgent-repository-url>`. `make deps` initializes submodules and installs dependencies in the selected Python environment.

[HTFS setup](docs/HTFS.md) documents the initial pin and checks. The app uses the Python API from `deps/HTFS`, never a discovered `tagfs` command or external checkout. Every operational CLI command requires HTFS and checks the diary boundary before dispatch. Help is available without backend initialization.

To use a local model, install/start Ollama and pull the model you choose, for example:

```bash
ollama pull llama3
```

## Configuration

`~/.config/diary_agent/config.txt`:

```text
diary_path=~/Diary
# Optional:
llm_model=llama3
```

`diary_path` is required; omit `llm_model` for no-LLM operation. An interactive run can create missing/incomplete config; unattended startup reports an error. The CLI override `--model MODEL` appears before the subcommand.

HTFS always comes from `deps/HTFS`. Old `htfs_path` entries and `DIARY_AGENT_HTFS_PATH` values are ignored. Metadata files `.tagfs.db` and `.tagfs.ttl` live in the diary directory, outside the submodule.

## Capture

```bash
python diary_agent.py
python diary_agent.py capture --day 25_03_2026
python diary_agent.py capture --day -1 --text "Backfilled a note"
python diary_agent.py --model mistral capture
```

No subcommand defaults to capture. Dates accept `dd_mm_yyyy` or relative day integers such as `-1`, `+1`, and `0`. Editor keys are `Ctrl+D` to submit, `Alt+R` to request a rewrite and `Alt+S` to request tag suggestions. Available LLM actions depend on model configuration. Successful interactive capture offers section tagging; capture never opens TODO review.

Final submitted bodies are saved verbatim. `Alt+R` displays a locked proposal; `Alt+Y` accepts and `Alt+N` restores the original draft. `Ctrl+D` submits after review. TTY `--text` proposals ask for consent; unattended capture keeps the original text.

Files use dates such as `25_03_2026.md`. Captures have time headings; repeated captures in one minute use serial suffixes:

```markdown
## 14:30

- Finished the review.
- [ ] Follow up with finance

## 14:30:2

- Project work
  - Reviewed the retry logic.
```

## TODOs and viewing

```bash
python diary_agent.py todos
python diary_agent.py show
python diary_agent.py show -1
python diary_agent.py show 25_03_2026
```

`todos` reviews pending checkboxes across immediate diary Markdown files. D-11's approved metadata target uses `[due: 16-11-2026] [priority: high]` for new generated values, preserving existing valid hyphen/ISO/underscore dates and unknown/invalid metadata as unvalidated text. Relative dates may be expanded only for open tasks within an accepted LLM proposal; completed dates stay unchanged. Task views mark unknown priorities and invalid due values as unvalidated. Invalid newly generated fields fail proposal preparation, retaining the original note; verbatim saves remain unrestricted. Diary filenames and explicit day arguments remain `dd_mm_yyyy`. A missing model does not prevent checkbox discovery/completion, but HTFS remains mandatory.

With noninteractive stdin, `todos` lists tasks without prompts or changes. Malformed/out-of-range interactive selections are rejected as a whole. Completion checks affected-file snapshots before writing and requires reselection after changes; this does not make multiple writes atomic.

`show` defaults to today and can offer the latest entry when today is missing. With the terminal UI, it supports scrolling and these explicit actions:

| Key | Action |
| --- | --- |
| `[` / `]` | Previous/next existing dated entry in calendar order. |
| `g` | Entry picker, newest date first. |
| `Space` | Toggle the checkbox at the cursor. |
| `e` / `t` / `d` | Edit, manage tags, or confirm deletion of the section at the cursor. |
| `q` / `Esc` / `Ctrl+C` | Exit. |

Without prompt_toolkit, viewing prints to stdout. Direct typing does not edit the viewer. Duplicate IDs block section mutations; edits preserve bytes outside their target. Cancellation preserves tags and an accepted empty selection clears them. Persistence failures report saved/partial/uncertain state and a recovery operation ID. The viewer reloads committed content even when metadata reconciliation fails.

## Tags and search

```bash
python diary_agent.py tags show 25_03_2026
python diary_agent.py tags show 25_03_2026 14:30
python diary_agent.py tags apply 25_03_2026 14:30 Project/DiaryAgent Topic/Retrieval
python diary_agent.py tags suggest 25_03_2026 14:30
python diary_agent.py tags ls
python diary_agent.py tags tree Project
python diary_agent.py tags delete Project --descendants --unused-only --yes
python diary_agent.py search "What did I note about retries?"
python diary_agent.py search --tags 'DiaryAgent&Retrieval' "retries"
python diary_agent.py search --tags DiaryAgent
```

Tagging is at timestamp-section level. HTFS owns hierarchical path creation; resources are associated with leaf tag names. `tags apply` adds associations; suggestions print without applying them. Taxonomy deletion is distinct from untagging a section and requires confirmation unless `--yes` supplies it. Serial-suffixed section times are supported.

Search retrieves local excerpts and tags. A configured model may synthesize an answer or translate a natural-language tag filter. Without a model, use HTFS expressions (`&`, `|`, `~`, parentheses); a tag-only search lists matching sections. Answer-synthesis failures can fall back to local excerpts; HTFS failures do not permit a tag-free fallback, and filter failures never silently widen the search.

## Recovery

Before diary or tag changes, intent is written under `<diary_path>/.diary-agent/operations/`. Records retain content fingerprints, prior/intended associations, progress and errors. Content changes are verified before metadata deletion; tag-only operations leave Markdown untouched. Capture tagging is a separate operation after the saved capture.

```bash
python diary_agent.py recovery list
python diary_agent.py recovery show OPERATION_ID
python diary_agent.py recovery retry OPERATION_ID
python diary_agent.py recovery list --all
python diary_agent.py recovery resolve OPERATION_ID --reason "Kept the current state" --yes
```

Retry checks content, unique targets and recorded metadata state. It never appends, edits, completes tasks or deletes diary content again. Divergence requires inspection; an unconfirmed content write is not replayed. Completed/resolved records remain receipts, so later manual changes survive repeated retries. Explicit resolution records the user's decision without changing either data store. Mandatory HTFS preflight still applies.

These are recovery guarantees, not atomic transactions, automatic rollback, multi-process isolation or a power-loss durability promise. See [Design](docs/Design.md) for record structure and [tests](docs/Testing.md) for fault boundaries.

## Development and verification

Formal consistency and verification skills were used to curate the [specification](docs/Specification.md) and [verify the implementation](docs/conformance/ConformanceReview.md).
