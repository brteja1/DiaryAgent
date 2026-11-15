# Diary Agent implementation conformance review

Version 1.0, baseline `c6432d3`. **The implementation does not fully conform to specification v1.0.** The review found six runtime issue groups and one documentation defect. It maps every numbered requirement, while distinguishing supported slices from violations and unchecked behavior.

This review applies the external [implementation-conformance skill](/linuxdev/github/mathematical-abstractions/ai/skills/implementation-conformance/SKILL.md) against the [explicit implementation mapping](ImplementationMapping.md), constructed with implementation-mapping. The [machine mapping](mapping.json) and [execution evidence](evidence.json) hold source hashes, versions, selected catalog records and exact observed traces. The specification is unchanged by this audit; production repairs are not included.

## Evidence and scope

The 106 existing tests pass at this revision. Eleven additional review probes produced **nine violating observations and two supported observations**. Those probes and static inspection classify **57 of 74 clauses as supported within their stated scope, 14 as violated, and three as unchecked**. Several violations share one root cause; these counts are neither an issue count nor a percentage of correctness.

“Supported within scope” may mean static inspection plus a specific unit trace; it does not mean every input/environment branch has been executed. The evidence table retains those limits for each clause. A missing test is not automatically a violation. Confirmed counterexamples below violate the actual requirement, without strengthening preconditions, changing equality or excluding a required date/failure input.

The review inspected all application modules, the CLI entrypoint, applicable tests and specification clauses. It uses the bundled HTFS backend on temporary boundaries; external terminal/model/failure stimuli are controlled at their boundary. No live diary, actual Ollama server or physical terminal was used. No compiled implementation-refinement proof, global consistency proof, durability, liveness or universal scheduling result is claimed.

## Findings

### F01 — High: removing optional prompt_toolkit prevents CLI import

- **Clauses / obligations:** CAP-08 / O-CAP-08, VIEW-02 / O-VIEW-02, QUAL-03 / O-QUAL-03. Interpretation: editor/fallback and outcome profiles; `TransitionSystem-post`, `HoareTriple-basis-holds` provide vocabulary, while these fallback requirements come directly from the product contract.
- **Location:** [ui.py](../../../../diary_agent_app/ui.py), ImportError fallback at line 32; [viewer.py](../../../../diary_agent_app/viewer.py), import at line 7; startup chain through commands and CLI.
- **Trigger:** a fresh child interpreter blocks imports of optional `prompt_toolkit`, then imports `diary_agent_app.cli`. Nothing is uninstalled or changed in the host environment.
- **Expected:** CLI imports and can dispatch documented stdin/stdout workflows without the terminal package; operational HTFS preflight still applies.
- **Actual:** `ImportError: cannot import name 'run_in_terminal' from 'diary_agent_app.ui'`. The optional-import fallback does not define that name, and viewer imports it unconditionally. The failure happens before the intended UI fallback or CLI exception boundary.
- **Evidence:** P01-optional-ui-import, fresh-process execution. Existing fallback tests mocked `require_prompt_toolkit` after importing everything with the package installed, so they missed this path.
- **Repair obligation:** make the optional UI boundary importable and add an actual absent-package process test covering fallback dispatch. Do not make prompt_toolkit mandatory to avoid its required fallback.

### F02 — High: cross-store mutation has no required recovery protocol and deletion runs in the wrong order

