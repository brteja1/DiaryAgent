# Diary Agent architecture

This document describes the current implementation and the architectural changes needed for approved targets. [Specification.md](Specification.md) is the behavior authority; [Requirements.md](Requirements.md) is its feature index. Design explanations do not override clauses or imply that pending targets are implemented.

## Current module boundaries

| Module | Responsibilities |
| --- | --- |
| [`diary_agent.py`](../diary_agent.py) | Stable executable entrypoint and `DiaryAgent` import. |
| [`cli.py`](../diary_agent_app/cli.py) | Argument parsing, mandatory startup preflight, dispatch and exit status. |
| [`commands.py`](../diary_agent_app/commands.py) | User workflows, terminal confirmations and command output. |
| [`service.py`](../diary_agent_app/service.py) | `DiaryAgent`: storage, navigation, TODO and search operations; no terminal UI dependency. |
| [`markdown.py`](../diary_agent_app/markdown.py) | One timestamp parser, immutable source spans, unique lookup and localized mutation. Reads/writes retain line endings. |
| [`core.py`](../diary_agent_app/core.py) | Config I/O, date/TODO parsing, lexical scoring and shortlisting. |
| [`models.py`](../diary_agent_app/models.py) | Shared immutable records; pending tasks carry their source snapshot. |
| [`llm.py`](../diary_agent_app/llm.py) | Five task-specific prompts over one Ollama transport/error boundary. |
| [`htfs_adapter.py`](../diary_agent_app/htfs_adapter.py) | The sole HTFS boundary; one context manager closes every backend session. |
| [`ui.py`](../diary_agent_app/ui.py) | Capture editor, proposal review, dialogs, tag completion and shared background-action lifecycle. |
| [`viewer.py`](../diary_agent_app/viewer.py) | Read-only viewer, picker and explicit navigation/mutation key bindings. |
| [`deps/HTFS`](../deps/HTFS) | Pinned backend owning SQLite/RDF storage and tag hierarchy/query semantics. |

Dependencies flow from the entrypoint to CLI, commands, and domain/UI boundaries. The service uses core, Markdown, models, LLM and HTFS; it does not import commands or UI. Viewer/editor use callbacks for domain operations. No generic repository, transaction framework or algebraic class hierarchy was introduced.

The [discovery report](Refactoring.md) records duplication counts and abstraction choices. [Testing.md](Testing.md) records behavior coverage, removed tests and mathematical mappings. The finite specification checker remains independent of application tests.

## Current startup

The CLI parses arguments first, so help needs no backend initialization. Operational startup validates the bundled HTFS import, loads config, constructs `DiaryAgent`, creates the diary directory if needed, initializes/reads the tagging boundary, and dispatches the command. Failed preflight reports an error before diary-content writes.

The parent gitlink pins `deps/HTFS`; setup installs local source through `requirements.txt`. No `tagfs` executable or external checkout is discovered. Legacy `htfs_path` and `DIARY_AGENT_HTFS_PATH` values are ignored. See [HTFS.md](HTFS.md).

Ollama/model availability and prompt_toolkit presentation are optional. Their workflow-specific fallbacks do not bypass mandatory HTFS (DEP-01–02).

## Current data and workflow composition

Diary content is UTF-8 Markdown. Filenames supply dates; recognized timestamp headings delimit sections. `DiarySection.section_id` derives filename/heading identity; HTFS resources use absolute file paths plus heading fragments. Metadata stays in `.tagfs.db` and `.tagfs.ttl` in the diary boundary, outside dependency source.

`run_capture` selects the editor/stdin path or `--text`. Final saves share verbatim persistence. An editor rewrite shows the complete candidate in the locked buffer: `Alt+Y` accepts, `Alt+N` restores the original draft. Submit and overlapping actions are blocked while work or proposal review is active. One shared background helper releases the work lock on success/failure. Tag suggestions leave text unchanged.

TTY `--text` may generate a proposal and asks for acceptance after all cleanup. Decline/failure saves the original. Unattended capture saves original text without requesting an LLM transformation. Successful editor capture offers tags afterwards; capture never opens TODO review.

`run_todos` lists without prompting in non-TTY mode. Interactive checklist/numeric selection uses tasks scanned once. Numeric input validates the whole selection. Before any write, the service rereads affected files and checks their source snapshots and selected open-checkbox locations. State changes splice only the checkbox character, retaining metadata, whitespace and line endings. There is no isolation against changes after validation or atomicity across file writes.

Navigation parses valid calendar-date filenames separately from all-Markdown history scans. `DiaryDocument` retains offsets into the original text, including preambles and CRLF. Edits replace only the body span and deletion removes only the selected section span. Duplicate IDs remain readable but unique lookup guards section mutations.

Tag dialogs return `None` for cancellation and a list for accepted selections, including `[]` for an explicit clear. Viewer callers branch on presence rather than truthiness. Backend session cleanup is centralized; backend errors are not converted into successful results.

Search scores section-body chunks and tags, optionally restricting section IDs through HTFS. No-model queries print local results; answer-synthesis failures can fall back to the same excerpts. Tag-filter translation/query failures do not silently become unfiltered searches. HTFS read errors propagate rather than appearing as absent tags.

The five LLM operations are rewrite/TODO classification, TODO similarity, answer synthesis, explicit tag suggestions and natural-language filter translation. Rewrite cleanup strips generated headings and preserves useful nested bullets. Proposal cleanup happens before review; persistence does not repeat it.

## Remaining implementation work

D-01 consent/verbatim paths, D-04 calendar selection, D-05 uniqueness guards, D-06 byte preservation, D-09 distinct selection outcomes and D-12 selection guards have focused acceptance coverage. D-09 metadata failures still require D-08 recovery. D-11 open-task proposal expansion now emits `DD-MM-YYYY` and leaves completed tasks alone; validated versus unvalidated metadata presentation is still pending.

D-08 remains an architectural gap: there is no recovery journal or retry/receipt command, deletion still performs metadata cleanup before the content write, and tag replacement can partially fail after clearing old associations. Do not describe these operations as atomic or safely retryable. These gaps require a persistence-focused change with fault-injection acceptance tests.

## Recovery design boundary

PERSIST-01–05 define the target. Journal schema/location and recovery CLI still need implementation. Records retain identities, expected/intended content fingerprints, prior/intended associations, and progress/errors; tags cannot be reconstructed from diary text alone.

Combined changes commit Markdown before HTFS reconciliation. Post-save tagging is a separate metadata operation. Retry inspects current state, stops on divergence/ambiguity, and never reexecutes capture or content mutation. Verified completion retains a receipt preventing replay even after manual changes. Account for backend close/flush/readback before success.

This is an approved architectural obligation, not an existing transaction mechanism. No atomicity across Markdown/SQLite/RDF, automatic rollback, arbitrary concurrent-edit protection or power-loss durability is asserted. Mandatory startup does not prevent later failures.

## Verification and evolution

Prefer focused outcome/preservation tests in the existing suite. Backend checks use temporary diary boundaries and the pinned package; model/UI behavior can use callbacks/fakes. Record real terminal/Ollama smoke evidence separately from unit tests.

The [mathematical model](specification/MathematicalModel.md) states selected carriers and bounds; its checks do not establish global consistency or concrete conformance. The [review](specification/ConsistencyReview.md) retains historical conflicts and repair evidence.

Follow the specification's incremental cleanup sequence. Keep the stable entrypoint, readable data and adapter boundaries, remove obsolete helpers after verification, and update status as targets land. [Future.md](Future.md) is nonbinding and does not authorize new tasks.
