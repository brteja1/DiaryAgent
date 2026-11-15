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
| [`persistence.py`](../diary_agent_app/persistence.py) | Intent journal, explicit outcomes, verified reconciliation and metadata-only retry. |
| [`todo_metadata.py`](../diary_agent_app/todo_metadata.py) | Raw metadata validity interpretation without canonicalizing storage. |
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

## Persistence and recovery

`persistence.py` owns `OperationJournal` and `DiaryPersistence`. The journal stores one JSON record per operation in `.diary-agent/operations/`, using a flushed temporary file and atomic replacement of the record. Its schema records:

- Operation identity/kind/status, error and completion/resolution information.
- Affected filenames with prior/intended UTF-8 content fingerprints and observed write states.
- Section identities, prior/intended resource existence and tag sets, requested hierarchical specs, verified checkpoints and in-flight metadata steps.
- For taxonomy deletion, affected resource associations and expected hierarchy changes, preserving child-before-parent order.

The coordinator records intent before a user-content/metadata mutation. Initial boundary initialization is mandatory startup setup, not a replay of a user operation. Content writes occur first and are observed as committed, not written or uncertain. Only confirmed desired content permits metadata reconciliation. A failed delete write leaves tag associations intact. Interrupted mutations carry their observed state and operation ID to the CLI while preserving status 130. A confirmed write followed by metadata/journal failure is reported as partial; a tag-only unverified mutation or uncertain content is reported as uncertain. No record claims successful completion until closed backend sessions and fresh observations verify the intended state, including requested hierarchical paths when leaf associations were already present.

All application mutations use this boundary: capture append, section edit/delete, checkbox toggle/completion, additive/replacement tags and taxonomy deletion. Direct HTFS primitives remain in the adapter; setup and test fixtures may use them independently of a user operation. Batch TODO intent is recorded before the first file write; partial writes are not described as atomic.

Recovery exposes `list`, `show`, `retry` and explicit `resolve` commands. Retry never calls a Markdown writer. It verifies content fingerprints, target uniqueness and expected prior/checkpoint/in-flight/intended associations before reconciling. Unknown external associations or new resource usage stop taxonomy retries. Unrelated taxonomy nodes are outside that deletion's comparison scope. Captured failure observations only authorize retry when they remain compatible with the operation's recorded tag domain; new foreign tags are not adopted as expected state.

A not-confirmed content change requires inspection, not automatic replay. A completed or explicitly resolved operation returns its retained receipt without applying metadata again, even if the user subsequently edits content or tags. Prior state remains in the record after completion. Resolution records a reason and does not modify content/tags.

Capture acknowledges the saved note before post-save tagging. Rejected-tag lists and exceptions report pending tagging and an operation identity. A failure to prepare a separate tagging intent reports that tagging did not start, retaining the capture receipt. Viewer mutation failures reload available committed content and display the recovery diagnostic.

This implements D-08's sequential recovery contract, not cross-store atomicity, rollback, physical durability, timeout guarantees or race isolation. A process crash can leave prepared/in-flight state requiring inspection; power-loss durability is not promised. Recovery record schema/commands are implementation choices under the approved policy.

## Metadata interpretation and proposal boundaries

`todo_metadata.py` recognizes exact-width valid Gregorian hyphen, ISO and underscore due fields; low/medium/high are the validated priority set. `PendingTask` retains raw `due`/`priority` strings and exposes `due_status`/`priority_status` as absent, validated or unvalidated. Displays annotate unvalidated fields. Checkbox edits splice only the state character, retaining all original bytes.

Proposal preparation expands open-task relative references, then validates newly generated metadata using the original submitted fields as preservation context. Invalid new fields raise before proposal consent; the editor retains its draft and TTY text capture saves its original input with an explanation. Existing explicit/unknown field spellings are not canonicalized by persistence. The model prompt also requests this policy. Ordinary final saves never invoke this guard.

The duplicate pipeline preserves checkbox state: completed history and regular notes cannot stand for an existing open task. Calendar rendering uses explicit four-digit years across the runtime-supported range.

## Verification and evolution

Prefer focused outcome/preservation tests in the existing suite. Backend checks use temporary diary boundaries and the pinned package; model/UI behavior can use callbacks/fakes. Record real terminal/Ollama smoke evidence separately from unit tests.

The [mathematical model](specification/MathematicalModel.md) states selected carriers and bounds; its checks do not establish global consistency or concrete conformance. The [review](specification/ConsistencyReview.md) retains historical conflicts and repair evidence.

Follow the specification's incremental cleanup sequence. Keep the stable entrypoint, readable data and adapter boundaries, remove obsolete helpers after verification, and update status as targets land. [Future.md](Future.md) is nonbinding and does not authorize new tasks.