- **Clauses / obligations:** PERSIST-01–05 / O-PERSIST-01–05, TAG-07 / O-TAG-07. Interpretation: outcomes/store profiles and `HoareTriple-basis-holds`; required partial/uncertain/retry policy is the product contract, not a promise of atomicity.
- **Locations:** [service.py](../../../../diary_agent_app/service.py), `delete_section` at line 378 and `set_section_tags` at line 389; [htfs_adapter.py](../../../../diary_agent_app/htfs_adapter.py), cleanup methods; [cli.py](../../../../diary_agent_app/cli.py), command surface.
- **Trigger A:** one Markdown section tagged `Old`; inject a content-write failure when deleting it.
- **Expected A:** persist intent first; confirm Markdown deletion before removing its metadata. A failed content commit cannot already have deleted the prior associations.
- **Actual A:** Markdown remains unchanged, but tags read back as `[]`. `delete_section` deletes the backend resource before calling `write_markdown`.
- **Trigger B:** replace `{Old}` with `{New}` and inject failure at the actual tagging boundary after old associations have been cleared.
- **Expected B:** retain operation identity and prior/intended state sufficient for reconciliation; report partial/uncertain state. Automatic rollback is not required.
- **Actual B:** associations are `[]`, an exception is raised and no recovery intent/receipt is present. There is no explicit metadata-retry/receipt workflow. Source inspection finds no journal/operation/retry implementation.
- **Evidence:** P02-delete-write-failure, P03-tag-replacement-failure and P10-recovery-interface. The first two use real temporary HTFS stores; the third combines actual parser inspection with complete runtime-source inspection. The absence conclusion is a pinned static review supported by the trace, not a generic grep-based proof for future code.
- **Repair obligation:** implement intent establishment, content-first mutation, truthful outcomes, verified metadata reconciliation and replay-safe metadata-only retries/receipts, including failures at close/flush/readback. Preserve the existing no-atomicity/no-automatic-rollback limits.

This was already documented as pending D-08. The audit confirms concrete consequences rather than excusing the approved requirement as out of scope.

### F03 — High: post-capture tagging failure is reported as generic failure or complete success

- **Clauses / obligations:** PERSIST-03 / O-PERSIST-03, QUAL-03 / O-QUAL-03. CAP-07's save-before-tag ordering itself is supported; the violated obligation is truthful reporting after the later failure.
- **Locations:** [commands.py](../../../../diary_agent_app/commands.py), `_capture_in_editor` at line 86, unchecked `tag_section` result at line 118, success output after tagging; [cli.py](../../../../diary_agent_app/cli.py), generic RuntimeError handling.
- **Trigger A:** save a note, accept tag `New`, then the tagging adapter raises.
- **Expected:** explicitly acknowledge the confirmed saved note plus pending/partial tagging and recovery identity. Exact wording is unspecified.
- **Actual A:** status 1, note exists, stdout empty, stderr only `Error: injected tagging failure`. The user is not told that the content was saved, making a retry liable to duplicate capture.
- **Trigger B:** adapter returns the nonempty rejected-tag list instead of raising.
- **Actual B:** the capture ignores that list and returns status 0 with ordinary `Updated …` output, although the requested tagging failed. This is false complete-success reporting, not a harmless empty result.
- **Evidence:** P04-capture-tag-exception and P05-capture-tag-rejected use full `cli.main`, real preflight/content persistence and controlled adapter outcomes. These are static outcome classifications supported by recorded stdout/stderr/bytes, not exact-message-string oracles.
- **Repair obligation:** consume backend failure results and expose content/metadata outcome separately, with D-08 recovery information. A generic top-level exception cannot represent every failure state.

### F04 — Medium: TODO metadata lacks required validation observations and generation constraints

- **Clause / obligation:** TODO-08 / O-TODO-08. Interpretation: task/store profiles and partial correctness; this is D-11's required structured-field policy.
- **Locations:** [core.py](../../../../diary_agent_app/core.py), `parse_todo_details` at line 58; [models.py](../../../../diary_agent_app/models.py), `PendingTask`/display; [service.py](../../../../diary_agent_app/service.py), task scan at line 299; [llm.py](../../../../diary_agent_app/llm.py), rewrite output path.
- **Trigger:** read existing valid ISO due text alongside impossible due `31-02-2026` and unknown priority `urgent`; separately accept a controlled LLM proposal newly generating those invalid fields from input that contained no metadata.
- **Expected:** preserve raw legacy/unknown values, distinguish validated fields from unvalidated text in structured views, and constrain newly generated due/priority metadata to the specified values. Consent does not redefine a valid Gregorian date.
- **Actual:** tasks expose raw string fields in the same display representation, without validation status; invalid newly generated metadata is accepted and saved as ordinary due/priority fields. Open-task relative expansion does emit `DD-MM-YYYY`, but that only satisfies part of D-11.
- **Evidence:** P06-metadata-validation records task fields, a controlled actual model-response path, final file content and capture output; absence of a validity interpretation is also checked by source inspection. No particular future API field spelling is prescribed.
- **Repair obligation:** define validated/unvalidated observations and generation validation while preserving raw text. Do not “fix” this by rejecting verbatim notes or rewriting existing legacy values.

