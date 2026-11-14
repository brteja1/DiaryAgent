# Diary Agent Specification

Version: 1.0 — authoritative behavior specification; D-01 through D-12 resolved, 14 November 2026.

## 1. Purpose and status

This specification defines the behavior to preserve while cleaning up Diary Agent, the boundaries that should guide implementation, and the decisions needed before changing ambiguous behavior. It is intended to support incremental refactoring and acceptance testing.

The baseline was extracted from [AGENTS.md](../AGENTS.md), [Requirements.md](Requirements.md), [Design.md](Design.md), [README.md](../README.md), the Python implementation, and `tests/test_diary_agent.py`. Historical statements that the implementation is aligned or tests pass are not evidence of conformance to this new document.

**Status vocabulary:**

- **Baseline**: documented behavior supported by the inspected implementation; preserve during refactoring.
- **Decision required**: conflicting or incomplete contracts; retain the observed behavior until a decision is recorded.
- **Proposed**: a cleanup goal or stronger guarantee that is not claimed to exist today.
- **Decided target**: user-approved behavior; takes precedence over contradictory baseline wording for that decision. Implementation conformance must be tracked separately.

Requirement IDs below are stable references for tests and future changes. “Must” expresses the baseline contract unless explicitly marked proposed or decided target. Subject to direct user instructions, this document is the authoritative behavior contract under D-10. All twelve recorded decisions are resolved. A decided target is not a claim of current implementation conformance; D-07's bundled dependency/startup integration is implemented and tested separately. Section 10 records the remaining implementation gaps.

- **DOC-01 — decided target (D-10), applied**: This specification owns behavior clauses and decision/implementation status. [Requirements.md](Requirements.md) is a feature index referencing these IDs; [Design.md](Design.md) describes current/target architecture; [AGENTS.md](../AGENTS.md) gives operational contributor guidance; [README.md](../README.md) gives setup/use guidance. These supporting documents must not define competing requirements or override approved clauses. Update the specification first for an authorized behavior change, then reconcile its supporting descriptions.
- **DOC-02 — decided target (D-10), applied**: Label approved-but-unimplemented targets and open decisions explicitly. Passing existing tests does not establish full conformance. [Future.md](Future.md) contains nonbinding proposals and adds no active requirements or LLM tasks; automatic tagging is not authorized by roadmap text. Historical excerpts in the consistency review describe prior versions, not current obligations.

The [mathematical interpretation](specification/MathematicalModel.md) defines carriers, equality, guards, outcomes and quantifier scope using the mathematical-abstractions catalog. The [consistency review](specification/ConsistencyReview.md) records demonstrated and conditional conflicts, repairs and executed finite evidence. Version 0.3 replaces the former normalized-save proposal with the user's consent-based D-01 decision. Mathematical abstractions constrain the interpretation; they do not supply new product features.

## 2. Product scope

Diary Agent is a local-first, single-user Python terminal application. The user can capture notes, manage persistent TODOs, browse and modify diary sections through explicit actions, attach hierarchical tags, and search history. Markdown is the canonical diary content; HTFS owns tag metadata. Ollama provides optional assistance.

In scope:

- Daily Markdown storage and timestamp-section identity.
- Interactive capture and capture through `--text`.
- Open TODO discovery, completion, duplicate handling, and relative-date expansion.
- Day viewing, navigation, section editing, section deletion, and tag management.
- Lexical retrieval, tag filtering, and optional LLM answer synthesis.
- Configuration, dependency fallbacks, and clear command outcomes.

Outside this cleanup: Android or web clients, synchronization, cloud models, embeddings, derived summaries, background agents, automatic tagging, new reflection workflows, and new LLM tasks. [Future.md](Future.md) describes separate planning work; its proposals do not extend this specification.

## 3. Terminology and data contracts

| Entity | Meaning and identity |
| --- | --- |
| Diary directory | Configured content root and HTFS boundary. |
| Day entry | UTF-8 Markdown file named `dd_mm_yyyy.md`. |
| Section | Timestamp heading and following body up to the next recognized timestamp heading. |
| Section ID | `<filename>#<time>`, such as `26_03_2026.md#14:30:2`. |
| HTFS resource | Absolute section file path plus `#<time>`, mapped through `HTFSAdapter`. |
| TODO | Markdown checkbox line, optionally indented, with state space, `x`, or `X`. |
| Pending task | Open TODO text, optional metadata, source path, and one-based line number. Line numbers are locations, not durable task IDs. |
| Search result | Source file, excerpt, score, and optional section ID and tags. |
| Draft | Unsaved user-controlled text; a changed LLM proposal replaces it only after review and explicit acceptance. |

### Storage and dates — baseline

