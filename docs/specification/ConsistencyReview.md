# Specification consistency review

Date: 14 November 2026. Original review: specification v0.1 to v0.2. Current specification: v1.0, all twelve decisions resolved by user.

## Findings and outcome

The review found two historical save/append contract conflicts under literal interpretations and a conflicting LLM allowlist across the source documents. Version 0.3 adopts the user's D-01 decision: no-LLM content is saved verbatim, and LLM-proposed modifications require explicit consent before use. It supersedes v0.2's unconditional normalized-save proposal. The current finite contract slices have an allowed outcome for every declared input. The editor reference model includes proposal acceptance/rejection and satisfies the selected safety conditions jointly.

**This is scoped evidence, not a proof that the entire specification is consistent.** All twelve decisions are resolved, with implementation gaps retained explicitly. D-10 establishes one behavior authority; D-11 selects DD-MM-YYYY TODO metadata rules; D-12 defines unattended/invalid/stale selection outcomes. Historical counterexamples motivate selected contracts rather than reimposing superseded requirements.

Artifacts:

- [Specification v1.0](../Specification.md): authoritative contracts, resolved decisions, implementation status and evidence links.
- [MathematicalModel.md](MathematicalModel.md): carriers, equalities, assumptions, catalog IDs, clause mapping, quantifiers, and exact check bounds.
- [check_consistency.py](../../scripts/specification/check_consistency.py): independent executable encodings and counterexamples.
- [evidence.json](evidence.json): results, witnesses, source/encoding/catalog hashes, and Python version.

## Method and source boundary

Applied [specification-consistency/SKILL.md](/linuxdev/github/mathematical-abstractions/ai/skills/specification-consistency/SKILL.md), including its checking/reporting and Boolean-example references. Used dependency-free authoritative Markdown retrieval, not ONTFS/SPARQL or a hosted service. Catalog structure validation returned **220 concepts, 2,132 nodes, no errors**. Structure validity does not establish semantic consistency.

The original v0.1 specification snapshot had SHA-256 `a8527460108ed68ccc111605197f49e96dd20d9643ec272014019c8907795faf`. Exact relevant excerpts are retained in the findings below; the complete original snapshot is not required to run the checks. Current source and encoding hashes are in the evidence file. Clause IDs and section names are the primary locators. Historical excerpts below describe pre-decision contracts; they are not current requirements when superseded by D-01.

Python **3.13.9**, standard-library finite enumeration and reachable-state exploration; no SAT/SMT solver, Lean compiler, or proof witness was used. The skill's four-valuation example was executed as `boolean_demonstration`: every pair of clauses is satisfiable, their full conjunction is not, and the repaired example covers both required inputs. This verifies the checking approach on the supplied example, not the Diary Agent translation by itself.

The original review modified no application code. The subsequent D-07 decision includes a real Git submodule, configuration/import/startup changes and focused integration tests; earlier decisions' implementation gaps remain tracked separately. No catalog records or runtime ontology graphs were modified. Mathematical definitions are instantiated explicitly; inheritance links do not confer laws. Known catalog source gaps and editorial/partial-model status are preserved in the model document.

## SC-01 — literal save conflicts with mandatory date normalization

**Classification:** historical conflict under exact-text semantics. **D-01 is resolved by user decision; runtime conformance is pending.**

Sources:

- [AGENTS.md](../../AGENTS.md), “Key Product Rules,” line 60: “whatever is in the buffer when `Ctrl+D` is pressed is written verbatim”.
- [Requirements.md](../Requirements.md), “Capture Workflow,” line 64: “The exact text present in the editor when `Ctrl+D` is pressed is written to the diary verbatim.”
- Requirements, “TODO Management,” line 95: “Relative date words in TODO text or due metadata are expanded to exact diary dates before the markdown is written.”
- Specification CAP-06 and TODO-02 expose these two policies; CAP-06 previously noted the unresolved wording conflict.

Required input: submit `- [ ] Call mom tomorrow` for `25_03_2026`. Literal equality requires the new body to contain `tomorrow`; normalization requires `26_03_2026`. The Boolean observation `changed` must be both false and true. The background is inhabited: a valid date and finite, nonempty checkbox text. Comparison concerns the new section body, not its generated heading or the rest of the file.

