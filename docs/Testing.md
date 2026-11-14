# Behavior-focused test audit

Tests are retained when they establish an observable clause of [Specification.md](Specification.md), a documented failure outcome, or preservation of user data. Implementation shape, wrapper existence, widget-constructor arguments and incidental call counts are not product requirements.

The audit uses the external [mathematical-tests skill](/linuxdev/github/mathematical-abstractions/ai/skills/mathematical-tests/SKILL.md). Test docstrings name their specification IDs. Mathematical properties are selected from actual behavior; most CLI behavior needs a direct acceptance oracle rather than an algebraic law.

## Retained and replacement coverage

| Test group | Contract and observation |
| --- | --- |
| Config/startup in `test_diary_agent.py` | CFG-01–04, DEP-01–02: parsing, optional model, legacy backend override ignored, bundled origin, preflight failure before content writes. |
| Storage/identity in both modules | DATA-01–08: exact framing and serials, recognized delimiters, unique/missing/ambiguous targets. |
| Capture in `test_contracts.py` | CAP-01/02/04/06/07/10–13: final exact text, duplicates retained without consent, TTY proposal acceptance/rejection/empty result/failure, unattended capture, enabled callbacks. |
| Editor action tests | CAP-04, QUAL-02: busy prevents submit/overlap; displayed proposals block submit until accept/reject; failure retains the draft and releases the lock. Real bindings and buffers are exercised with a deterministic scheduled executor result. |
| TODO tests | TODO-01–05/09/10: all-Markdown discovery, metadata retention, proposal-only duplicate advice, read-only unattended listing, whole-selection rejection and stale-batch guards. Checkbox mutations retain all other bytes. |
| Viewer tests | VIEW-01–09: default/missing-day handling, read-only typing, boundaries, real navigation/tag key bindings, exact unrelated-byte preservation and ambiguous mutation guards. |
| Tag commands/integration | TAG-01–07: resource mapping, hierarchy, explicit creation, additive application, explicit suggestions, taxonomy-deletion safeguards, cancel/clear/replace outcomes. Persistence tests reopen the actual pinned HTFS backend in temporary boundaries. |
| Search/model context | SEARCH-01–06, CAP-03: matching excerpts/tags, restrictions, no-model/model-error fallbacks, supplied context, heading removal and nested bullets. |

Doubles remain at terminal/service boundaries where they make the test independent of an interactive terminal or model. They are not used to replace the domain operation under assertion. Some routing tests inspect callback payloads because selecting the intended section/backend resource is itself required behavior.

## Removed or replaced tests

Twenty-seven old test functions were removed; replacement coverage is grouped rather than preserving one function for every old helper.

| Old expectation or structure | Disposition |
| --- | --- |
| Two `append_entry_skips_reworded_duplicate_*` tests and `run_capture_reports_duplicate_update` | Removed unconditional save-time deletion expectations. CAP-06/10–13 require duplicates to survive without accepted LLM changes. New exact-input/consent tests cover this. |
| Mocked noninteractive capture that expected automatic synthesized output | Replaced with actual-file unattended capture checks: model configuration supplies no consent. |
| Separate append nesting/verbatim/date tests and section-edit relative-date test | Consolidated into exact Unicode/indentation/metadata/trailing-whitespace cases and localized body edits. Date expansion is tested only in proposal preparation. |
| Four heavily mocked interactive capture tests | Replaced by final-buffer persistence, model-dependent callbacks, actual editor proposal transitions and direct proposal preparation checks. Post-save tagging coverage remains. |
| Two large viewer construction/callback tests | Replaced by actual prompt_toolkit bindings and final backend/file observations. Read-only behavior and navigation boundaries remain covered. |
| Editor/tag/similarity dialog thread-flag tests | Removed assertions limited to a flag or obsolete presentation path. Action/loop-state tests and real viewer key bindings remain; live nested-terminal execution remains a separate integration check. The unused similarity-confirmation dialogs were deleted. |
| `ensure_storage`, `get_htfs_adapter` initialization and leaf-projection helper tests | Removed duplicate/helper-only examples. Actual capture creates storage, CLI preflight initializes HTFS, and real hierarchical-tag/resource tests cover leaf semantics. The test equating an empty database file with initialized HTFS was also removed; readiness requires the startup backend checks, not mere file existence. |
| Today-context forwarding and mocked completion-message tests | Removed unused-wrapper/display-constructor checks. Proposal context and checkbox/source outcomes are the relevant obligations. |
| Two same-month adjacent-entry examples and callback-wiring test | Replaced by calendar-boundary order, no-neighbor behavior and real key-dispatch outcomes. |

Existing duplicate-helper tests were renamed as **proposal** tests. They test permitted advisory transformations; they do not authorize those transformations during final save. Existing legacy ISO metadata fixtures remain valid read-compatibility cases, not a generated-date policy.

