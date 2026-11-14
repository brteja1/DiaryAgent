# Mathematical interpretation of the Diary Agent specification

Status: companion to authoritative specification v1.0; all twelve decisions recorded 14 November 2026.

This document applies the external [specification-consistency skill](/linuxdev/github/mathematical-abstractions/ai/skills/specification-consistency/SKILL.md). It separates mathematical definitions from product requirements, makes the selected interpretation explicit, and defines the finite checks in [check_consistency.py](../../scripts/specification/check_consistency.py). Findings and execution evidence are in [ConsistencyReview.md](ConsistencyReview.md) and [evidence.json](evidence.json).

The mathematical catalog supplies vocabulary and applicable laws. Catalog membership, successful structure validation, or a model declaration does not prove the product specification consistent. The checker constructs independent reference models; it does not import or test the application.

D-10 establishes document roles, not a new mathematical theorem: the specification is the behavior authority, its requirements index references stable IDs, and design/guidance/roadmap documents have supporting roles. Link/ID/status validation checks this documentation structure separately from finite semantic models. Historical conflicts remain historical evidence; they do not impose superseded clauses on current models.

## 1. Interpretation and assumptions

The following are modeling assumptions, not additional product promises:

- One user and one active operation; no concurrent external file edits during an operation. D-08 specifies recovery outcomes and safe metadata retry; physical durability, races and arbitrary crash interleavings are not modeled. Divergence observed before retry is an explicit conflict scenario.
- Text is a finite sequence of Unicode characters. Equality of text is exact character equality, unless an explicitly named observation/normalization is used. Encoding success and filesystem availability are environment conditions for successful writes, not guarantees that storage cannot fail.
- A diary date is a valid Gregorian date supported by the runtime. Relative input is a signed integer string. Parsing returns either a supported date or an explicit invalid/out-of-range outcome; an unbounded integer does not imply an unbounded calendar.
- A stored file is an ordered sequence of lines. A parsed section is a file/heading/body occurrence; heading uniqueness is not assumed for arbitrary manually edited files.
- Tags are finite sets of backend tag identities. Path strings and leaf names are different observations; no claim that leaf projection is injective is introduced.
- LLM availability and completion are environment behaviors. A configured model does not imply that the service responds or its text is factually correct.
- Under D-07, HTFS is a mandatory pinned dependency. Missing source/dependencies or an unavailable diary boundary remain required failure scenarios with explicit errors, not excluded inputs. Their permitted outcomes do not include dispatching a tag-free workflow or writing diary content.
- A successful operation, explicit error, cancellation, and no-change result are distinct observations. A successful content write followed by tag failure is not an unchanged file.

Required scenarios include empty and nonempty drafts, drafts containing relative TODO dates, wholly redundant processed captures, configured/unconfigured model modes, no search matches, and navigation boundaries. Do not exclude these inputs to make a contract satisfiable.

D-02 separates two command workflows: capture has no transition to the pending-TODO checklist or a prompt to open it; the explicit `todos` command enters that review workflow. Viewer checkbox toggles and consent to content proposals are different actions. This command-routing decision is documented directly; the finite editor model does not model the checklist or claim to verify application routing.

## 2. Catalog mapping

All IDs use the `urn:csabs:` prefix. Records were retrieved from authoritative Markdown through `scripts/catalog.py` and `scripts/agent_query.py`; ONTFS/SPARQL and Lean were not used. Concept files are hashed in the execution evidence. Operations and claims are explicit selections; no laws are inherited through `specializationOf` or `requiresConcept`.