Catalog mapping: HoareTriple successful postconditions plus Function identity/composition; PropositionalLogic evaluation and finite truth-table checking. `save_contracts()` verifies no output for the conflicting input and a model after removing either clause. This is inclusion-minimal with the scenario fixed.

**User-selected repair, model rechecked:** CAP-06/13 prohibit hidden normalization, trimming and duplicate removal. A changed LLM proposal requires display and explicit consent before use; model configuration or a rewrite request alone is insufficient. Without an accepted proposal, preserve original text verbatim, including unattended capture. The checker covers all eight combinations of LLM use, changed proposal and consent, plus nine concrete verbatim-preservation cases. Project guidance is updated for this decision. Existing save helpers, automatic filters and immediate rewrite replacement still need implementation changes and regression tests.

## SC-02 — nonempty raw input need not produce an appended section

**Classification:** demonstrated conflict under an unconditional reading of the original DATA-02; a scope ambiguity under the contextual reading of “capture”.

Original v0.1 DATA-02: “Append each nonempty capture under `## HH:MM`, with blank-line separation.” CAP-12: “If nothing remains, report redundancy without adding an empty section.”

Required input: a nonempty processed capture whose every line is redundant. If “nonempty capture” denotes raw input, DATA-02 requires `appended=true`, while CAP-12 requires false. This is not an empty-input exclusion or a filesystem failure. The fixed Boolean output domain is sufficient for the conflict; every actual append has one of these observations.

Catalog mapping: PropositionalLogic full conjunction, HoareTriple/input-coverage distinction. `save_contracts()` verifies the fixed-scenario two-clause conflict and both single-clause removals.

**Current repair rechecked:** DATA-02 applies to accepted content. Under D-01, an accepted complete LLM proposal may omit duplicates; verbatim mode retains the original content, including duplicates. All eight mode/nonempty/redundant abstract inputs have one allowed append decision under one shared policy. This changes the earlier automatic-filtering target; no application change is claimed.

## SC-03 — the three-task LLM allowlist excludes specified tagging operations

**Classification:** historical cross-document conflict under an exhaustive reading of “only”; otherwise an incomplete allowlist. **D-03 is resolved: the user retained all five tasks.**

[AGENTS.md](../../AGENTS.md), “LLM Guidance,” lines 111–114: “Use Ollama only for the currently implemented tasks” followed by capture rewrite, TODO similarity decision, and search answer synthesis. AGENTS also lists tag suggestion at line 97. [Requirements.md](../Requirements.md) specifies model-based tag-filter translation at line 141 and tag suggestion at line 201.

Required scenario: a configured, available model and an explicit request for one of the two tagging operations. The old allowlist forbids the model call; the requested LLM operation needs it. `llm_allowlist()` checks all five requested task kinds and both configuration modes together under the same allowlist. The old set leaves exactly two inputs without outputs.

Catalog mapping: PropositionalLogic conjunction and coverage. Availability and explicit invocation are fixed background, not claims that configuration ensures successful model output.

**User-selected repair rechecked:** LLM-01, AGENTS and the other project documents now explicitly list all five existing operations. All ten abstract inputs remain covered by the same allowlist model. No runtime change is needed to retain these operations. Model errors, automatic tag application, or new model tasks are not licensed by this allowlist; D-01 consent still governs content changes.

## SC-04 — cancelled and accepted-empty selections need distinct observations

**Classification:** D-09 resolved by user decision, runtime implementation pending. The collapsed representation cannot satisfy the selected cancellation-preserves-tags and accepted-empty-clears contract for nonempty prior tags.

Sources: TAG-05 describes replacement, and the user-approved TAG-07 distinguishes cancellation, accepted-empty and accepted-nonempty selections. The original baseline did not explicitly promise cancellation preservation; this review does not retroactively attribute the chosen policy to it. Current UI/caller code still conflates cancellation and accepted-empty as `[]`.

Fix prior tags `{Project}`. Desired cancellation leaves `{Project}`; accepting an empty selection yields `{}`. If the handler receives the same `[]` in both cases with the same prior state, no deterministic function can return both desired outputs.

Catalog mapping: SumType constructors and case-injection laws. The selected result type `Cancelled | Accepted(tags)` preserves that distinction. `cancellation_model()` checks all 20 prior-state/result inputs for a two-tag inventory, separately counting four cancellations, four accepted-empty and twelve accepted-nonempty cases, plus the collapsed-output witness.