### F05 — Medium: a supported relative date creates a noncanonical year-one filename

- **Clauses / obligations:** DATA-01 / O-DATA-01, DATA-04 / O-DATA-04. Interpretation: calendar profile, `TotalOrder-basis-le`/`TotalOrder-transitive` on supported dates. This is a representation/domain-coverage defect, not a failure of date comparison.
- **Location:** [core.py](../../../../diary_agent_app/core.py), `parse_explicit_day_input` line 321; [service.py](../../../../diary_agent_app/service.py), date filename construction.
- **Trigger:** relative offset `(date(1,1,1) - date.today()).days`. On this baseline's local date it is `-739933`; the script computes it to retain the same target on later execution.
- **Expected:** `01_01_0001`, producing `01_01_0001.md`. Year 0001 is supported; an out-of-range rejection is not applicable to this input.
- **Actual:** this platform's `strftime('%d_%m_%Y')` returns `01_01_1`; actual append writes `01_01_1.md`. That file is then excluded by the strict dated-history filter.
- **Evidence:** P07-relative-year-one, direct parse and actual temporary append. Package/Python/platform context and runtime hashes are recorded; the year-padding behavior is platform-sensitive.
- **Repair obligation:** render the documented fixed-width format explicitly across supported dates. Do not silently narrow the date domain to modern years.

### F06 — Medium: completed history suppresses a new open TODO during proposal preparation

- **Clause / obligation:** TODO-04 / O-TODO-04. Interpretation: key-equivalence profile, `EquivalenceRelation-basis-class`/`equivalence-transitive` only for normalized open-task keys. Completed tasks are outside the specified existing-open-task carrier.
- **Locations:** [service.py](../../../../diary_agent_app/service.py), `prepare_rewrite_for_review` at line 162, `filter_new_entry_lines` at line 193 and `entry_line_text` at line 216.
- **Trigger:** target day contains `- [x] Buy milk`; LLM-associated proposed content is `- [ ] Buy milk`.
- **Expected:** the completed task alone is not an existing open duplicate; the new action remains in the proposed task set.
- **Actual:** proposal becomes `""`. The generic day-line filter erases checkbox state before comparing, so it treats completed/open actions identically. The separate `open_todo_keys` helper is correct, but is not the whole rewrite pipeline.
- **Evidence:** P08-completed-todo-history, one existing completed task and one candidate, no model nondeterminism needed after the supplied proposal.
- **Consequence:** this changes a proposal rather than silently deleting a final raw save; a user can reject the proposal. It still violates the required task comparison semantics and can suppress a legitimate repeated action.
- **Repair obligation:** preserve task state/type in day-line comparison and validate the entire proposal pipeline, not just the open-task deduplication helper. Retain consent requirements.

### F07 — Low: specification status prose contradicts the current span-based implementation

- **Clause / obligation:** DOC-02 / O-DOC-02. No catalog law is needed.
- **Location:** [Specification.md](../../../Specification.md), line 193, unqualified paragraph after VIEW-09.
- **Expected:** current/pending/historical status is distinguishable and agrees with evidence.
- **Actual:** it says the present implementation reconstructs whole files for section edits/deletion and does not conform to VIEW-08/09. The current `DiaryDocument` source-span mutation and byte-preservation tests contradict that statement, as does the specification's own section 10 status.
- **Evidence:** static text/code comparison, `test_section_mutation_preserves_all_outside_bytes` and P11-exact-save-and-spans.
- **Repair obligation:** reconcile the nonnormative implementation-status paragraph. The required VIEW-08/09 behavior is clear and need not be weakened or redesigned.