- **DATA-01**: Use the configured diary directory and create it when required. Store day files using `dd_mm_yyyy.md` and UTF-8.
- **DATA-02**: Append each nonempty capture accepted for storage under `## HH:MM`, with blank-line separation. In processed capture, acceptance follows CAP-10–12; an explicitly accepted empty proposal causes no append; unconsented nonempty input remains eligible for verbatim storage. For repeated captures in the same minute within the target file, use `## HH:MM:2`, then increasing serials. Existing sections keep their identifiers.
- **DATA-03**: Recognize `## HH:MM` and `## HH:MM:<serial>` as section boundaries. Ignore text before the first recognized heading for section parsing. Other Markdown headings remain body content.
- **DATA-04**: Accept explicit day input only as a valid `dd_mm_yyyy` calendar date or relative day integer, such as `-1`, `+1`, or `0`. Resolve relative days against the local current date. Reject other formats and impossible dates.
- **DATA-05**: Capture defaults to the local current day. An explicit day selects the target file and TODO reference date; the capture heading still uses the local current clock time.
- **DATA-06 — decided target (D-04)**: TODO and unfiltered text-search history scans include all immediate `*.md` files, without recursive traversal. Day navigation, its picker, and latest-entry selection use only valid `dd_mm_yyyy.md` calendar-date filenames. Non-date, malformed and impossible-date filenames remain on disk and available to TODO scans/text search, but are excluded from day navigation. Do not rename or repair them automatically.

Example:

```markdown
## 14:30

- Finished the reconciliation.
- [ ] Follow up with finance [due: 16-11-2026] [priority: high]

## 14:30:2

- Project work
  - Reviewed the retry logic.
```

Section IDs are stable under body edits that do not add, remove or rename timestamp delimiters. External file renames and timestamp-heading edits change identity under D-05.

The relative-date grammar does not promise an infinite calendar: a syntactically valid integer whose resolved date is outside the runtime's date range is an error outcome. No wrapping or silent clamping is specified. Uniqueness of section lookup is conditional on unique recognized headings within a file; no such invariant is asserted for arbitrary externally edited Markdown.

- **DATA-07 — decided target (D-05)**: Retain `<filename>#<timestamp>` section IDs and automatic serial suffixes for app-generated repeated captures. Recognized timestamp-shaped heading lines always delimit sections, including when entered manually. Do not silently escape, rename or normalize submitted headings or body content. D-01's verbatim-save rule remains in force.
- **DATA-08 — decided target (D-05)**: A section-ID lookup is usable only when exactly one occurrence matches. For duplicate IDs, allow whole-file viewing but report ambiguity and block section-specific editing, deletion and tagging for that ID until the headings are explicitly corrected. Do not choose the first match, merge occurrences, or apply a tag to every match. Missing IDs are reported separately from ambiguous IDs. Unique IDs in the same file remain usable.
- **DATA-09 — decided target (D-05)**: Manual file/heading renames produce new IDs. Do not silently transfer tag associations or rewrite content. Metadata migration requires an explicit operation; defining this policy does not add a migration command. Automatic heading allocation affects storage framing only and does not repair manual duplicate headings.

## 4. Command interface

**CLI-01**: Keep `python diary_agent.py` as the entrypoint; omitting the command selects interactive capture. The global `--model MODEL` option overrides configuration for one invocation and appears before the subcommand.

| Command | Inputs | Outcome |
| --- | --- | --- |
| `capture` | `[--day DAY] [--text TEXT]` | Append a section, or report empty/redundant input. |
| `todos` | None | Review pending tasks across history and complete selected tasks. |
| `show` | `[DAY]` | View the requested day, defaulting to today. |
| `search` | `[QUERY] [--tags FILTER]` | Retrieve excerpts, optionally synthesize an answer. |
| `tags show` | `DAY [TIME]` | Show tags for one section, or tagged sections in the day. |
| `tags apply` | `DAY TIME TAG...` | Ensure tags exist and add associations to the section. |
| `tags suggest` | `DAY TIME` | Print suggestions without applying them. |
| `tags ls` / `tags list` | None | List the flat tag inventory. |
| `tags tree` | `[TAG]` | Show the taxonomy, optionally rooted at a tag. |
| `tags delete` | `TAG [--descendants] [--unused-only] [--yes]` | Delete taxonomy tags after the applicable checks and confirmation. |

`DAY` follows DATA-04. `TIME` identifies the heading text, including a serial suffix if present.

**CLI-02**: Return status 0 for successful commands and ordinary no-result/no-change outcomes, 1 for application failures, 2 for argparse usage errors, and 130 for keyboard interruption handled by the main boundary. Do not promise machine-readable output or exact diagnostic wording.

### Configuration — baseline

- **CFG-01**: Read `~/.config/diary_agent/config.txt` as `key=value` lines. Ignore blank lines, comment lines beginning with `#`, and lines without `=`. Expand `~` in paths.
- **CFG-02 — decided target (D-07), implemented**: Require nonempty `diary_path`. Treat absent/empty `llm_model` as no-LLM mode. Do not invent a default model. HTFS always comes from the pinned `deps/HTFS` submodule; ignore legacy `htfs_path` settings and `DIARY_AGENT_HTFS_PATH`. Do not prompt for an external checkout.
- **CFG-03**: On missing/incomplete configuration, prompt and write configuration in an interactive terminal. Fail clearly when stdin is not a TTY.
- **CFG-04**: Resolve the effective model from the CLI override first, then configuration. A missing model must not prevent deterministic note, TODO, or lexical-search behavior.

