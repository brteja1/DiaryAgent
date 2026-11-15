# Requirements summary

[Specification.md](Specification.md) is the authoritative behavior contract under D-10. This document is a feature index referencing its stable requirement IDs; it defines no independent behavior. Direct user decisions take precedence and must be recorded in the specification.

The specification distinguishes baseline behavior and approved targets. All twelve recorded decisions are resolved; integration verification limits remain; see the conformance review. Passing regressions do not establish conformance to unimplemented targets. See [Design.md](Design.md) for architecture and [the consistency review](specification/ConsistencyReview.md) for scoped mathematical evidence.

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

The approved contracts have regression and fault-injection coverage. The [conformance review](conformance/ConformanceReview.md) records repaired violations and remaining unchecked integration behavior; passing tests are not a universal conformance proof. All twelve recorded decisions are resolved in specification v1.0. The [specification](Specification.md) owns the exact targets and acceptance examples; the review records the tested scope and unverified terminal/model behavior.

| Decision | Status at this documentation update |
| --- | --- |
| D-01: consent/verbatim saves | Save/consent paths implemented; tests cover original/proposal selection and exact persistence. |
| D-02: review only through `todos` | Approved; capture routing agrees. |
| D-03: five LLM tasks | Approved; existing operations retained and documentation aligned. |
| D-04: calendar navigation | Implemented using parsed dates, including month/year boundaries. |
| D-05: identity/duplicate guards | Unique/missing/ambiguous lookup and mutation guards implemented. |
| D-06: targeted byte preservation | Implemented using exact source spans and byte-preservation tests. |
| D-07: bundled mandatory HTFS | Implemented and integration-tested; setup is in [HTFS.md](HTFS.md). |
| D-08: persistence/recovery | Recorded intent, content-first operations, partial/uncertain outcomes, metadata-only retries and retained receipts are implemented and fault-tested. |
| D-09: cancellation/accepted-empty | Cancel/clear/replace and recorded failure recovery are implemented and tested. |
| D-10: document authority | Applied in documentation; no application behavior changed. |
| D-11: TODO metadata interpretation | Open-task proposal dates use `DD-MM-YYYY`; generated fields are validated; legacy/unvalidated fields retain their spelling and expose validity status. |
| D-12: unattended/stale TODO selection | Selection guards and read-only unattended listing implemented; cross-file failures retain partial/uncertain records without replaying content. |

## Verification

See [Testing.md](Testing.md) for behavior coverage and the test audit. Use the commands and acceptance plan in [Specification.md](Specification.md). Keep this index aligned as decisions and implementations change. Mathematical models, application tests and live integration checks are separate evidence. [Future.md](Future.md) is a proposal archive, not additional requirements.
