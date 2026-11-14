# Diary Agent architecture

This document describes the current implementation and the architectural changes needed for approved targets. [Specification.md](Specification.md) is the behavior authority; [Requirements.md](Requirements.md) is its feature index. Design explanations do not override clauses or imply that pending targets are implemented.

## Current module boundaries

| Module | Current responsibilities |
| --- | --- |
| [`diary_agent.py`](../diary_agent.py) | CLI routing, `DiaryAgent`, file/section operations, TODO orchestration, search composition and compatibility wrappers. It still contains substantial domain/storage logic. |
| [`core.py`](../diary_agent_app/core.py) | Config parsing/prompting/I/O, date/TODO helpers, tokenization, lexical scoring and shortlisting. It is not wholly side-effect-free. |
| [`models.py`](../diary_agent_app/models.py) | Frozen `AppConfig`, `PendingTask`, `SimilarTodoMatch`, `DiaryEntryOption`, `DiarySection` and `SearchResult` records. Config has diary directory and optional model. |
| [`llm.py`](../diary_agent_app/llm.py) | Ollama calls for LLM-01's five tasks, prompts, heading cleanup and model errors. |
| [`htfs_adapter.py`](../diary_agent_app/htfs_adapter.py) | Bundled import/origin validation, client lifecycle, resource mapping, hierarchy/tag operations and queries. |
| [`ui.py`](../diary_agent_app/ui.py) | Editor, dialogs, viewer, picker, tag completion, background feedback and event-loop-safe subsidiary prompts. |
| [`deps/HTFS`](../deps/HTFS) | Pinned upstream backend owning SQLite/RDF tag storage and hierarchy/query semantics. |
| [`tests/test_diary_agent.py`](../tests/test_diary_agent.py) | Application regressions and temporary-boundary HTFS integration checks. |
| [`check_consistency.py`](../scripts/specification/check_consistency.py) | Independent finite contract models, not an implementation oracle. |

HTFS access stays behind the adapter. UI code uses callbacks; domain policy should not gain terminal dependencies. Improve these boundaries incrementally without a new framework or incidental storage migration.

## Current startup

The CLI parses arguments first, so help needs no backend initialization. Operational startup validates the bundled HTFS import, loads config, constructs `DiaryAgent`, creates the diary directory if needed, initializes/reads the tagging boundary, and dispatches the command. Failed preflight reports an error before diary-content writes.

The parent gitlink pins `deps/HTFS`; setup installs local source through `requirements.txt`. No `tagfs` executable or external checkout is discovered. Legacy `htfs_path` and `DIARY_AGENT_HTFS_PATH` values are ignored. See [HTFS.md](HTFS.md).

Ollama/model availability and prompt_toolkit presentation are optional. Their workflow-specific fallbacks do not bypass mandatory HTFS (DEP-01–02).

## Current data and workflow composition

Diary content is UTF-8 Markdown. Filenames supply dates; recognized timestamp headings delimit sections. `DiarySection.section_id` derives filename/heading identity; HTFS resources use absolute file paths plus heading fragments. Metadata stays in `.tagfs.db` and `.tagfs.ttl` in the diary boundary, outside dependency source.

`run_capture` selects an editor/stdin path or `--text`. A successful interactive save is followed by section tagging, never a TODO-review prompt. Current saves still normalize checkbox dates and trim text; processed capture also filters duplicates, and model-enabled `--text` synthesizes automatically. These behaviors do not yet satisfy D-01.

`run_todos` scans checkbox lines across immediate Markdown files and uses the shared checklist or numeric-input fallback. Task locations currently use source paths and one-based line numbers. D-11 metadata and D-12 selection contracts are approved but pending implementation; the current numeric path can prompt unattended and silently ignore out-of-range indices, and completion lacks snapshot guards.

`run_show_day` handles day lookup, missing-today substitution and viewer callbacks. The text area is read-only for typing; explicit actions mutate content/tags. Subsidiary prompts use suspended terminal rendering and thread mode where needed. Current filename sorting, section reconstruction and tag-dialog result encoding need the approved fixes below.