```text
diary_path=~/Diary
# Optional:
llm_model=llama3
```

Python 3.10+ is the documented runtime. `prompt_toolkit` is optional at runtime; Ollama and its Python client are required only for LLM operations. HTFS and its Python dependencies are mandatory in every operational mode and are imported from the bundled checkout through the adapter. See [HTFS.md](HTFS.md) for setup and the initial pin.

- **DEP-01 — decided target (D-07), implemented**: Carry HTFS as the Git submodule `deps/HTFS`, pinned by the parent gitlink. Use its Python API through `HTFSAdapter`. No `tagfs` command lookup/execution, sibling/home checkout discovery, configurable backend path, or silent system-package substitution is permitted. Setup initializes submodules recursively and installs the local dependency through `requirements.txt`.
- **DEP-02 — decided target (D-07), implemented**: Before dispatching any operational CLI command, validate the bundled backend import and initialize/read the configured diary tagging boundary. If the source, Python dependencies or boundary are unavailable, fail explicitly before writing diary content or starting the main workflow. Do not run in a tag-free fallback mode, including no-LLM operation. Help/usage parsing does not require boundary initialization. Later HTFS failures must not silently become untagged search results or a successful UI fallback; D-08 governs partial persistence and recovery after writes.

**LLM-01 — decided target (D-03)**: The allowed LLM operation set is capture rewrite (including TODO classification), TODO similarity, search answer synthesis, explicit tag suggestion, and natural-language tag-filter translation. Each call must belong to an enabled workflow and use a configured model. This retains all five existing tasks and does not authorize additional tasks or automatic tag application. Content changes remain subject to D-01 consent. AGENTS.md and Requirements now use this same allowlist. A configured model is distinct from an available service and from a successful response.

## 5. Capture contract

### Interactive capture — baseline

D-01's decided target applies to all capture and section-edit save paths, including `--text` and stdin fallback. It overrides the earlier automatic normalization/deduplication policies wherever they would silently change submitted content.

- **CAP-01**: Open one multiline editor. Provide text entry, cursor movement, and a status toolbar. `Ctrl+D` submits when no background operation is running. Empty/whitespace-only submission creates no section.
- **CAP-02**: `Alt+R` explicitly requests a rewrite. With no model, expose no rewrite callback or misleading hint. Do not automatically rewrite on submission.
- **CAP-03**: Supply the target day's existing notes as rewrite context. Ask the model to rewrite only the new draft, preserve facts, distinguish notes from actionable TODOs, avoid repeating existing notes/open tasks, and preserve useful nested bullets. Strip generated Markdown headings. Filter redundant lines before putting the rewrite back into the editor.
- **CAP-04 — decided target (D-01)**: During rewrite, lock editing, block submission and overlapping LLM actions, and show waiting status. On success, show the complete proposed content and obtain explicit acceptance before replacing the draft in the same editor. `Alt+R` requests generation; it does not consent to unseen output. Rejecting/cancelling the proposal or a rewrite failure retains the prior draft. The user may keep editing an accepted draft before submission.
- **CAP-05**: `Alt+S` explicitly requests tags from the current inventory. It must not create or apply tags. During suggestion, lock the buffer and block submission/overlapping LLM actions. Suggestions populate the later tag prompt; errors retain the draft.
- **CAP-06 — decided target (D-01)**: Save user-controlled content verbatim. Without an LLM content transformation, preserve submitted text exactly, including relative date words, indentation, metadata and trailing whitespace. Merely configuring a model, running tag suggestion, or searching does not authorize changing content. An LLM-proposed change may be used only after the user has seen and explicitly accepted the complete proposal. Save the resulting user-edited final draft without further transformation. The generated timestamp heading and outer section separation are storage framing, outside the submitted body; do not trim or reformat the body itself.
- **CAP-13 — decided target (D-01)**: Consent is specific to the displayed proposal. Include any proposed date expansion, metadata rendering, duplicate removal and output cleanup before requesting consent. No deterministic content modification is permitted after acceptance or on a no-LLM save. If a changed proposal cannot obtain consent, do not persist it; retain/save the original text verbatim and report that proposed changes were not applied. Cancellation of the whole capture still writes nothing.
- **CAP-07**: After a successful save, prompt for tags for the new section. Allow skipping tags. Saving precedes this prompt, so cancelling tagging leaves the saved content in place. There is no automatic suggestion request.
- **CAP-08**: Without `prompt_toolkit`, collect lines from stdin until an empty line or EOF, then use the interactive save path. This fallback has no editor hotkey actions.

Mandatory HTFS preflight now applies at operational CLI startup under D-07, before capture opens or any other workflow is dispatched. Availability of the optional LLM is a separate condition.

### Capture with `--text` — baseline