No failing requirement test was deleted to hide a defect. Replaced expectations were checked against the approved clauses; affected production paths were repaired where the replacement exposed consent, date-order, span-preservation or selection defects. Pending contracts are listed below rather than weakened.

## Mathematical mapping

Catalog availability: `catalog.py check` reported 220 concepts, 2,132 nodes, no errors. Bounded queries used ONTFS/SPARQL with projection input SHA-256 `a14ad4c82c1c589682e9344a9737e19ea6c7eee8cc939cf5a5a7ea56dc2be49a`. A scratch projection was built outside the catalog checkout, preserving that checkout. All selected pages returned completely; no premise closure, theorem witness or inherited specialization law was assumed.

IDs below have prefix `urn:csabs:`.

| Basis and assumptions | Complete API correspondence | Obligation and finite domain |
| --- | --- | --- |
| `concept/TotalOrder`, `operation/TotalOrder-basis-le`, `axiom/TotalOrder-transitive`. Carrier: valid supported Gregorian dates; ordinary date equality/comparison. | Fixture files construct the history; `dated_diary_files`, `entry_options`, `latest_diary_file`, `adjacent_entry` expose the order. Filenames are observed as paths but compared through their dates. Missing neighbors are partial results, not extra dates. | Literal independently supplied three-date order crosses year/month boundaries; tests verify ascending history, descending picker, latest, both neighbors of each entry and boundary `None`. Non-date/malformed/impossible files stay available to task scans. This tests product ordering, not Python date axioms in isolation. |
| `concept/OptionType`; `operation/option-none`, `OptionType-some`, `option-case`; `axiom/option-case-none`, `option-case-some`. Pure equations assume total, correctly typed functions. | `prompt_for_section_tags` supplies absence (`None`) or a present accepted list (including `[]`). The viewer's `t` binding is case analysis; `set_section_tags` is the accepted branch. `get_section_tags` after reopening backend sessions observes the final association set. Fixture setup constructs `{Old}` through the real adapter. | Successful-operation cases: cancellation retains `{Old}`, accepted-empty clears it, accepted `{New}` replaces it. Lists are payloads, not truth values. Backend failure/recovery and taxonomy deletion are separate effects, outside these pure equations. |
| `concept/HoareTriple`, `operation/HoareTriple-basis-holds`. Partial correctness: only terminating executions satisfying the precondition have the required postcondition. | `Path.write_bytes` constructs a source snapshot; `update_section`/`delete_section` mutate a uniquely delimited span; `Path.read_bytes` observes exact UTF-8 equality. Prefix/suffix expectations are literal fixture strings, independent of the implementation parser. | Edit/delete × LF/CRLF, with Unicode preamble, trailing spaces, unrelated sections and no final newline. All outside bytes survive. Missing/duplicate target tests assert the specified no-write/error outcomes separately; undefined unique lookup is not silently assigned a success. |

TotalOrder's selected axiom has `provenanceStatus: legacy-source-missing`. Option case axioms cite `urn:csabs:source/awodey-types` and carry `reviewStatus: editorial-summary; not machine-proved`. The Hoare operation states partial correctness; it supplies no termination or storage guarantee. These source/semantic limits are retained, not repaired by passing tests.

Exact normalized-key equality and heuristic near-matching remain different relations (CAP-11). No transitivity property is imposed on the latter; [Refactoring.md](Refactoring.md) records a counterexample. Editor tests exercise a finite event schedule with explicit completion and consent; they claim no fairness, liveness or universal concurrency safety.

## Execution and deferred obligations

```bash
python -m py_compile diary_agent.py diary_agent_app/*.py
pytest -q tests/test_diary_agent.py tests/test_contracts.py
ruff check diary_agent.py diary_agent_app tests --select F
python3 scripts/specification/check_consistency.py --output docs/specification/evidence.json
```

The automated suite passes 106 cases. A CLI smoke check with injected temporary configuration also passed capture, read-only TODO listing, hierarchical tag application and tag-only search against the bundled backend; the executable help path was checked separately. This is finite acceptance/regression evidence, not full specification conformance. The independent consistency checker constructs reference models and does not test production code.

Still deferred:

- PERSIST-01–05: intent journal, truthful partial/uncertain cross-store outcomes, metadata-only retries and replay receipts. Current cross-store success tests do not establish failure recovery or content-first deletion ordering.
- TODO-08: structured validated/unvalidated metadata presentation and validation of newly generated fields. Raw text is preserved and open-task proposal date expansion uses `DD-MM-YYYY`; this is only part of D-11.
- Live Ollama responses, actual nested-terminal rendering/thread execution, physical write failures and races after snapshot validation. UI tests replace terminal execution, and model tests use supplied responses.

Add tests for those contracts with their implementations. Do not restore expectations contradicting consent/verbatim requirements, or add universal algebraic laws whose premises the software does not meet.
