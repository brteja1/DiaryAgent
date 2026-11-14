# Maintainability refactor

The cleanup applies the external [abstraction-discovery skill](/linuxdev/github/mathematical-abstractions/ai/skills/abstraction-discovery/SKILL.md), followed by [mathematical-tests](/linuxdev/github/mathematical-abstractions/ai/skills/mathematical-tests/SKILL.md). The baseline is commit `99a8ceb`. The dominant finding was structural duplication, rather than a missing algebraic class hierarchy.

## Scope and discovery

Python is the application source language. The initial scope was `diary_agent.py` and the six Python modules in `diary_agent_app/`; dependency source, generated artifacts and tests were excluded from runtime-pattern counts. Counts were collected before reading implementations. All seven files were then read, including zero/low-density files: the skill's 1–20-file tier requires the entire scope, so no tier was cut short.

These are matching **lines**, not independent defects. Counts after cleanup use the same patterns across the entrypoint and all application modules; formatting/comments can affect them.

| Pattern | Regex | Before | After |
| --- | --- | ---: | ---: |
| Combination | `\b(combine\|merge\|fold\|reduce\|append\|concat\|accumulate)\b` | 44 | 40 |
| Comparison | `\b(compare\|compareTo\|cmp\|lt\|lte\|gt\|gte\|lessThan\|greaterThan\|sorted\|sort)\b` | 16 | 12 |
| Transformation | `\b(map\|fmap\|transform\|project\|select\|convert)\b` | 1 | 1 |
| Initialization | `\b(empty\|zero\|identity\|neutral\|initial\|default)\b` | 17 | 23 |
| Resource lifecycle | `\b(try\|finally\|close\|_client)\b` | 89 | 33 |

Combined initial density, highest first: `htfs_adapter.py` 65, `diary_agent.py` 56, `ui.py` 29, `llm.py` 11, `core.py` 4, `models.py` 2, `__init__.py` 0. This ordering determined inspection, rather than treating only the largest file as the whole problem.

## Inventory and structural changes

Counts below describe concrete static call sites, not dynamic execution frequencies. “Copies” means separately implemented instances of the named pattern. Existing model records were reused rather than replaced with a new object framework.

| Abstraction / interface | Initial uses and copies | Diagnosis | Result |
| --- | --- | --- | --- |
| `HTFSAdapter._client() -> HTFS` | 14 uses, each with its own cleanup block | Factory well used; session ownership missing | `_session()` context manager has 14 uses, one acquisition/close site and no copied cleanup blocks. |
| Ollama task helpers | Five `ollama.chat`/transport-error blocks | Missing shared transport boundary | `_chat(model, messages) -> str` has five callers and one transport call. Prompts remain task-specific. |
| `core` parsing/scoring helpers | Existing helpers plus forwarding functions in the entrypoint | Redundant indirection, not missing logic | Direct imports from their owners; 12 trivial root forwarding definitions removed. Bound domain-to-LLM methods remain where they supply model/context policy. |
| Section parsing | Eight calls to the domain parser, plus separate viewer heading/body scans | Underused parser; no exact mutation spans | `DiaryDocument.parse()` supplies source spans, display sections, cursor lookup and unique-target mutation. One heading recognizer is shared with annotations. |
| TODO state mutation | Two parse/render/rewrite pipelines | Existing parser reused, source-preserving update missing | `todo_with_state(line, state)` splices one checkbox character; completion and viewer toggle both use it. |
| Capture workflows | Repeated optional-day branches and processed save paths | Mirrored pipelines and hidden policy | Two explicit workflows, shared exact persistence and output; proposal preparation is separate from final saving. |
| Editor background actions | Two lock/executor/error/unlock pipelines | Missing lifecycle helper | `_start_editor_action` has two callers. `EditorState` owns busy/review state and suggestions. |
| Tag input | GUI and CLI repeated selection parsing/unknown-tag checks | Missing shared interpretation | Presentation-specific input functions feed one validation/confirmation path. `None` differs from accepted `[]`. |
| `PendingTask` | Shared location/metadata record | Healthy abstraction, insufficient stale-state evidence | Reused with a source snapshot; scan once, validate all selected files before writes. |