- **CAP-09**: Do not open the editor or post-save tag prompt. Empty input creates no section.
- **CAP-10 — decided target (D-01)**: With no LLM transformation, save the supplied text verbatim. When a model generates changed content, treat that content and all proposed cleanup as one reviewable proposal under CAP-13. A TTY may collect consent without opening the multiline editor. Unattended execution must not treat `--text` or model configuration as consent to changed output.
- **CAP-11 — decided target (D-01)**: Duplicate checks may compare regular notes and TODO lines against target-day content and other candidate lines. Use deterministic normalized-text/lexical heuristics for detection. Removal may occur only within an LLM-associated proposal explicitly accepted under CAP-13; comparison alone must not mutate submitted text. Do not claim general semantic equivalence for regular notes.
- **CAP-12 — decided target (D-01)**: If an accepted complete proposal has no content, report that nothing was appended. Without an accepted changed proposal, nonempty original content remains eligible for verbatim append, including duplicates. Report any accepted skipped similar tasks with their existing source file and line.

For CAP-11, equality of normalized keys and the near-match heuristic are different relations. Exact key equality defines equivalence classes; heuristic near-matching does not promise transitivity or order-independent filtering. It must not be treated as mathematical equality.

### Mode distinctions

| Behavior | Interactive editor / stdin fallback | `--text` |
| --- | --- | --- |
| LLM rewrite | Explicit request, then consent to changed proposal | May generate with configured model; changed output requires consent |
| Explicit rewrite/suggestions | Editor hotkeys when available | No editor |
| Day-line deduplication | Only within an accepted LLM-associated proposal | Only within an accepted LLM-associated proposal |
| History-wide TODO duplicate/similarity review | Advisory; changes require proposal consent | Advisory; changes require proposal consent |
| TODO relative-date normalization | Only within an accepted LLM-associated proposal | Only within an accepted LLM-associated proposal |
| Post-save tag prompt | Yes | No |
| Post-save TODO checklist | Never prompted or opened; D-02 resolved | Never prompted or opened; D-02 resolved |

## 6. TODO contract — baseline

- **TODO-01**: Discover open `- [ ] ...` lines across the Markdown history. Recognize completed `- [x] ...` and `- [X] ...` lines for viewer toggling. Preserve indentation and optional trailing `[due: VALUE]` and `[priority: VALUE]` metadata when updating state.
- **TODO-02 — decided target (D-01/D-11), proposal expansion implemented**: Relative-date expansion may be proposed only for open TODOs during an LLM content transformation, subject to CAP-13 consent. It must not run as hidden save-time processing, including section edits. Use the target diary date, including backfilled entries: `today` means that date, `tomorrow` the next date, and a weekday the nearest occurrence on or after that date. Generated TODO dates use `DD-MM-YYYY`, for example `26-03-2026`. Do not expand dates in completed `x`/`X` tasks. Without an accepted proposal, preserve the original words and metadata. Existing explicit dates remain unchanged under TODO-08.
- **TODO-03 — decided target (D-12), selection guards implemented**: `todos` shows pending task text, metadata, source file and one-based line number. Interactive checklist/numeric selection marks selected pending tasks complete only after TODO-09/10 validation. Empty selection makes no task-state changes. Malformed or out-of-range selections reject the entire selection with an error before task writes, including mixed valid/invalid inputs. Repeated valid indices denote one selected task, not repeated mutations.
- **TODO-04 — decided target (D-01)**: Compare normalized TODO text independently of due/priority metadata to detect exact duplicates against existing open tasks and within new input. Any removal must be part of a complete accepted LLM-associated proposal under CAP-13. Completed history does not count as an existing open task. No-LLM saves retain duplicate text verbatim.
- **TODO-05 — decided target (D-01)**: When LLM similarity review flags a candidate as the same unresolved action, present any proposed removal for consent under CAP-13. Without consent, including unattended execution, preserve original content. Model configuration alone does not authorize deleting a flagged task.
- **TODO-06**: A similarity-model call failure currently yields no semantic match; it must not be described as proof that tasks are distinct. Preserve this behavior during a pure refactor and track any policy change explicitly.
- **TODO-07 — decided target (D-02)**: Open the pending-TODO review/checklist only through the explicit `todos` command. Capture must not ask whether to review pending tasks or open the checklist, even when open tasks exist. After saving and any applicable section tagging, capture finishes. This does not remove the viewer's explicit checkbox toggle or D-01's consent to a proposed content change.
- **TODO-08 — decided target (D-11), implementation pending**: Newly generated due metadata uses valid Gregorian `DD-MM-YYYY` dates and newly generated priorities use lowercase `low`, `medium`, or `high`. Read existing valid `DD-MM-YYYY`, `YYYY-MM-DD` and `dd_mm_yyyy` due values while preserving their original text; do not rewrite legacy values merely to canonicalize them. Preserve unknown priorities and invalid/unrecognized due values as unvalidated text rather than guessing, correcting, dropping them or rejecting a verbatim note save. Structured views distinguish validated fields from unvalidated text. Completed task dates remain unchanged by automatic/proposed date expansion; manual user edits remain possible. Out-of-range relative-date results must be reported rather than wrapped or guessed. This TODO-field decision does not rename diary files or change DATA-04's explicit day-input syntax.
- **TODO-09 — decided target (D-12), selection guards implemented**: Without an interactive stdin terminal, `todos` lists pending tasks and exits successfully without opening a dialog, prompting, consuming piped selections or changing task state. Empty history is a normal no-result outcome. Mandatory HTFS startup still applies; read-only task listing does not imply bypassing DEP-02's metadata initialization.
- **TODO-10 — decided target (D-12), selection guards implemented**: Retain source-file snapshots and selected-task locations/raw checkbox text/metadata when the list is loaded. Before the first task write, reread every affected file and verify that its snapshot and all selected tasks still match, including their open state. If a file is missing/changed or a task moved/changed/completed, reject the whole stale selection without task writes; report the need to refresh and reselect. Do not select a replacement task by its current line number or guess which occurrence was intended. Files outside the selection need not match. This guard does not promise isolation from races after validation or atomicity across multiple subsequent writes; failures during writes follow truthful outcome/recovery reporting under PERSIST-01–05.