## Rejected hypothesis and partial support

The suspected inherited Alt+Enter consent bypass was **not confirmed**. Prompt_toolkit's actual Emacs binding filter includes insert-mode checks that are disabled when the buffer is read-only. P09-inherited-submit-filter finds one real inherited binding and zero enabled bindings in that state; it does not directly invoke an inactive handler and manufacture a failure. Existing controlled editor tests still establish successful accept/reject/error paths. Actual terminal scheduling remains separately unchecked.

P11-exact-save-and-spans independently confirms exact original body persistence and exact prefix/suffix preservation in one CRLF edit trace. Existing navigation tests cross month/year boundaries and preserve invalid-name files for history scans. These supported slices do not repair the separate persistence/fallback/domain defects.

## Unchecked obligations and interpretation boundaries

- **O-CAP-05:** suggestion-specific success/failure/overlap traces were not independently executed; shared background helper and callbacks were inspected.
- **O-TODO-06:** transport failure has the documented no-match path, but missing-client/malformed-response boundaries need interpretation before a blanket conformance claim.
- **O-VIEW-07:** nested actual terminal execution/render suspension/thread behavior was not exercised. Static flags and mocked handlers are insufficient for this entire obligation.
- Other supported rows retain narrower unchecked branches in their scope, including live model outputs, GUI picker/edit/delete events, physical write failures outside the injected traces and external races after snapshot validation.
- U03 (post-capture tagging among manually delimited multiple new sections and foreign metadata resource paths), U04 (similarity failure boundary) and the remaining limits are recorded explicitly in mapping.json. They do not block the confirmed findings or reopen the twelve resolved product decisions.

No requirement-level inconsistency was established here. These are concrete implementation defects, a documentation-status defect, and explicit unchecked interpretation/evidence boundaries. The mapping itself was checked against clause domains: it does not assume global unique headings, omit year 0001, equate failed writes with unchanged metadata, collapse cancellation into an empty selection, or transfer algebraic laws to heuristic similarity.

## Obligation-to-evidence table

Generated from the structured mapping and latest evidence. Probe IDs refer to complete expected/actual traces in evidence.json. Existing test names refer to `tests/test_diary_agent.py` or `tests/test_contracts.py`. Static-only support and narrower unexecuted branches remain stated rather than converted to unconditional passes.