**User-selected repair rechecked:** distinct constructors cover all declared cases. Cancellation leaves existing tags unchanged without adapter mutation; accepted-empty clears associations only, and accepted-nonempty replaces them. D-08 governs persistence failures. Current UI/caller return values still need the focused regression fix; this finite check does not test terminal dispatch or backend recovery.

## SC-05 — total ordering alone does not establish chronological ordering

**Classification:** historical ordering ambiguity and concrete failure of lexical filenames to match calendar order. **D-04 is resolved by user decision; implementation is pending.** This is not an inconsistency of total-order mathematics.

Historical sources: VIEW-03/D-04 and [Requirements.md](../Requirements.md), “Show Viewer Navigation,” previously combined “filename/date order” with “newest first.” These are superseded by the D-04 decision.

Witness: `31_03_2026.md` precedes `01_04_2026.md` chronologically but follows it lexicographically. Both comparisons can be valid total orders; the issue is which one the product requires. `order_and_similarity()` retains the four-date witness and checks the calendar relation's pair/triple laws on that finite carrier.

Catalog mapping: TotalOrder comparison and its four selected axioms. The witness refutes equating filename and calendar order, not the axioms.

**User-selected repair rechecked:** navigate using parsed calendar dates and list the picker newest first. Include only valid `dd_mm_yyyy.md` calendar-date filenames in day navigation/latest selection; retain other Markdown files in TODO scans/text search without renaming them. The reference model checks all 16 subsets of the four dates with invalid/non-date filenames, plus every neighbor and boundary. The application ordering fix remains pending.

## SC-06 — heuristic similarity is not an equivalence relation

**Classification:** invalid potential mathematical mapping avoided; no original requirement asserts transitivity.

Sources: CAP-11 distinguishes deterministic lexical heuristics from semantic equivalence; TODO-04 compares exact normalized keys. Under the selected overlap heuristic, take five-token sets:

```text
A = {a,b,c,d,e}
B = {a,b,c,d,f}
C = {a,b,c,f,g}
```

At 80% overlap, A matches B, B matches C, but A does not match C. Greedy processing of A,B,C accepts A and C; processing B,A,C accepts B alone. This is a reference-model counterexample, not a complete analysis of every text/token/substring rule in the implementation.

Catalog mapping: EquivalenceRelation transitivity is appropriate for normalized-key equality, not this heuristic. `order_and_similarity()` checks the witness.

**Draft clarification:** CAP-11's accompanying paragraph now forbids treating near-matching as equivalence or assuming order-independent filtering. No heuristic is changed. A requirement for order independence would need a separate algorithm/product decision.

## SC-07 — section identity is conditional on heading uniqueness

**Classification:** historical missing uniqueness contract and conditional collision. **D-05 is resolved by user decision; implementation is pending.** This was not an unconditional specification contradiction.

Sources: DATA-02/03 and D-05. Two same-file occurrences with heading `14:30` have the same derived ID but may have different bodies. If arbitrary Markdown edits are allowed, heading uniqueness cannot simply be assumed. Automatic serial allocation demonstrates a way to keep generated headings distinct, not a validator for external files.

Catalog mapping: CandidateKey motivates a uniqueness obligation but neither minimality nor an FD theorem is used. `key_collision()` retains a two-occurrence collision and a distinct serialized-heading example.

**User-selected repair rechecked:** DATA-07–09 retain file/timestamp IDs and timestamp delimiters. Duplicate IDs allow file viewing but block ambiguous section edits, deletion and tagging until explicit correction. No silent heading repair or tag migration is allowed; manual renames change identity. The checker covers 40 heading sequences, three queried IDs and six operation classes (720 decisions), plus rename examples. These are finite lookup-policy checks, not full Markdown parsing, implementation guards or cross-store migration verification.

## SC-08 — section mutations must preserve unrelated file bytes

**Classification:** D-06 resolved by user decision; implementation conformance pending. Whole-file reconstruction losing preamble/formatting is a known implementation gap, not a contradiction in this selected contract.