Semantic TODO classification is part of rewriting, not an independent background task. Bare prose is not guaranteed to become a checkbox in no-LLM mode.

## 7. Viewer and modification contract — baseline

- **VIEW-01**: `show` opens today's file by default. If today is absent, offer the latest valid dated entry. An explicitly requested missing day reports no entry without automatically substituting another day.
- **VIEW-02**: Display stored diary content in a scrollable, read-only text area; tags may be added as display annotations. Without the terminal UI, print content to stdout. Read-only describes direct typing; the explicit mutation actions below remain available.
- **VIEW-03 — decided target (D-04)**: `[` / `]` navigate to the immediately earlier/later existing dated entry by parsed calendar date, including across month/year boundaries. Only DATA-06's valid dated files participate. At a boundary, do nothing. `g` opens an in-place fuzzy picker in descending calendar-date order with date labels and previews; selection updates the existing viewer and `Esc` cancels. An empty dated-file inventory offers no navigation target.
- **VIEW-04**: `Space` toggles a checkbox at the cursor, preserving metadata. A non-TODO line causes no change. `e` edits the timestamp section at the cursor; a nonempty submitted body replaces that section's body and retains its heading/identity. The current viewer makes no replacement for an empty submitted body; deletion is the separate confirmed action.
- **VIEW-05**: `t` manages the current section's tags through the adapter. `d` asks for explicit confirmation before deleting that section and its HTFS resource/tag associations. Declining deletion changes nothing.
- **VIEW-06**: Refresh the viewer after successful modifications. Provide `q`, `Esc`, and `Ctrl+C` to leave the viewer. Do not provide the removed LLM reorganization action.
- **VIEW-07**: Suspend terminal rendering for subsidiary editors/dialogs and use event-loop-safe execution, including thread mode when a synchronous prompt is launched from an active asyncio context. Do not start a conflicting application on the viewer's active loop.

- **VIEW-08 — decided target (D-06)**: Editing replaces only the selected section's body, preserving its existing heading. Deletion removes only the selected section, including its heading and owned framing up to the next section boundary or end of file. Preserve every byte outside the targeted span: preamble, other sections, spaces, blank lines, line endings and any final newline outside that span. Do not reconstruct or normalize the whole file from parsed section records.
- **VIEW-09 — decided target (D-06)**: Determine a unique target and its exact boundaries before writing. If it is missing, ambiguous or cannot be located safely, report the problem without writing. DATA-08's ambiguity guards and CAP-06/13's final-body consent/verbatim rules remain applicable. This preservation contract does not itself promise atomicity, concurrent-edit detection or cross-store recovery; those remain separate decisions.

The present implementation reconstructs whole files for section edits/deletion and does not yet conform to VIEW-08/09.

## 8. HTFS and search contracts — baseline

### Tagging

- **TAG-01 — decided target (D-07), implemented**: Route all HTFS operations through `HTFSAdapter`. Use the diary directory as boundary, with `.tagfs.db` and `.tagfs.ttl` owned by HTFS. Initialize metadata automatically at operational CLI startup when needed, and read the inventory before dispatch. HTFS is mandatory even for otherwise tag-independent operations.
- **TAG-02**: Tag timestamp sections, not whole files or individual bullets. Map section IDs to HTFS resources in the adapter.
- **TAG-03**: Show top-level tags for context and complete both atomic names and hierarchical paths, including after commas. Require explicit confirmation for new tags entered through interactive tag prompts. An explicit `tags apply ...` command itself requests creation/application of its supplied tags.
- **TAG-04**: Pass hierarchical paths unchanged to HTFS for hierarchy creation. Associate resources using the leaf tag name, such as `DiaryAgent` for `Project/DiaryAgent`. Do not implement a parallel hierarchy in Diary Agent.
- **TAG-05**: `tags apply` adds associations; viewer tag management replaces the selected section's associations. `tags suggest` prints suggestions drawn only from existing tags and never applies them.
- **TAG-06**: Taxonomy deletion is distinct from untagging a section. `--descendants` includes descendants in child-before-parent order. `--unused-only` refuses the operation if any targeted tag is used. Require final confirmation unless `--yes` supplies it; refuse unattended deletion without `--yes`. These flags do not delete diary text.
- **TAG-07 — decided target (D-09), selection distinction implemented; recovery pending**: Tag management must return distinguishable `Cancelled` and `Accepted(tags)` outcomes. Cancel, Esc or Ctrl+C leaves the section's prior tags unchanged and starts no metadata mutation. Explicitly accepting an empty selection removes all associations from that section; accepting a nonempty selection replaces its associations with that selection. Removing associations does not delete taxonomy tags or diary content. Apply accepted changes through the adapter with D-08 recovery/failure handling. Do not encode cancellation and accepted-empty as the same value. Cancelling post-capture tagging also retains the already saved note under CAP-07.