<!-- BEGIN EVIDENCE-TABLE -->
| Obligation | Assessment | Executed probe / existing test / static scope |
| --- | --- | --- |
| O-DOC-01 | supported_within_scope | . Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-DOC-02 | violated | . Static documentation defect: the unqualified paragraph after VIEW-09 still says edits/deletion reconstruct whole files, contradicting current code and section 10. Prior reports are historical snapshots. |
| O-DATA-01 | violated | P07-relative-year-one, `test_append_entry_appends_to_existing_daily_file`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-DATA-02 | supported_within_scope | `test_append_entry_verbatim_uses_serial_suffix_for_same_minute`, `test_text_capture_consent_is_specific_to_displayed_proposal`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-DATA-03 | supported_within_scope | `test_parse_day_sections_returns_timestamp_sections_with_stable_ids`, `test_parse_day_sections_supports_serialized_timestamp_headings`, `test_parse_day_sections_ignores_text_before_first_timestamp_heading`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-DATA-04 | violated | P07-relative-year-one, `test_invalid_day_is_rejected`, `test_parse_explicit_day_input_accepts_relative_days`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-DATA-05 | supported_within_scope | `test_backfilled_rewrite_uses_target_day_context`, `test_append_entry_appends_to_existing_daily_file`. Static composition plus one explicit backfilled-context trace. Midnight rollover during a single workflow is not independently checked. |
| O-DATA-06 | supported_within_scope | `test_navigation_orders_calendar_dates_and_excludes_invalid_files`, `test_scan_pending_tasks_reads_unchecked_todos_from_all_markdown_files`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-DATA-07 | supported_within_scope | `test_parse_day_sections_returns_timestamp_sections_with_stable_ids`, `test_parse_day_sections_supports_serialized_timestamp_headings`, `test_parse_day_sections_ignores_text_before_first_timestamp_heading`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-DATA-08 | supported_within_scope | `test_duplicate_section_identity_blocks_mutations`, `test_section_for_id_returns_none_for_missing_section`. Domain guards tested; raw viewer diagnostics for duplicate IDs are inspected but terminal presentation is unchecked. Post-capture identity under submitted delimiters is U03. |
| O-DATA-09 | supported_within_scope | . Static derivation/no migration code; externally renamed HTFS metadata behavior has no dedicated executed trace. |
| O-CLI-01 | supported_within_scope | `test_build_parser_accepts_capture_day`, `test_build_parser_accepts_show_without_day`, `test_build_parser_accepts_tag_list_and_tree`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-CLI-02 | supported_within_scope | `test_cli_requires_bundled_htfs_before_loading_config`, `test_cli_htfs_initialization_failure_prevents_capture`. Static exception/dispatch boundary and preflight failure tests. Broad defensive exceptions can hide partial persistence (P04/P05); no exhaustive exit-code trace for every command. |
| O-CFG-01 | supported_within_scope | `test_parse_config_text_ignores_comments_and_invalid_lines`, `test_load_or_initialize_config_reads_required_entries`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-CFG-02 | supported_within_scope | `test_load_or_initialize_config_allows_missing_llm_model`, `test_load_config_ignores_legacy_htfs_path`, `test_bundled_htfs_path_ignores_environment_and_home`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-CFG-03 | supported_within_scope | `test_load_or_initialize_config_non_interactive_missing_required_values_raises`, `test_write_config_needs_only_diary_path_and_optional_model`. Non-TTY rejection and serialization tests; full actual terminal configuration prompting is unchecked. |
| O-CFG-04 | supported_within_scope | `test_unattended_capture_preserves_exact_input_and_duplicates`. Constructor/selection inspected; no-model deterministic tests use installed prompt_toolkit. Optional-package absence is a separate violation under CAP-08/VIEW-02. |
| O-DEP-01 | supported_within_scope | `test_bundled_htfs_path_ignores_environment_and_home`, `test_adapter_rejects_preloaded_external_htfs`, `test_bundled_htfs_resource_tagging_survives_reopening`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-DEP-02 | supported_within_scope | `test_cli_requires_bundled_htfs_before_loading_config`, `test_cli_htfs_initialization_failure_prevents_capture`, `test_search_does_not_hide_htfs_read_failures`, `test_show_does_not_mask_runtime_errors_as_ui_fallback`. Operational preflight and later read errors tested; post-write error reporting remains separately violated under PERSIST-03. Optional UI import failure prevents help without that package (F01). |
| O-LLM-01 | supported_within_scope | `test_editor_capture_saves_final_buffer_without_postprocessing`, `test_run_show_day_hides_llm_tag_suggestions_when_model_missing`, `test_run_tags_suggest_uses_available_htfs_tags`. All model call sites statically inventoried and selected callbacks tested. Real model behavior/service completion is unchecked. |
| O-CAP-01 | supported_within_scope | `test_editor_reviews_rewrite_before_draft_replacement`, `test_text_capture_consent_is_specific_to_displayed_proposal`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-CAP-02 | supported_within_scope | `test_editor_capture_saves_final_buffer_without_postprocessing`, `test_editor_reviews_rewrite_before_draft_replacement`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-CAP-03 | supported_within_scope | `test_backfilled_rewrite_uses_target_day_context`, `test_synthesize_entry_strips_headings_and_preserves_nested_bullets`. Prompt/cleanup contract inspected and finite outputs tested; no claim that a nondeterministic model preserves every fact. Completed/open comparison distinction is violated under TODO-04. |
| O-CAP-04 | supported_within_scope | P09-inherited-submit-filter, `test_editor_reviews_rewrite_before_draft_replacement`. Finite controlled work/success/error/accept/reject traces plus actual inherited-key filter. Live scheduling/rendering and arbitrary completion interleavings remain unchecked. |
| O-CAP-05 | unchecked | . Callback effects and shared lock lifecycle inspected; success/failure/overlap suggestion traces not independently executed. |
| O-CAP-06 | supported_within_scope | P11-exact-save-and-spans, `test_unattended_capture_preserves_exact_input_and_duplicates`, `test_editor_capture_saves_final_buffer_without_postprocessing`, `test_text_capture_consent_is_specific_to_displayed_proposal`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-CAP-13 | supported_within_scope | `test_text_capture_consent_is_specific_to_displayed_proposal`, `test_failed_text_rewrite_retains_original`, `test_editor_reviews_rewrite_before_draft_replacement`. Normal successful/RuntimeError callbacks and controlled cancellation/rejection. Arbitrary non-RuntimeError model/normalization failures and physical terminal cancellation remain unchecked. |
| O-CAP-07 | supported_within_scope | `test_run_capture_interactive_prompts_for_tags_and_applies_them`. Successful prompt/order/cancellation inspected and tested. Multiple timestamp delimiters in one capture leave post-tag target interpretation U03; failure reporting is separately violated under PERSIST-03. |
| O-CAP-08 | violated | P01-optional-ui-import. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-CAP-09 | supported_within_scope | `test_text_capture_consent_is_specific_to_displayed_proposal`. Text workflow contains no UI editor/tag call; empty accepted proposal tested. All-whitespace original text observed only by inspection. |
| O-CAP-10 | supported_within_scope | P11-exact-save-and-spans, `test_unattended_capture_preserves_exact_input_and_duplicates`, `test_editor_capture_saves_final_buffer_without_postprocessing`, `test_text_capture_consent_is_specific_to_displayed_proposal`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-CAP-11 | supported_within_scope | `test_unattended_capture_preserves_exact_input_and_duplicates`, `test_todo_proposal_removes_existing_and_new_duplicate_open_todos`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-CAP-12 | supported_within_scope | `test_text_capture_consent_is_specific_to_displayed_proposal`. Empty/rejected proposal tested and accepted similar-task report inspected. No end-to-end semantic-omission report trace was executed. |
| O-TODO-01 | supported_within_scope | `test_scan_pending_tasks_reads_unchecked_todos_from_all_markdown_files`, `test_todo_completion_changes_only_selected_state_and_rejects_stale_batch`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-TODO-02 | supported_within_scope | `test_only_proposed_open_todos_expand_dates`, `test_unattended_capture_preserves_exact_input_and_duplicates`. Ordinary date inputs tested; date.max overflow and metadata validity remain separate TODO-08 obligations. |
| O-TODO-03 | supported_within_scope | `test_invalid_todo_selection_rejects_entire_batch`, `test_todo_completion_changes_only_selected_state_and_rejects_stale_batch`. Numeric invalid/batch paths and duplicate completion tested; live interactive checklist selection is unchecked. |
| O-TODO-04 | violated | P08-completed-todo-history, `test_todo_proposal_ignores_optional_todo_metadata`, `test_todo_proposal_removes_existing_and_new_duplicate_open_todos`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-TODO-05 | supported_within_scope | `test_todo_proposal_can_omit_a_declined_similar_task`, `test_unattended_capture_preserves_exact_input_and_duplicates`. Helper omission and final-original selection tested separately; actual semantic model and interactive-editor cross-history similarity path are unchecked. |
| O-TODO-06 | unchecked | . Explicit catch inspected. Malformed response shape and a missing client have separate errors; failure-policy boundaries beyond transport are U04. |
| O-TODO-07 | supported_within_scope | . All production call sites inspected; existing capture tests and source routing have no checklist call. |
| O-TODO-08 | violated | P06-metadata-validation, `test_only_proposed_open_todos_expand_dates`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-TODO-09 | supported_within_scope | `test_unattended_todos_lists_without_prompting_or_mutating`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-TODO-10 | supported_within_scope | `test_todo_completion_changes_only_selected_state_and_rejects_stale_batch`. Stale second-file batch abort tested; full raw snapshot equality establishes fields at selected offsets. Later physical multi-file failures require PERSIST and are not claimed atomic. |
| O-VIEW-01 | supported_within_scope | `test_run_show_day_defaults_to_today_when_day_omitted`, `test_run_show_day_asks_to_show_latest_entry_when_today_missing`, `test_run_show_day_reports_missing_file`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-VIEW-02 | violated | P01-optional-ui-import, `test_viewer_is_read_only_and_boundary_navigation_is_noop`, `test_run_show_day_falls_back_to_stdout_when_ui_unavailable`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-VIEW-03 | supported_within_scope | `test_navigation_orders_calendar_dates_and_excludes_invalid_files`, `test_viewer_is_read_only_and_boundary_navigation_is_noop`. Order/boundaries and real navigation bindings tested. Picker query, selection, cancellation and actual terminal rendering inspected but not independently executed. |
| O-VIEW-04 | supported_within_scope | `test_todo_completion_changes_only_selected_state_and_rejects_stale_batch`, `test_section_mutation_preserves_all_outside_bytes`. Domain mutations tested; actual e-key nested editor/cursor and empty-edit interaction are unchecked. |
| O-VIEW-05 | supported_within_scope | `test_viewer_tag_cancel_clear_replace_are_distinct`, `test_delete_section_removes_markdown_section_and_htfs_resource`. Successful tag/delete operations tested. Actual d-dialog decline and physical nested-terminal execution are unchecked; deletion failure ordering is violated separately under PERSIST-01. |
| O-VIEW-06 | supported_within_scope | `test_viewer_tag_cancel_clear_replace_are_distinct`. Refresh code and exit bindings inspected; real exit events and delete-to-empty refresh not independently exercised. |
| O-VIEW-07 | unchecked | . Required calls/thread flags are present by static inspection; no live nested-terminal execution was performed. A mocked flag alone is insufficient evidence for the full obligation. |
| O-VIEW-08 | supported_within_scope | P11-exact-save-and-spans, `test_section_mutation_preserves_all_outside_bytes`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-VIEW-09 | supported_within_scope | `test_duplicate_section_identity_blocks_mutations`, `test_delete_section_returns_none_when_heading_is_missing`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-TAG-01 | supported_within_scope | `test_bundled_htfs_path_ignores_environment_and_home`, `test_adapter_rejects_preloaded_external_htfs`, `test_bundled_htfs_resource_tagging_survives_reopening`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-TAG-02 | supported_within_scope | `test_htfs_adapter_maps_section_to_resource_path_and_back`, `test_htfs_adapter_loads_section_from_resource_path`. Roundtrip and resolved section tests use in-boundary paths. Foreign-resource basename collisions and post-capture manual timestamp choice are U03. |
| O-TAG-03 | supported_within_scope | `test_tag_prompt_requires_explicit_creation_consent`, `test_comma_separated_tag_completer_completes_after_commas`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-TAG-04 | supported_within_scope | `test_run_tags_apply_creates_and_applies_tags`, `test_bundled_htfs_resource_tagging_survives_reopening`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-TAG-05 | supported_within_scope | `test_run_tags_apply_creates_and_applies_tags`, `test_run_tags_suggest_uses_available_htfs_tags`, `test_viewer_tag_cancel_clear_replace_are_distinct`. Successful outcomes and inventory filtering inspected/tested. Replacement/capture partial-failure handling is not supported by these tests; see P03/P04/P05. |
| O-TAG-06 | supported_within_scope | `test_run_tags_delete_recursively_deletes_descendants_first`, `test_run_tags_delete_blocks_when_tags_are_used`. Child order/usage guards tested; non-TTY confirmation and partial taxonomy-deletion failure inspected but not fault-injected. |
| O-TAG-07 | violated | P03-tag-replacement-failure, `test_viewer_tag_cancel_clear_replace_are_distinct`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-PERSIST-01 | violated | P02-delete-write-failure. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-PERSIST-02 | violated | P02-delete-write-failure, P03-tag-replacement-failure. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-PERSIST-03 | violated | P04-capture-tag-exception, P05-capture-tag-rejected. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-PERSIST-04 | violated | P10-recovery-interface. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-PERSIST-05 | violated | P02-delete-write-failure, P03-tag-replacement-failure. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-SEARCH-01 | supported_within_scope | `test_search_returns_best_matching_history_chunks`, `test_search_matches_sections_via_tags`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-SEARCH-02 | supported_within_scope | `test_run_search_supports_raw_tag_expressions_without_llm`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-SEARCH-03 | supported_within_scope | `test_run_search_translates_natural_language_tag_filters_when_llm_enabled`, `test_run_search_supports_raw_tag_expressions_without_llm`. Translation routing and scoped success tested; actual invalid-expression/backend parser failures are inspected only, with no new executed invalid-filter trace. |
| O-SEARCH-04 | supported_within_scope | `test_answer_query_includes_section_tags_in_prompt`. Prompt inspected/tested. No claim of factual model output or complete live-model compliance. |
| O-SEARCH-05 | supported_within_scope | `test_run_search_falls_back_to_basic_text_search_when_llm_is_unavailable`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-SEARCH-06 | supported_within_scope | . All search code paths inspected; empty-answer early return is explicit. Metadata initialization at operational startup is separately required, so no assertion of a write-free whole CLI invocation. |
| O-QUAL-01 | supported_within_scope | . Dependency/call-site inspection, not a network-isolation proof. |
| O-QUAL-02 | supported_within_scope | `test_editor_reviews_rewrite_before_draft_replacement`. Shared executor use and lock transitions tested with deterministic scheduled work. Actual worker-thread execution and all toolbar rendering states remain unchecked. |
| O-QUAL-03 | violated | P01-optional-ui-import, P04-capture-tag-exception, P05-capture-tag-rejected, `test_cli_htfs_initialization_failure_prevents_capture`, `test_search_does_not_hide_htfs_read_failures`. Static inspection and the referenced finite test cases; not a universal refinement proof. |
| O-QUAL-04 | supported_within_scope | `test_append_entry_verbatim_uses_serial_suffix_for_same_minute`. Storage/identity derivation and entrypoint compatibility inspected and ordinary historical formats tested. New relative-date rendering boundary failure is recorded under DATA-01/04. |
<!-- END EVIDENCE-TABLE -->

## Reproduce and plan repairs

```bash
PYTHONDONTWRITEBYTECODE=1 python scripts/conformance/check_implementation.py --render-docs
```

At this baseline, the command exits **1**, writes evidence and refreshes the generated tables because violations are present. It also reruns the 106-case ordinary suite, whose passing result is stored separately. It returns **2** on changed semantic fingerprints or unavailable/inconclusive evidence. Static-review conclusions are pinned and labeled; future implementation changes require mapping/finding review rather than automatic fingerprint replacement.

The audit tooling also passed compilation, `ruff check scripts/conformance --select F`, and `git diff --check`. No model proof/compiler/witness was used. Selected catalog records retain legacy citation gaps and editorial status as described in the mapping; source gaps are separate from the runtime findings.

Repair priority is F01 (required fallback), F02/F03 (persistence and truthful outcomes), then F04–F06 and F07. Each repair should update its mapping representation/evidence and add a focused behavior regression, while retaining its full required input/failure domain. This review records that work; it does not modify production behavior or mark these gaps complete.