| Clause / local obligation | Catalog concept and selected IDs | Instantiation and limits |
| --- | --- | --- |
| SC-01–03: conjunction and input coverage | `concept/PropositionalLogic`; `operation/PropositionalLogic-basis-evaluate`; `operation/PropositionalLogic-semantic-queries`; `axiom/PropositionalLogic-truth-semantics`; `axiom/PropositionalLogic-entailment`; `theorem/PropositionalLogic-finite-truth-table` | Boolean atoms describe an input scenario and an allowed output. Evaluate the full clause conjunction; existential satisfiability is separate from coverage of each required input. |
| CAP-06/13, TODO-02: save relation | `concept/HoareTriple`; `operation/HoareTriple-basis-holds`; `concept/Function`; `operation/function-identity`; `operation/function-composition` | Persistence is identity on the final user-controlled body. LLM proposal generation and explicit acceptance are separate from persistence. A partial-correctness implication does not promise an outcome or termination. |
| CAP-01/02/04/05, QUAL-02 | `concept/TransitionSystem`; `operation/TransitionSystem-post` | States are editor phases with draft/tag/save observations; reachable closure is computed from inhabited initial states. A waiting self-loop is permitted; no fairness/liveness claim follows. |
| TAG-07 / D-09: cancellation versus empty accepted selection | `concept/SumType`; `operation/SumType-injectLeft`; `operation/SumType-injectRight`; `operation/sum-case`; `axiom/case-inl`; `axiom/case-inr` | `Cancelled + Accepted(TagSet)` has distinct constructor tags. Case analysis preserves old tags on cancellation and uses the payload on acceptance. This is the user-approved target; the runtime now represents cancellation as `None` and acceptance as a list, including `[]`; see Testing.md for application coverage. |
| VIEW-03 / D-04 | `concept/TotalOrder`; `operation/TotalOrder-basis-le`; `axiom/TotalOrder-reflexive`; `axiom/TotalOrder-transitive`; `axiom/TotalOrder-antisymmetric`; `axiom/TotalOrder-comparable` | User selected parsed calendar dates as the ordering carrier. Valid dated-file filtering precedes navigation; previous/next are partial on boundaries, represented by no target. Filename lexical order is a distinct rejected interpretation. |
| CAP-11 / TODO-04 | `concept/EquivalenceRelation`; `operation/EquivalenceRelation-basis-class`; `axiom/equivalence-reflexive`; `axiom/equivalence-symmetric`; `axiom/equivalence-transitive` | Equality of normalized keys induces equivalence classes. Near-match heuristics need not be transitive and must not be used as an equivalence-class or quotient assumption. |
| DATA-02/03/07–09 / D-05 | `concept/CandidateKey` | A file/heading pair is usable only with exactly one matching occurrence. Zero matches means missing, multiple matches ambiguous. Whole-file viewing is independent of uniqueness. No candidate-key minimality or FD theorem is asserted. |
| VIEW-08/09 / D-06 | `concept/HoareTriple`; `operation/HoareTriple-basis-holds` | With file bytes `prefix + target + suffix` and a uniquely located target, successful edit/delete preserves the exact prefix and suffix. Missing/ambiguous targets permit an explicit error and unchanged bytes. This is an operation postcondition, not an atomicity or parser-correctness theorem. |
| DEP-01/02 / D-07 | `concept/PropositionalLogic`; `operation/PropositionalLogic-basis-evaluate`; `concept/HoareTriple`; `operation/HoareTriple-basis-holds` | For every operational command and model mode, source/dependency/boundary availability determines ready-to-dispatch versus explicit failure. Failure forbids diary-content writes; initialization may create HTFS metadata. Actual runtime startup is covered separately by integration tests. |
| PERSIST-01–05 / D-08 | `concept/TransitionSystem`; `operation/TransitionSystem-post`; `concept/HoareTriple`; `operation/HoareTriple-basis-holds`; `concept/Function`; `operation/function-composition` | Recovery intent precedes mutation; observed content/metadata outcomes determine truthful status. A retry leaves the content-write count unchanged, reconciles recorded desired tags only against compatible state, and completed receipts make replay a no-op. This is a finite reference policy, not a distributed-transaction theorem or real journal implementation. |
| TODO-02/08 / D-11 | `concept/Function`; `concept/SumType`; `operation/sum-case`; `concept/HoareTriple`; `operation/HoareTriple-basis-holds` | Metadata parsing returns validated values or unvalidated original text. Proposal selection is gated by open-task state, actual LLM use and consent. Generated TODO dates use DD-MM-YYYY; file/day-input syntax is a distinct domain. Validation must not rewrite stored text. |
| TODO-03/09/10 / D-12 | `concept/Function`; `concept/SumType`; `concept/HoareTriple`; `operation/HoareTriple-basis-holds` | Selection produces listed/no-change/invalid/stale/updated outcomes. Updates require a TTY, entirely valid indices and matching affected-file/task snapshots. Invalid or stale input permits no task mutation; duplicate valid indices identify one task. This does not establish real TTY behavior, race isolation or multi-file write atomicity. |

The finite-truth-table theorem's direct premises were retrieved: `axiom/PropositionalFormula-induction`, `axiom/PropositionalFormula-substitution`, `axiom/PropositionalLogic-truth-semantics`, and `axiom/PropositionalLogic-entailment`. We use only finite Boolean support and classical implication `not p or q`. No formula text is evaluated as code. The complete four-valuation demonstration from the skill is reproduced as `boolean_demonstration`.