### Persistence and recovery — decided target (D-08), implementation pending

- **PERSIST-01**: Markdown is authoritative for diary content. For a confirmed operation changing both content and section metadata, persist its recovery intent first, commit the Markdown change, then reconcile HTFS to the intended metadata state. Do not delete HTFS resources before a section deletion is confirmed in Markdown. Tag-only operations leave Markdown untouched. Tag associations are not reconstructible from Markdown alone; preserve their intended state in the recovery record.
- **PERSIST-02**: Before mutating either store, persist an operation identity, target file/section IDs, operation kind, expected prior and intended content fingerprints, prior and intended tag associations, and progress/error information sufficient for reconciliation. For deletion, retain the target identity and metadata even after the content disappears. If recovery information cannot be persisted, do not start the mutation. Capture's post-save tagging is a separate metadata operation against the already saved section; cancelling it does not undo the capture.
- **PERSIST-03**: Distinguish complete success, failure with no confirmed change, partial completion, and an uncertain outcome requiring inspection. After a confirmed content write and failed metadata reconciliation, retain the written content and report, for example, `note saved; tagging pending`, with the recovery operation identity. Do not report a generic no-change failure, silently discard the note, or claim rollback/atomicity across Markdown, SQLite and RDF. Uncertain content outcomes must not be reported as confirmed saves.
- **PERSIST-04**: Recovery retry targets the recorded operation and checks current content/metadata against its expected state before reconciling. A metadata retry must never rerun capture, append another section or replay a content deletion/edit. If content has diverged or the target is ambiguous, stop without mutation and report a conflict. Retry sets the intended associations rather than incrementally duplicating resources/tags. Preserve a completion receipt so repeating a completed operation causes no additional mutation, including after later manual changes.
- **PERSIST-05**: Retain pending records and prior tag state until reconciliation is verified after backend close/flush and readback, or the user explicitly resolves the pending operation. Do not clear old tags without preserving their recovery state; do not swallow resource-deletion errors as successful cleanup. The implementation must expose explicit recovery actions, with CLI syntax chosen during implementation. Normal startup still requires HTFS under D-07. This contract promises truthful outcomes and safe retries, not multi-store atomic transactions, automatic rollback, unlimited concurrency safety or power-loss durability.

### Search

- **SEARCH-01**: Require a nonblank query or tag filter. Retrieve locally before answer synthesis. Score lexical overlap in section-body chunks plus available section tags. For files without parsed timestamp sections, allow text-only chunk retrieval. Return the highest-scoring excerpts (current default limit: six).
- **SEARCH-02**: A tag filter restricts retrieval to matching section IDs using HTFS expressions with `&`, `|`, `~`, and parentheses. With no query, list matching sections and tags without answer synthesis.
- **SEARCH-03**: Without a model, require an HTFS expression. With a model, support natural-language filter translation using the available inventory. The current implementation passes through filters containing expression operators and sends other filters to translation. Invalid expressions must not silently become an unfiltered search.
- **SEARCH-04**: With a model and a query, ask for an answer based only on supplied excerpts, including tags as context, filename references, and acknowledgement of insufficient evidence. Print supporting excerpts after the answer. This is a prompt contract, not a guarantee of model factual accuracy.
- **SEARCH-05**: With no model or failed answer synthesis, print local results; for synthesis failure, warn and retain the same retrieval results. Do not claim that this fallback also covers failed tag-filter translation or HTFS querying.
- **SEARCH-06**: No matches is a normal result. Search must not rewrite diary content or apply tags.

## 9. Implementation boundaries and quality goals

Keep the existing responsibility split during initial cleanup. Module names are implementation choices, not storage/API contracts.

| Boundary | Responsibility | Dependencies to keep outside it |
| --- | --- | --- |
| CLI / orchestration (`cli.py`, `commands.py`) | Parse arguments, resolve runtime dependencies, sequence workflows, report outcomes. | Detailed terminal rendering and model prompt construction. |
| Deterministic logic (`core.py`) | Parse config/text/TODO metadata, resolve dates, normalize, rank, shortlist. | Interactive input, model calls; existing config I/O can be separated incrementally. |
| Domain and storage (`DiaryAgent` in `service.py`, `markdown.py`) | Files, sections, task mutations, capture policies, retrieval composition. | Terminal-specific dialogs and command presentation. |
| Models (`models.py`) | Small explicit records for config, tasks, sections, results, and picker options. | Service startup and side effects. |
| LLM adapter (`llm.py`) | Ollama calls, prompts, output cleanup, dependency/model errors. | File writes and user confirmation. |
| HTFS adapter (`htfs_adapter.py`) | Backend import/lifecycle, hierarchy/resource mapping, tag queries and mutations. | Capture UI and diary-content policy. |
| Terminal UI (`ui.py`, `viewer.py`) | Editors, dialogs, viewer/picker state, background-action feedback. | Direct backend access; use supplied callbacks. |