Sources: VIEW-08/09 and D-06. Editing replaces only a selected body; deletion removes only the selected section. Bytes outside the exact target span must remain identical. Missing/ambiguous targets or unsafe boundaries cause no write. This complements D-01's final-body preservation and D-05's identity guards.

Catalog mapping: HoareTriple successful postconditions with explicit failure outcomes. `targeted_mutations()` checks all 486 combinations of supplied byte spans, replacements, operation kind and match count. Examples include preamble text, Unicode, trailing spaces, mixed line endings and missing final newlines. The reference model returns explicit missing/ambiguous errors with unchanged content, or a unique-span result preserving prefix/suffix bytes.

This constructs scoped preservation evidence. It does not discover spans from Markdown, test current application mutations, prove successful disk writes, or establish crash/concurrency/cross-store recovery. Those remain separate implementation obligations.

## SC-09 — mandatory bundled HTFS

**Classification:** D-07 resolved and implemented. The user rejected a tag-optional mode and required HTFS as a Git submodule used in every operational mode.

DEP-01/02 and CFG-02 require the bundled Python API and mandatory startup preflight; external command/checkout discovery and config/environment selection are removed. Missing source, missing Python dependencies and boundary errors are still required scenarios; they return explicit startup errors instead of being excluded to make a precondition true.

Catalog mapping: PropositionalLogic conjunction/coverage and HoareTriple operation outcomes. `required_htfs()` covers 80 declared inputs, including both model modes and all availability combinations. Ten inputs permit dispatch; seventy require failure without diary-content writes. This is a reference contract, not a guarantee against subsequent backend failure or an atomicity proof.

The repository now registers `https://github.com/brteja1/HTFS.git` at `deps/HTFS`, pinned initially to `fa82438b63e6b9daa146cd05812b062b0beffd7c`. Runtime integration tests use that package for persistent tagging/querying and exercise missing-backend, initialization-failure, and non-suppressed HTFS-error paths. All 91 application tests passed. A temporary-boundary CLI smoke check also passed for no-LLM capture, hierarchical tag application and tag-filter retrieval with SQLite/RDF persistence. Help remains available without startup initialization. See [HTFS.md](../HTFS.md) for setup and verification. Later partial-persistence handling remains D-08.

## SC-10 — partial completion and metadata-only retry

**Classification:** D-08 resolved by user decision; runtime implementation pending. No atomicity or rollback guarantee is introduced.

PERSIST-01–05 retain Markdown authority for content and record intended/prior tag associations separately. Recovery intent precedes mutation. Confirmed content writes survive a later tagging failure with an explicit partial result; uncertain content writes require inspection and must not be reported as saved. Metadata reconciliation is verified before success, including backend close/flush and readback. Completed receipts make repeated requests harmless.

Catalog mapping: TransitionSystem operation phases, HoareTriple outcome predicates and Function composition for replay of metadata assignment. `recovery_contract()` checks all 48 declared operation/outcome cases and 288 retry cases, including unavailable intent, uncertain content, successful repair, incompatible targets and completed receipts. Metadata retry performs no content mutation and never allocates another capture. This is scoped constructive reference-model evidence, not an implementation fault-injection test, durable-journal proof or general concurrency/crash proof.

Current code still deletes HTFS state before writing a section deletion and can swallow resource cleanup errors; tag replacement clears previous state without recovery records. Those paths need implementation changes and meaningful fault-injection regressions. D-07 mandatory startup remains in force; D-08 handles failures after that startup succeeds.

## D-10 — one documentation authority

**Classification:** resolved and applied in documentation; no application behavior changed. DOC-01/02 make Specification.md the authority, Requirements.md its ID-based feature index, Design.md the architecture description, AGENTS.md operational guidance, README.md setup/use guidance and Future.md nonbinding proposals.

Supporting documents no longer claim general conformance or compete over save behavior, task inventory, model configuration or backend discovery. Design distinguishes current code from pending targets, and the historical automatic-tagging recommendation is explicitly unapproved. Requirement-reference and local-link checks are documentation evidence, not proofs of semantic consistency or implementation conformance. Subsequent D-11/D-12 decisions are recorded below; implementation gaps remain visible.

## SC-11 — TODO metadata and consented date proposals