Catalog provenance gaps remain visible: TransitionSystem, Function, EquivalenceRelation and the selected TotalOrder axioms carry `legacy-source-missing`. These are explicit modeling definitions here, not independently sourced or compiled theorem witnesses. Sum case axioms and the propositional claims are editorial records; this work claims no Lean compilation or formal proof reuse.

## 3. Operation semantics

For operation relation `R(i,o)`, required domain `D`, and permitted terminating outcomes `O`:

```text
joint satisfiability: there is one interpretation satisfying all selected clauses
input coverage:      for every i in D, there is o in O with R(i,o)
partial correctness: P(s) and C(s,t) implies Q(t)
```

Check that `D` and initial states are inhabited. An empty transition relation satisfies partial correctness vacuously and does not demonstrate input coverage. Existence of an allowed result in a mathematical relation also does not prove that a real operation terminates, especially when it awaits user input or an external service.

### Save and append

Let `d` be original user-controlled text and `p` a complete LLM-associated content proposal, including any cleanup. Under the user's D-01 decision, `used` means an LLM content transformation was actually used and `consent` means explicit acceptance of this displayed proposal:

```text
selected_body = p if used and consent else d
body_saved = final_user_edits(selected_body)
file_after = serialize(file_before, fresh_heading, body_saved)
```

Persistence is identity on `body_saved`: no trimming, normalization or filtering after user submission. In the finite relation there are no later user edits, so the selected body is saved exactly. User edits themselves are authorized input, not automatic changes. Headings and separation are outside the body observation. Configuration, tag suggestions and search are not `used`. Calling the model requests a proposal; it does not consent to unseen content. Rejection or absence of a consent channel preserves the original. Whole-capture cancellation writes nothing.

Date expansion and duplicate removal may appear only within a complete LLM-associated proposal before consent. A nonempty raw draft can produce no append if its accepted complete proposal is empty. Without accepted changes, nonempty original text, including duplicates, is preserved. DATA-02 applies to accepted content; CAP-12 does not authorize dropping unconsented original text. Write errors are explicit outcomes, outside the successful-save relation used by the finite Boolean check. The earlier unconditional normalization profile is historical and has been superseded.

### Editor state machine

`Editor = (configured, phase, draft, suggested, saved, proposal, accepted)` where:

- `configured`, `suggested`, `saved`, `accepted` are Boolean; `accepted` records consent to an applied LLM proposal.
- `phase` is `editing`, `rewriting`, `reviewing`, `suggesting`, or `closed`.
- `draft` is the abstract observation `empty`, `raw`, or `rewritten`. `proposal` is absent or a pending `empty`/`rewritten` candidate. Precise text transformation is a separate obligation.
- Initial states have phase `editing`, draft `empty` or `raw`, no pending proposal, no acceptance, no suggestions and no save, with either model configuration value.

While busy or reviewing a pending proposal, edit, submit, and new-request events stutter. Rewrite success enters `reviewing` with a candidate and preserves the original draft; explicit acceptance applies the candidate, rejection discards it. Rewrite failure returns to editing with the original draft. Suggestion completion preserves the draft. With no model, request events stutter. Submission from `editing` closes the editor and marks a save only for nonempty content. Events in `closed` stutter.

The twelve event classes are listed in `EVENTS` in the checker, including acceptance and rejection. Completion and consent events are explicit environment inputs; the model does not assume they eventually arrive. Safety is checked on every edge of the complete reachable finite model, with every event enabled as a modeled response. This is a constructive example satisfying the selected safety constraints together. It does not verify real prompt_toolkit scheduling, background threads, precise text, errors in storage, or progress.

### Cancellation

User-approved D-09 dialog output is `Cancelled | Accepted(tags)`. For prior tags `p`:

```text
apply(p, Cancelled)   = p
apply(p, Accepted(t)) = t
```

If both `Cancelled` and `Accepted(empty)` are encoded as `[]`, a deterministic downstream handler cannot distinguish them for the same `p`. For nonempty `p`, requiring both different outputs under that collapsed representation is impossible. D-09 explicitly chooses the distinguishable representation; this policy comes from the user, not type theory alone. Cancellation starts no metadata mutation; accepted changes follow D-08. The finite selection model describes intended final tags under successful mutation, not backend failure/recovery or terminal key dispatch.

### Targeted file mutations