Search scores section-body chunks and tags, optionally restricting section IDs through HTFS. No-model queries print local results; answer-synthesis failures can fall back to the same excerpts. Tag-filter translation/query failures do not silently become unfiltered searches. HTFS read errors propagate rather than appearing as absent tags.

The five LLM operations are rewrite/TODO classification, TODO similarity, answer synthesis, explicit tag suggestions and natural-language filter translation. Rewrite cleanup strips generated headings and preserves useful nested bullets. The current editor applies the returned rewrite directly; D-01 requires a separate review/acceptance state for the complete proposal.

## Changes required by decided targets

| Target | Current gap | Intended implementation responsibility |
| --- | --- | --- |
| D-01; CAP-04/06/10–13, TODO-02/04–05 | Immediate rewrite replacement and automatic save-time transformation. | Generate/clean a complete candidate before consent; persist the final user-controlled body unchanged. |
| D-04; DATA-06, VIEW-03 | Shared filename-sorted navigation/picker list. | Separate all-Markdown scans from valid-dated-file selection; use calendar comparison. |
| D-05; DATA-07–09 | First-match lookup can hide duplicate headings. | Distinguish missing/unique/ambiguous targets; block ambiguous operations while preserving raw viewing/content. |
| D-06; VIEW-08–09 | Mutation reconstructs files from parsed sections. | Retain exact source spans and preserve all bytes outside a safely located target. |
| D-08; PERSIST-01–05 | HTFS-first deletion, suppressed cleanup errors and replacement without recovery records. | Record intent/prior tags, commit combined content changes first, reconcile/verify metadata, and expose safe retry/completion receipts. |
| D-09; TAG-07 | Cancellation and accepted-empty both return `[]`. | Use distinct outcomes; cancellation calls no mutation, accepted selection enters recovery-aware replacement. |
| D-11; TODO-02/08 | Current helpers mechanically expand dates in both open and completed checkboxes, emit underscore dates and accept metadata without structured validation. | Generate `DD-MM-YYYY` only in accepted proposals for open tasks; validate known date/priority forms without rewriting legacy text. Preserve completed dates and invalid/unknown metadata. |
| D-12; TODO-03/09/10 | TTY assumptions, partial acceptance of invalid selections and line-number-only mutation. | Route non-TTY `todos` to listing only. Validate all selections before writing and compare affected-file snapshots plus raw selected tasks; reject stale state for refresh/reselection. Snapshot guards do not imply multi-file atomicity or race isolation. |

D-02 routing, D-03's task inventory and D-07's mandatory dependency agree with their selected contracts. D-10 changes document roles, not runtime architecture.

## Recovery design boundary

PERSIST-01–05 define the target. Journal schema/location and recovery CLI still need implementation. Records retain identities, expected/intended content fingerprints, prior/intended associations, and progress/errors; tags cannot be reconstructed from diary text alone.

Combined changes commit Markdown before HTFS reconciliation. Post-save tagging is a separate metadata operation. Retry inspects current state, stops on divergence/ambiguity, and never reexecutes capture or content mutation. Verified completion retains a receipt preventing replay even after manual changes. Account for backend close/flush/readback before success.

This is an approved architectural obligation, not an existing transaction mechanism. No atomicity across Markdown/SQLite/RDF, automatic rollback, arbitrary concurrent-edit protection or power-loss durability is asserted. Mandatory startup does not prevent later failures.

## Verification and evolution

Prefer focused outcome/preservation tests in the existing suite. Backend checks use temporary diary boundaries and the pinned package; model/UI behavior can use callbacks/fakes. Record real terminal/Ollama smoke evidence separately from unit tests.

The [mathematical model](specification/MathematicalModel.md) states selected carriers and bounds; its checks do not establish global consistency or concrete conformance. The [review](specification/ConsistencyReview.md) retains historical conflicts and repair evidence.

Follow the specification's incremental cleanup sequence. Keep the stable entrypoint, readable data and adapter boundaries, remove obsolete helpers after verification, and update status as targets land. [Future.md](Future.md) is nonbinding and does not authorize new tasks.