**Baseline quality constraints:**

- **QUAL-01**: Keep Markdown human-readable and local. Do not add a cloud dependency or automatic model download.
- **QUAL-02**: Execute LLM work off the active UI loop. Restore editable state after failures and keep toolbar hints consistent with enabled actions.
- **QUAL-03**: Report missing config, unavailable packages/backend/model, and command failures clearly. Preserve the documented per-workflow fallbacks rather than catching every failure as a successful no-op.
- **QUAL-04**: Keep existing day filenames, timestamp headings, section IDs, metadata syntax, and CLI entrypoint compatible through refactoring. Do not introduce a storage migration as an incidental cleanup.

**Proposed engineering goals, not current guarantees:** inject a clock for deterministic date/time behavior; isolate storage and external-service access enough for tests. Untouched-byte preservation and distinct tag-selection outcomes now have application tests. Explicit partial-completion/recovery semantics (D-08) remain an implementation target. Add abstractions only when these needs justify them. Multi-process safety, physical durability, timeout/cancellation guarantees, diary encryption, and performance targets remain unspecified; multi-store atomicity and automatic rollback are not promised.

## 10. Decisions and observed gaps

Resolved rows record user-approved contracts; their implementation status is separate. Open rows are not authorization to invent behavior. Record the decision and acceptance examples here before implementing an unresolved choice.

| ID | Conflict or gap and evidence | Recommended direction for review |
| --- | --- | --- |
| D-01 — resolved, save/consent paths implemented | User decision: saving may change submitted content only when an LLM is used and the user consents to its proposed modification. No-LLM content must be saved verbatim. | CAP-04/06/10–13 and TODO-02/04/05 record the target. Final-save paths preserve submitted bodies; editor and TTY text proposals require acceptance. Unattended text capture retains originals. See Testing.md for finite acceptance coverage and remaining integration checks. |
| D-02 — resolved | User selected review only through `todos`; no post-capture review prompt or checklist. | TODO-07 records the contract. Current capture behavior agrees; obsolete post-capture prompting requirements have been removed. |
| D-03 — resolved | User retained all five existing LLM tasks: rewrite/TODO classification, TODO similarity, answers, explicit tag suggestions, and tag-filter translation. | LLM-01 and project guidance use one exhaustive allowlist. D-01 consent and explicit tag application remain required. No new model task or runtime change is needed for this decision. |
| D-04 — resolved, implemented | User approved calendar-date ordering: earlier/later navigation, newest-first picker, valid `dd_mm_yyyy.md` files only. Other Markdown files remain in TODO/text scans. | DATA-06 and VIEW-03 define filtering, boundaries and ordering. Navigation/picker/latest now share parsed calendar ordering, independently of all-Markdown history scans. |
| D-05 — resolved, identity guards implemented | User retained file/timestamp IDs and delimiter semantics. View files with duplicate IDs, but block ambiguous section edits, deletion and tagging; never silently rename content. Manual renames change identity and tag migration must be explicit. | DATA-07–09 define the contract. Duplicate-aware lookup blocks ambiguous mutations; raw viewing and verbatim saves remain available. No UUID migration was introduced. |
| D-06 — resolved, implemented | User approved editing only the selected body and deleting only the selected section, with exact preservation of all unrelated bytes. Missing/ambiguous targets must cause no write. | VIEW-08/09 define byte-span preservation and guards. One source-span parser supports localized changes, with byte-preservation tests for preambles, other sections and LF/CRLF. |
| D-07 — resolved and implemented | User requires HTFS always, bundled as a pinned Git submodule, with no command/external-checkout discovery or tag-free operation. | DEP-01/02, CFG-02 and TAG-01 define the contract. `deps/HTFS` is registered, config overrides removed, startup required, and tests cover real backend use and failure paths. Post-write failure reporting/recovery remains D-08. |
| D-08 — resolved, implementation pending | User approved Markdown authority, explicit partial-completion reporting, retained recovery information and safe metadata retries without duplicated diary content. No multi-store atomicity is promised. | PERSIST-01–05 require recorded intent, content-first ordering for combined changes, verified metadata reconciliation and replay-safe receipts. Current delete/tag-replacement paths need implementation fixes. |
| D-09 — resolved, selection outcomes implemented | User approved cancellation preserving tags, accepted-empty clearing section associations, and accepted-nonempty replacing them, with D-08 failure handling. | TAG-07 requires distinguishable outcomes and no mutation on cancellation. None and accepted lists are distinct; real-backend caller tests cover cancel, clear and replace. Metadata failure recovery still depends on D-08. |
| D-10 — resolved and applied | User approved this specification as behavior authority; Requirements is its feature index, Design covers architecture, AGENTS operational guidance and Future nonbinding proposals. | DOC-01/02 define the roles. Supporting documents were reconciled, stale claims replaced, requirement IDs indexed and pending implementation distinguished from current behavior. |
| D-11 — resolved, partially implemented | User selected `DD-MM-YYYY` for generated TODO dates and accepted legacy-date preservation, generated low/medium/high priorities, consent-only open-task date expansion, unchanged completed dates and unvalidated invalid metadata. | TODO-02/08 define the target. Open-task proposal expansion uses hyphen dates and preserves completed tasks. Structured validated/unvalidated metadata presentation and generated-field validation remain pending. Diary filenames/day-input syntax remain `dd_mm_yyyy`; no storage migration is implied. |
| D-12 — resolved, selection guards implemented | User approved noninteractive listing without prompts/mutations, whole-selection errors for invalid/out-of-range input, and snapshot/task verification before writing with refresh/reselection on stale state. | TODO-03/09/10 define the target. Non-TTY listing, whole numeric-selection validation and affected-file/raw-checkbox snapshot guards are implemented. Cross-file write failures still need D-08 reporting/recovery; no isolation after validation is claimed. |