For D-06, the carrier is finite byte strings, compared by byte equality. A supplied unique span gives `before = prefix + target + suffix`. Successful replacement returns `prefix + replacement + suffix`; deletion uses an empty replacement. For an edit, the retained heading belongs to `prefix`; for deletion the heading belongs to `target`. Storage framing owned by the section must be included in the chosen span. Determining correct spans from Markdown is a separate unchecked obligation. The model supplies them directly and checks preservation, including UTF-8, LF/CRLF, blank lines and trailing whitespace examples. Missing/ambiguous lookup returns an explicit failure and the original bytes. No actual files are written.

### Partial completion and metadata retry

D-08 models four operation kinds: capture, edit, deletion and tag replacement. Before mutation, recovery intent is either recorded or unavailable; the latter permits failure without any content attempt. For content operations, the observed write result is `not_written`, `committed`, or `unknown`. An unknown result permits an uncertain status, never a claim of confirmed persistence. Tag-only operations do not write Markdown.

Only verified metadata reconciliation can complete the operation. A confirmed content write with unverified metadata remains partial; it is never undone or described as no change. A tag-only operation whose metadata outcome cannot be verified is uncertain, since no change has been confirmed. Pending recovery retains prior/intended associations and fingerprints; no inference of tag associations from text is permitted. Post-save capture tagging is its own metadata operation, so its failure does not undo the successful capture.

On explicit metadata retry, the observed target is `before`, `desired`, or `diverged`; this abstracts content for combined operations and tag associations for tag-only operations. Divergence causes conflict; content not confirmed at its desired state causes inspection/no mutation. With compatible state and a ready backend, reconcile to the recorded intended set, verify, and mark a completion receipt. A completed receipt causes no further mutation, even if the user subsequently changed data. Retry never allocates another content operation or increments the content-write count.

The finite model checks these observations and replay outcomes, not physical journal persistence, JSON/schema choices, close/flush correctness, Markdown write mechanics or races between checking and writing. Real retry must honor D-05 uniqueness guards and D-07 mandatory startup; their complete implementations are not composed into this reference model.

## 4. Finite obligations and exact bounds

D-11 interprets recognized due-date fields as valid runtime Gregorian dates in three exact-width forms: DD-MM-YYYY, legacy YYYY-MM-DD and legacy dd_mm_yyyy. Parsing retains the raw field. New generated values use zero-padded DD-MM-YYYY; new priorities are low/medium/high. Invalid dates and other priorities remain unvalidated original text. Relative expansion is conditional on an open checkbox, LLM transformation and acceptance, using the target diary date. Completed x/X tasks never expand. Out-of-range results are explicit errors, not guessed dates. This does not change diary filenames/day-input grammar or authorize hidden save-time processing. The finite model covers recognized full weekday tokens; general language interpretation and abbreviation handling remain outside this finite check.