The code also had repeated conditional branches, mirrored transformations, synchronized UI flags and long callback argument lists. These signals justified structural cleanup first. The viewer callback interface remains explicit rather than introducing a generic callback registry; a larger interface object is deferred until it removes more complexity than it adds.

The executable is now nine lines. The CLI, command presentation, domain operations, Markdown representation and viewer have distinct owning modules; [Design.md](Design.md) shows dependencies. The service does not import terminal UI. Dead similarity-confirmation dialogs and the unused today-context wrapper were removed.

## Scoped mathematical assessment

Catalog validation reported 220 concepts, 2,132 nodes and no structural errors. Selected records were retrieved after the behavioral inventory. Discovery used focused catalog records; the test-design follow-up used bounded ONTFS/SPARQL queries against a separate `/tmp/diary-test-catalog` projection because the catalog checkout was read-only. No catalog files or dependency revisions were changed.

| Candidate and stable IDs (`urn:csabs:` prefix) | Carrier, operation and equality | Assessment |
| --- | --- | --- |
| `concept/TotalOrder`; `operation/TotalOrder-basis-le`; `axiom/TotalOrder-reflexive`, `TotalOrder-transitive`, `TotalOrder-antisymmetric`, `TotalOrder-comparable` | Valid Gregorian diary dates; parsed date comparison; equality of dates. Navigation observes a sorted sequence of valid paths. | Conditionally applicable on valid dates. Lexical filename order was a valid order on strings but violated the product's calendar order. Boundary/invalid-file tests now cover the corrected selection. No general ordering proof is claimed. |
| `concept/OptionType`; `operation/option-none`, `OptionType-some`, `option-case`; `axiom/option-case-none`, `option-case-some` | Optional accepted tag lists, where `None` is absent and every list, including `[]`, is present. Observe final tag sets after successful backend operations. | Previously violated by collapsing cancel and accepted-empty. Successful cancel/clear/replace cases now distinguish the constructors. Effects/failure recovery are outside the pure option equations. |
| `concept/EquivalenceRelation`; `axiom/equivalence-reflexive`, `equivalence-symmetric`, `equivalence-transitive` | Exact equality of normalized TODO keys, as distinct from heuristic near-matching of lines. | Key equality has the equivalence interpretation; near-matching does **not**. No equivalence interface or transitive deduplication algorithm was imposed on that heuristic. |
| None: backend sessions, model transport and code ownership | Resource lifecycle, effectful calls and module responsibilities | Structural refactoring candidates. Calling these a monoid, lattice or CRDT would introduce unsupported semantics. |

Concrete counterexamples:

- `31_12_2025.md` precedes `01_01_2026.md` by date, while filename lexicographic sorting reverses them.
- With prior tags `{Old}`, cancellation must retain `{Old}` and accepted-empty must yield `{}`. Encoding both as `[]` loses required information.
- For `A="a b c d"`, `B="a b c d e"`, `C="b c d e"`, the lexical near-match heuristic relates A/B and B/C but not A/C. Transitive closure would change its meaning.
- A preamble and unrelated CRLF section cannot be recovered byte-for-byte by reconstructing the file from stripped section bodies. Mutation must retain source ranges.

The selected TotalOrder axioms and EquivalenceRelation records have legacy source gaps (`provenanceStatus: legacy-source-missing`). Option case records cite `urn:csabs:source/awodey-types` and are editorial summaries, not machine-proved witnesses. Passing tests does not repair provenance or establish universal mathematical refinement. [Testing.md](Testing.md) gives operation/observer mappings and finite test domains.

## Limits and next work

D-08 recovery is deliberately still recorded as pending: there is no intent journal, completion receipt or metadata retry command. Current cross-store deletion/replacement can fail partially. D-11 structured validation/presentation of unvalidated metadata is also pending. These require dedicated implementation and failure tests, rather than an algebraic name or tests accepting the wrong behavior.

A later implementation-mapping/conformance review can formalize these remaining boundaries. This change uses concrete contract tests and does not claim a formal conformance proof. Real terminal rendering and a live Ollama server were not exercised by the automated suite.