**Classification:** D-11 resolved by user decision; implementation pending. The user selected DD-MM-YYYY for generated TODO dates, preserving the existing underscore filename/day-input contract. Existing valid hyphen/ISO/underscore due fields remain readable without rewriting; unknown priorities and invalid due values remain unvalidated text.

TODO-02/08 permit relative expansion only for open TODOs inside an accepted LLM content proposal, based on the diary day. Completed dates remain unchanged. New priorities use low/medium/high; neither validation nor parsing authorizes hidden mutation or guessing.

Catalog mapping: Function parsing, SumType validated/unvalidated outcomes and HoareTriple preservation/guard predicates. `todo_metadata_contract()` checks twelve explicit due fixtures, four generated-date round trips, six priority fixtures and 324 state/LLM/consent/date-token combinations. It includes leap-day and maximum-year overflow, unchanged completed tasks and nonconsented raw text. These are finite reference examples, not proof of arbitrary model output, full language interpretation or application conformance. Current code's automatic underscore-date expansion, including completed tasks, still requires replacement.

## SC-12 — unattended and stale TODO selection

**Classification:** D-12 resolved by user decision; implementation pending. TODO-03/09/10 select noninteractive listing only, whole-selection errors for invalid/out-of-range input, and affected-file/raw-task snapshot validation before writes. A stale selection requires refresh/reselection, not guessing a task from a current line number.

Catalog mapping: Function/SumType operation outcomes and HoareTriple mutation guards. `todo_selection_contract()` checks 154 combinations of TTY mode, selection and source-state fixtures. It covers empty and repeated selections, malformed and mixed-invalid input, missing files, moved/completed/edited tasks, metadata changes, and changes to unselected files. Rejected actions preserve the live source state; successful actions change only the selected checkbox state and deduplicate repeated indices.

This is a finite reference policy, not implementation conformance or a concurrency proof. Actual TTY routing, empty-history handling, snapshot capture/verification and real write failures still need application tests. Snapshot checks do not establish race isolation after validation or atomic multi-file updates; D-07 startup and D-08 outcome handling remain applicable.

## Executed evidence and remaining coverage

Command:

```bash
python3 scripts/specification/check_consistency.py --output docs/specification/evidence.json
```

Result: **PASS — expected conflicts reproduced and selected repaired finite models covered.** A passing checker means it reproduced the stated diagnoses and satisfied its scoped repair obligations; it does not mean the old conflicts disappeared from every source document.

Editor safety: four inhabited initial states, **64 reachable abstract states and 768 checked transitions** across twelve event classes, including explicit proposal acceptance and rejection. All selected guards, consent requirements, rejection-preservation and failure-preservation conditions hold together in the reference model. Every state/event pair has a modeled successor. A busy waiting self-loop is retained, so no eventual-completion claim is made. This is full reachable exploration of the declared finite machine, not a depth-bounded search and not an abstraction proof for real terminal execution.

No full-spec conjunction was encoded. The remaining clauses cover open-ended text, storage, backend semantics, and interactions not captured by these finite observations. In particular:

- D-02 is resolved: the user chose pending-TODO review only through `todos`. TODO-07 and project guidance now prohibit the obsolete post-capture review prompt. Current capture routing agrees; no runtime change was needed. This was a product choice, not a contradiction inferred merely from the existence of a separate command. Command routing is outside the finite editor model.
- D-06 preservation and missing/ambiguous-target outcomes are decided and checked in a supplied-span reference model. D-07's mandatory bundled dependency and startup errors are integrated. D-08's partial-completion/retry policy is decided and checked in a finite reference model, with implementation pending; physical durability and arbitrary crash/concurrency behavior remain unverified.
- D-10's document roles are reconciled. D-11 metadata and D-12 selection policies are decided with finite reference evidence and implementation pending. No recorded product decision remains open; unmodeled semantics and implementation obligations remain explicit.
- Date-range errors, exact normalization and full Markdown identity/round-trip behavior are specified or identified as obligations but not exhaustively verified here.
- The LLM answer-only-from-excerpts rule is a prompt obligation; no assertion of universal factual correctness is introduced.

Use the authoritative specification and its explicit outcome/observation definitions for implementation. Complete recorded implementation gaps before claiming full conformance. Resolving the decision list, aligning documentation and passing scoped finite checks do not establish a global consistency proof or prove arbitrary text/backend/concurrency behavior.