## 11. Acceptance and verification plan

Use requirement IDs to connect observable behavior to tests. Existing tests provide regression evidence; they do not resolve contradictory requirements or prove live-terminal/backend integration.

D-01 acceptance examples (automated save/consent-path coverage; live terminal/Ollama checks remain separate):

- No LLM transformation: save `- [ ] Call mom tomorrow` unchanged, preserving any submitted trailing spaces and duplicate lines.
- Model configured but no rewrite used: the same verbatim rule applies.
- Changed proposal rejected or unable to obtain consent: retain the original text; do not apply cleanup or filtering.
- Changed proposal accepted: use precisely that proposal, allow subsequent user edits, and save the final submitted body without post-processing.
- Requesting another rewrite requires consent to its new proposal; earlier acceptance is not blanket permission.

[Testing.md](Testing.md) records the retained regression groups, removed/replaced tests, catalog-to-API mapping and deferred obligations. `tests/test_contracts.py` covers exact saves/consent, source-span preservation, ambiguous identities, calendar boundaries, stale TODO batches, non-TTY listing, and distinct tag-selection outcomes. `tests/test_diary_agent.py` retains CLI/config, storage framing, tagging, retrieval and fallback behavior tests.

Tests for unconditional save-time date expansion or duplicate removal are superseded by CAP-06/10–13. Proposal-only duplicate checks remain useful and are labeled as such. Passing a helper test never authorizes applying its transformation without consent.

Run the repository checks from its root:

```bash
python -m py_compile diary_agent.py diary_agent_app/core.py diary_agent_app/llm.py diary_agent_app/ui.py
pytest -q tests/test_diary_agent.py tests/test_contracts.py
```

Use temporary diary/config roots and fake external services in automated behavior tests. Add live Ollama/HTFS and real terminal smoke checks when changing those integration boundaries; report them separately from unit-test results. Tests must assert outcomes and preserved data, not just internal calls.

## 12. Incremental cleanup sequence

1. **Maintain the resolved contract.** D-01 through D-12 are resolved. This specification is the behavior authority; maintain supporting documents under DOC-01/02 as implementation status changes. New behavior decisions require explicit recording rather than reopening resolved choices implicitly.
2. **Establish regression examples.** Run the current suite. Add focused tests for each approved behavior change, including cross-month navigation and unrelated-content preservation where adopted.
3. **Separate decisions from I/O.** Move terminal confirmations out of domain logic, make time-dependent logic controllable, and isolate file access incrementally while retaining the stable CLI entrypoint and adapter boundaries.
4. **Refactor one workflow at a time.** Start with configuration and storage/section parsing, then TODO logic, capture, tagging/search, and viewer integration. Keep behavior changes in separately reviewable steps.
5. **Verify integration and remove dead code.** Exercise no-model, model-enabled, UI-fallback, and backend-failure cases. Update the requirement-to-test mapping and remove obsolete helpers/docs only after replacements are verified.

A cleanup step is complete when its relevant acceptance checks pass, data/CLI compatibility is retained or explicitly changed, applicable documentation agrees, and remaining limitations are recorded. This specification does not require a wholesale rewrite or a new framework.

## 13. Mathematical consistency evidence

Run the independent finite specification models with:

```bash
python3 scripts/specification/check_consistency.py --output docs/specification/evidence.json
```

The checks cover full conjunctions within selected finite contract slices, required-input coverage, inhabited initial states, editor safety, and concrete counterexamples for identity/order/equivalence assumptions. The [model and bounds](specification/MathematicalModel.md) and [review findings](specification/ConsistencyReview.md) are part of the evidence contract. Keep the [generated evidence](specification/evidence.json) current after document or encoding changes.

Permitted error outcomes must be distinguished from successful postconditions. Partial correctness does not imply termination; a blocked external service is not ruled out by these models. Cancellation, accepted empty input, no change and partial persistence must not be conflated when specifying future repairs. No global satisfiability, implementation-conformance, atomicity or unbounded liveness proof is claimed.