| Check | Entire declared domain / encoded constraints | Result type |
| --- | --- | --- |
| Skill example | Two Boolean variables, four valuations; every two-clause subset and all three clauses; repair covers both input values. | Demonstrates joint checking and nonvacuous input coverage. |
| SC-01 | Historical conflict fixes required relative-date input; old strict verbatim and automatic normalization disagree. D-01 repair checks `llm_used`, `proposal_changed`, `consent` over all eight Boolean inputs. Three concrete original strings exercise whitespace, relative words, duplicates and Unicode without consent. | Historical conflict, then unique output per repaired input and nine exact-preservation examples. |
| SC-02 | Output `appended` is Boolean. Fix historical nonempty/all-redundant processed input. D-01 repair covers verbatim/accepted-proposal modes × two nonempty flags × two redundant flags = eight inputs. Redundancy has no effect in verbatim mode. | Literal v0.1 scope conflict, then unique permitted append decision per input. |
| SC-03 | Five existing requested task kinds × two model-configuration values = ten inputs; output `call` is Boolean. Service available and the named action invoked are fixed background for these cases. | Historical three-task allowlist leaves two inputs uncovered; the user-approved five-task profile covers all ten. D-01 consent remains a separate constraint on content changes. |
| Editor | Reachability closure from four initial states, twelve events at each state. The carrier is finite; no trace-depth cutoff is used. | Joint safety/consent coverage witness for selected editor clauses, not liveness. |
| SC-04 | All four tag subsets of `{Project, Topic}` × one cancellation/four accepted selections = twenty inputs: four cancellations, four accepted-empty cases and twelve accepted-nonempty cases. | User-approved tagged-outcome target and collision in old representation. Real terminal dispatch and D-08 persistence remain separate implementation obligations. |
| SC-05 | Four dates spanning month/year boundaries; all 16 pairs and 64 triples, plus all 16 date subsets with four invalid/non-date filenames. Check date filtering, newest-first/latest selection, and every neighbor/boundary in each subset. | User-selected D-04 reference model and historical lexical counterexample; not application conformance or complete filename-grammar verification. |
| SC-06 | Three five-token sets, overlap at least four of five; compare two input orders. | Concrete nontransitivity and order-dependence witness, not a global heuristic analysis. |
| SC-07 | Retain the duplicate-heading collision and fresh-heading witness. Enumerate all 40 heading sequences of length zero through three over three headings, with three queried IDs and six operation classes per sequence. | 720 reference-model decisions distinguish file viewing, missing, unique and ambiguous targets. Rename examples check changed identity; complete Markdown grammar and metadata migration remain unverified. |
| SC-08 | Three prefix byte strings × three target spans × three suffixes × three replacement strings × edit/delete × zero/one/two matching targets = 486 inputs. | Exact byte preservation and unchanged-file failure outcomes in the supplied-span reference model; actual Markdown span discovery and disk writes remain unchecked. |
| SC-09 | Five operational command families × two model-configuration modes × three Boolean availability flags (bundled source, Python dependencies, diary boundary) = 80 inputs. | Nonvacuous mandatory-dependency reference contract: ten ready outcomes and seventy explicit startup failures, no tag-free dispatch. Actual backend success/failure is also exercised in application integration tests. |
| SC-10 | Four operation kinds × recovery intent recorded/not recorded × three observed content outcomes × metadata verified/not verified = 48 cases. For each, three observed retry target states × ready/unready backend = 288 retry cases. Content-outcome inputs are ignored for tag-only operations; future metadata flags are irrelevant if content cannot be confirmed. | Truthful completion/partial/uncertain/failure classification and safe metadata-only replay. Includes successful repairs and completed-receipt replays, so checks are nonvacuous. Physical journal durability and crash/concurrency behaviors remain unverified. |
| SC-11 | Twelve explicit due fixtures (six valid/six unvalidated), four generated-date round trips spanning minimum/maximum years and leap day, six priority fixtures; three diary dates × nine relative tokens × three checkbox states × LLM-use/consent Booleans = 324 relative-date cases. | New-format validation, legacy/invalid-text preservation, consent/open-task guards, completed-task preservation and explicit overflow. No general natural-language or application-conformance proof. |
| SC-12 | Two TTY modes × eleven selections (empty, valid, repeated, malformed, out-of-range and mixed) × seven source states (unchanged, changed text/metadata, shifted lines, completed task, changed other file, missing file) = 154 inputs over four displayed tasks in two files. | Read-only unattended handling, whole-selection rejection, affected-file snapshot checks and checkbox-only updates. Includes every outcome and unselected-file drift; real UI/file I/O and concurrent races remain unchecked. |

D-12 treats displayed tasks as file/line/raw-text observations inside an immutable loaded snapshot, not durable task IDs. Source byte/line equality is used in the reference model; a real implementation may retain fingerprints plus raw selected tasks but must justify that correspondence. It verifies every affected file before applying any selection. Changes to unrelated files do not invalidate the action. Empty unattended history is specified as a normal listing result but is not an additional fixture in this four-task model. Mandatory HTFS startup, post-validation file races and failures during actual writes are outside this selection model.

Each conflict's required scenario is checked separately. They are not conjoined as simultaneous executions. `minimal_conflict` fixes the scenario, checks the whole selected clause set, then verifies satisfiability after each single-clause removal; its two-clause conflicts are inclusion-minimal under that background. No minimum-cardinality claim across the full specification is made.

Repairs use one shared function/transition policy across their entire declared input domain. They do not merely select unrelated favorable executions. The independent models are not combined into a proof of the entire application's satisfiability.

## 5. Reproduction and remaining obligations

```bash
python3 scripts/specification/check_consistency.py --output docs/specification/evidence.json
```

Use `--catalog-root /path/to/mathematical-abstractions` for another checkout. No third-party Python packages, network, ONTFS projection, or catalog writes are required. The evidence records Python version, exact source/encoding/catalog-file hashes, model bounds/counts, and witnesses. Changing source documents requires rerunning the command; an old evidence file is not current evidence.

The unchecked remainder includes complete Markdown parsing/serialization, normalization for all Unicode/text inputs, filesystem permissions and failure recovery, date overflow handling in the implementation, HTFS identity semantics, cross-store operations, lexical ranking quality, model answer correctness, real terminal concurrency, and termination/fairness. Current implementation conformance is a separate task. The finite models do not establish that all legacy documents agree.
