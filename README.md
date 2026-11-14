# Diary Agent

A local-first Python terminal diary with daily Markdown notes, persistent TODOs, section tags and local Ollama-assisted search. HTFS is a mandatory bundled dependency; LLM assistance is optional.

[Specification](docs/Specification.md) is the authoritative behavior contract. [Requirements](docs/Requirements.md) indexes its features and implementation status. [Design](docs/Design.md) describes architecture; [AGENTS.md](AGENTS.md) provides contributor guidance. [Future](docs/Future.md) contains nonbinding proposals.

## Implementation status

The specification includes approved targets that are not yet implemented. Current regression success is not a claim of full conformance.

| Area | Current status |
| --- | --- |
| Mandatory bundled HTFS (D-07) | Implemented, including startup validation and integration tests. |
| TODO review (D-02) and five LLM tasks (D-03) | Current routing/task inventory agrees with the decisions. |
| Consent and verbatim saves (D-01) | Pending: code still applies rewrite output directly and normalizes/trims/filters content in save paths. |
| Calendar navigation, identity guards and byte preservation (D-04–06) | Pending: lexical ordering, first-match lookup and whole-file reconstruction require correction. |
| Recovery and tag cancellation (D-08–09) | Pending: no recovery journal/retry mechanism; cancellation and accepted-empty still need distinct UI results. |
| Documentation authority (D-10) | Applied in the documentation. |
| TODO metadata (D-11) | Approved; generated `DD-MM-YYYY` dates and metadata validation/preservation need implementation. |
| Unattended/stale selection (D-12) | Approved; read-only non-TTY listing, complete selection validation and snapshot guards need implementation. |

The authoritative specification records the exact targets, acceptance examples and remaining gaps.

All twelve recorded decisions are resolved in specification v1.0; the pending rows above describe implementation work, not unanswered product choices.

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

D-01's approved target requires exact final-body preservation and explicit consent to a complete changed LLM proposal. The current implementation does not yet satisfy that target, including in `--text` processing; see the status table and specification before relying on literal preservation.

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

`todos` reviews pending checkboxes across immediate diary Markdown files. D-11's approved metadata target uses `[due: 16-11-2026] [priority: high]` for new generated values, preserving existing valid hyphen/ISO/underscore dates and unknown/invalid metadata as unvalidated text. Relative dates may be expanded only for open tasks within an accepted LLM proposal; completed dates stay unchanged. These metadata changes still need implementation. Diary filenames and explicit day arguments remain `dd_mm_yyyy`. A missing model does not prevent checkbox discovery/completion, but HTFS remains mandatory.

D-12's pending target lists tasks without prompts or task changes when stdin is noninteractive. Interactive malformed/out-of-range input changes no tasks; completion must verify affected files/tasks still match the displayed snapshot and require refresh/reselection if stale. The current implementation does not yet provide these guarantees.

`show` defaults to today and can offer the latest entry when today is missing. With the terminal UI, it supports scrolling and these explicit actions:

| Key | Action |
| --- | --- |
| `[` / `]` | Previous/next existing entry. Calendar ordering is an approved pending fix. |
| `g` | Entry picker. Newest-first calendar sorting is a pending fix. |
| `Space` | Toggle the checkbox at the cursor. |
| `e` / `t` / `d` | Edit, manage tags, or confirm deletion of the section at the cursor. |
| `q` / `Esc` / `Ctrl+C` | Exit. |

Without prompt_toolkit, viewing prints to stdout. Direct typing does not edit the viewer. Consult pending D-05/D-06/D-08/D-09 targets before treating section mutations, recovery or tag cancellation as fully conformant.

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

## Development and verification

```text
diary_agent.py                 CLI, orchestration and current domain/storage logic
diary_agent_app/
  models.py                    Shared records
  core.py                      Config, parsing, TODO and retrieval helpers
  llm.py                       Five Ollama-backed operations
  htfs_adapter.py              Bundled HTFS boundary
  ui.py                        Terminal UI
deps/HTFS/                     Pinned Git submodule
tests/test_diary_agent.py       Application and backend integration tests
scripts/specification/         Independent finite consistency checker
```

```bash
python -m py_compile diary_agent.py diary_agent_app/core.py diary_agent_app/llm.py diary_agent_app/ui.py
pytest -q
python3 scripts/specification/check_consistency.py --output docs/specification/evidence.json
```

The consistency command uses the mathematical-abstractions checkout documented in [MathematicalModel.md](docs/specification/MathematicalModel.md); another location can be supplied with `--catalog-root`. Its [review](docs/specification/ConsistencyReview.md) and evidence are scoped finite analyses, separate from application-conformance and real terminal/model checks.

The stable entrypoint remains `diary_agent.py`. Follow [AGENTS.md](AGENTS.md), update contracts before implementation, and keep approved targets and implemented behavior visibly separate.
