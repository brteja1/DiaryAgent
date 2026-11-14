# Requirements summary

[Specification.md](Specification.md) is the authoritative behavior contract under D-10. This document is a feature index referencing its stable requirement IDs; it defines no independent behavior. Direct user decisions take precedence and must be recorded in the specification.

The specification distinguishes baseline behavior and approved targets. All twelve recorded decisions are resolved; implementation gaps remain. Passing regressions do not establish conformance to unimplemented targets. See [Design.md](Design.md) for architecture and [the consistency review](specification/ConsistencyReview.md) for scoped mathematical evidence.

## Feature index

| Area | Summary | Specification IDs |
| --- | --- | --- |
| Storage | Daily UTF-8 Markdown, timestamp headings/serials, strict explicit or relative day input. | DATA-01–05 |
| History and navigation | All immediate Markdown files in TODO/text scans; valid dated files and calendar order for day navigation and newest-first picker. | DATA-06, VIEW-01–03 |
| Section identity | Filename/timestamp IDs, reserved delimiters, missing/unique/ambiguous lookup and explicit metadata migration. | DATA-07–09 |
| CLI/config | Stable entrypoint, command outcomes, configured diary directory and optional model. | CLI-01–02, CFG-01–04 |
| Mandatory HTFS | Pinned bundled submodule, Python API and startup preflight; no external backend discovery. | DEP-01–02, TAG-01 |
| LLM tasks | Rewrite/TODO classification, TODO similarity, answers, explicit tag suggestions and tag-filter translation. | LLM-01 |
| Interactive capture | Single editor, explicit background actions, proposal consent, final-body preservation and post-save tagging. | CAP-01–08, CAP-13 |
| Text capture | Changed output requires consent to a complete LLM-associated proposal; otherwise retain original text. | CAP-09–13 |
| TODOs | Persistent checkboxes, metadata, advisory duplicates/similarity and explicit review. Generated dates use `DD-MM-YYYY`; preserve legacy/unvalidated values. Read-only unattended listing, validated selections and stale-snapshot guards. | TODO-01–10 |
| Viewer mutations | Explicit checkbox/edit/delete/tag actions and exact preservation outside a unique target. | VIEW-04–09 |
| Tags | HTFS hierarchy, explicit creation, section associations, taxonomy commands and distinct cancelled/accepted selections. | TAG-02–07 |
| Search | Local retrieval, tag restrictions, excerpt-based answers and scoped model-error fallbacks. HTFS remains mandatory. | SEARCH-01–06 |
| Recovery | Markdown content authority, recorded intent, truthful partial/uncertain outcomes and metadata-only retries. | PERSIST-01–05 |
| Engineering | Local readable data, event-loop-safe UI, clear failures and compatible data/CLI formats. | QUAL-01–04 |
| Documentation | One behavior authority; supporting summaries, design, guidance and nonbinding roadmap. | DOC-01–02 |

## Implementation status

| Decision | Status at this documentation update |
| --- | --- |
| D-01: consent/verbatim saves | Approved; automatic processing and immediate rewrite application need changes. |
| D-02: review only through `todos` | Approved; capture routing agrees. |
| D-03: five LLM tasks | Approved; existing operations retained and documentation aligned. |
| D-04: calendar navigation | Approved; lexical navigation/picker need correction. |
| D-05: identity/duplicate guards | Approved; duplicate-aware guards need implementation. |
| D-06: targeted byte preservation | Approved; whole-file reconstruction needs replacement. |
| D-07: bundled mandatory HTFS | Implemented and integration-tested; setup is in [HTFS.md](HTFS.md). |
| D-08: persistence/recovery | Approved; records, receipts and retry actions need implementation. |
| D-09: cancellation/accepted-empty | Approved; current UI/caller outcomes need repair. |
| D-10: document authority | Applied in documentation; no application behavior changed. |
| D-11: TODO metadata interpretation | Approved; consent-only open-task expansion, `DD-MM-YYYY` generation and structured validation/preservation need implementation. |
| D-12: unattended/stale TODO selection | Approved; TTY routing, whole-selection validation and source/task snapshot guards need implementation. |

## Verification

Use the commands and acceptance plan in [Specification.md](Specification.md). Keep this index aligned as decisions and implementations change. Mathematical models, application tests and live integration checks are separate evidence. [Future.md](Future.md) is a proposal archive, not additional requirements.
