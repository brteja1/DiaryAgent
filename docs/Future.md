# Future Roadmap

This document captures a practical next-stage roadmap for Diary Agent while preserving the current project philosophy:

- local-first
- Markdown as source of truth
- explicit user control
- simple, inspectable workflows

The goal is not to turn the project into a generic AI knowledge platform. The goal is to evolve it into a stronger local diary system with better retrieval, review, and derived insight.

## Direction

The current design is already strong in areas that matter:

- trustworthy local storage
- simple Markdown files
- explicit rewrite control
- durable human-readable data
- practical TODO integration

The main gap compared with more advanced systems is not capture. It is retrieval, derived organization, and higher-level reflection.

## Phase 1: Better Retrieval And Navigation

This is the highest-leverage next step.

- Improve `search` with hybrid retrieval
  - keep lexical scoring
  - add local semantic indexing or embeddings
  - combine both for ranking
- Add structured filters
  - date range
  - specific day
  - TODO-only
  - recent period
- Improve `show` navigation further
  - jump to first or last entry
  - search within current day
  - optional quick movement by date
- Improve the fuzzy picker
  - stronger matching
  - richer preview
  - optional small metadata like TODO count

Why this comes first:

- capture is already usable
- retrieval is where the biggest practical gap exists

## Phase 2: Derived Views

Keep raw Markdown files as the source of truth and build generated views on top.

- weekly summary command
- monthly summary command
- unresolved TODO digest
- people, projects, or topic summaries for a period
- “what changed since last week?” review

These should be derived outputs, not replacements for daily files.

## Phase 3: Light Semantic Structure

Add a small derived metadata layer without replacing the diary files.

- detect people, projects, places, and recurring topics
- maintain a local derived index
- support queries such as:
  - what did I do on project X this month
  - when did I last mention person Y
  - what open follow-ups are related to topic Z

Implementation can remain lightweight:

- local SQLite
- JSON cache
- rebuildable derived artifacts

Raw Markdown should remain canonical.

## Phase 4: Better Capture Intelligence

The current capture model is rewrite-focused. A stronger version would help structure thought without taking control away from the user.

Possible additions:

- optional capture modes
  - quick log
  - polished rewrite
  - reflection
  - meeting note
- better TODO separation
  - commitments
  - reminders
  - loose ideas
- inline suggestions rather than forced transformation
- dedicated “extract TODOs” action

These should remain explicit user-invoked actions.

## Phase 5: Reflection Workflows

This is where a diary becomes significantly more valuable over time.

- end-of-day review
- weekly review
- monthly review
- recurring unresolved themes
- unfinished threads across recent entries
- optional mood or trend summaries if the user wants them

These workflows are often more useful than adding more raw capture features.

## Phase 6: Optional Local Memory Layer

If the project later needs a more advanced intelligence layer, it can add one without giving up local-first principles.

- local embeddings
- derived topic index
- cached summaries
- derived memory cards or timeline snapshots

Requirements for this layer:

- local
- inspectable
- rebuildable from source files

If the memory layer breaks, the Markdown diary should still remain complete and usable.

## Suggested Architecture Evolution

If the project grows along this roadmap, the architecture should evolve toward four layers:

1. Raw diary storage
2. Derived indexes
3. Retrieval and summarization services
4. CLI and UI workflows

This would preserve the current strengths while supporting more sophisticated behavior.

## What To Avoid

The following would likely make the project worse, not better:

- replacing Markdown with opaque app-native storage
- excessive automatic mutation of saved entries
- background agent behavior that edits content without explicit user action
- cloud dependencies added only for more “AI”
- overbuilt knowledge-graph machinery before retrieval is strong

## Best Next Step

If only one thing is prioritized next, it should be:

- build a local derived index and improve `search`

That is the most valuable improvement while staying aligned with the current project philosophy.

## Plan

This section captures a concrete interaction design for integrating Diary Agent with HTFS as a structured semantic layer.

### Role Split

The two systems should keep distinct responsibilities:

- DiaryAgent owns capture, display, and search UX.
- HTFS owns hierarchical metadata and tag querying.

HTFS should enrich retrieval, not replace the diary model.

### Tagging Unit

The recommended tagging unit is the timestamp section within a day file, not the whole file and not individual bullets.

Why:

- file-level tagging is too coarse once a day contains multiple updates
- bullet-level tagging is too granular and harder to maintain
- timestamp sections already exist as natural storage units

Example:

```markdown
## 14:30

- Project work
  - Finished auth cleanup
  - Added regression coverage
```

That entire section should be treated as one retrievable and taggable unit.

### Section Model

Each timestamp section should expose:

- source file path
- date
- time heading
- raw section text
- preview text
- optional HTFS tags

Conceptually:

- source file: `26_03_2026.md`
- section id: `26_03_2026.md#14:30`
- body: all content under that heading until the next heading

### Capture Interaction

After the user saves a section in DiaryAgent:

1. DiaryAgent writes the Markdown section first.
2. Tag derivation may happen after the write.
3. Tagging should not block the diary write.

Two possible approaches:

- explicit tagging
  - user invokes a tag action
  - DiaryAgent suggests tags
  - user confirms and tags are stored in HTFS
- automatic derived tagging
  - DiaryAgent derives candidate tags from a known ontology
  - tags are stored in HTFS automatically
  - user can review later

Recommended starting point:

- automatic derived tagging with later audit and review tools

### Show Interaction

When viewing a timestamp section in `show`, the integration should support:

- viewing associated HTFS tags
- filtering current-day sections by tag
- jumping to related sections sharing tags

This makes HTFS visible as an aid to navigation rather than hidden infrastructure.

### Search Interaction

A hybrid search flow is the preferred design:

1. Parse the user query.
2. Infer likely concepts or candidate tags.
3. Ask HTFS for matching tagged sections.
4. Run lexical or semantic retrieval over diary text.
5. Merge and rank the candidates.
6. Send the best excerpts to the LLM for answer synthesis.

This gives:

- HTFS for structured recall
- local text retrieval for fuzzy recall
- the LLM for final answer generation

### HTFS Storage Role

HTFS should store references to diary sections and their tags, not act as the canonical content store.

For each section, HTFS should know:

- section identifier
- underlying file reference
- associated hierarchical tags

DiaryAgent should maintain the mapping between:

- section id and file path plus heading
- file path plus heading and section text

### Ontology Shape

Start with a small practical ontology rather than a large taxonomy.

Suggested roots:

- `Project/...`
- `People/...`
- `Topic/...`
- `Area/...`
- `Status/...`
- `Place/...`

Examples:

- `Project/DiaryAgent`
- `Project/HTFS`
- `People/Raghub`
- `Topic/Retrieval`
- `Topic/Authentication`
- `Status/Followup`
- `Area/Work`
- `Area/Personal`

### User-Facing Commands

A plausible future CLI surface:

- `diary_agent tags suggest`
  suggest HTFS tags for recent sections
- `diary_agent tags show <day> <time>`
  show tags for one section
- `diary_agent tags apply ...`
  manually attach tags
- `diary_agent related <day> <time>`
  show related tagged sections

The regular `search` command should remain the main entrypoint and internally use both text retrieval and HTFS-aware filtering or boosting.

### Ranking Strategy

HTFS should not decide ranking alone.

Candidate ranking should combine:

- text similarity score
- HTFS tag match score
- recency bonus
- exact phrase bonus

This is important because:

- HTFS is precise but narrow
- text retrieval is broad but noisy

### Implementation Order

Recommended sequence:

1. Add timestamp-section parsing in DiaryAgent.
2. Define stable section identifiers.
3. Build an HTFS adapter layer.
4. Support manual or suggested tagging for sections.
5. Use HTFS as a search boost or filter.
6. Add richer tag-aware navigation later.

### Core Principle

DiaryAgent remains the journal.
HTFS becomes the structured semantic index beside it.
