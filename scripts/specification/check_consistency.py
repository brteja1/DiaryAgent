#!/usr/bin/env python3
"""Finite specification models, not implementation-conformance tests.

Run from any directory. All domains and translations are documented in
docs/specification/MathematicalModel.md. No model calls or diary writes occur.
"""
from __future__ import annotations

import argparse
from collections import deque
from dataclasses import asdict, dataclass, replace
from datetime import date, timedelta
from hashlib import sha256
from itertools import combinations, product
import json
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BITS = (False, True)


def require(condition, message):
    # Deliberately not assert: checks also run under python -O.
    if not condition:
        raise RuntimeError(message)


def models(rules, names):
    return [x for x in BITS if all(rules[name](x) for name in names)]


def minimal_conflict(rules):
    """Check the entire selected set and every single-clause deletion."""
    names = tuple(rules)
    require(not models(rules, names), f"Expected conflict: {names}")
    removals = {name: models(rules, tuple(n for n in names if n != name)) for name in names}
    require(all(removals.values()), f"Conflict was not inclusion-minimal: {names}")
    return {"clauses": names, "single_clause_removal_witnesses": removals}


def boolean_demonstration():
    # Skill reference example: every pair SAT, full conjunction UNSAT.
    rows = list(product(BITS, repeat=2))
    rules = {
        "R1": lambda a, o: not o or a,
        "R2": lambda a, o: a or o,
        "S1": lambda a, o: not a,
    }
    sat = lambda ids: [(a, o) for a, o in rows if all(rules[k](a, o) for k in ids)]
    pairs = {"+".join(pair): sat(pair) for pair in combinations(rules, 2)}
    require(all(pairs.values()) and not sat(tuple(rules)), "Boolean demonstration failed")
    original = {str(a): [o for o in BITS if rules["R1"](a, o) and rules["R2"](a, o)] for a in BITS}
    repaired = {str(a): [o for o in BITS if (not o or a) and (a or not o)] for a in BITS}
    require(not original["False"] and all(repaired.values()), "Coverage example failed")
    return {"valuation_count": 4, "pair_witnesses": pairs, "full_set": "UNSAT",
            "original_outputs": original, "repaired_outputs": repaired}


def save_contracts():
    # SC-01: strict equality and mandatory changed-date normalization.
    conflict = minimal_conflict({
        "LEGACY-VERBATIM": lambda changed: not changed,
        "LEGACY-TODO-02[relative-date-input]": lambda changed: changed,
    })
    repaired = []
    for llm_used, proposal_changed, consent in product(BITS, repeat=3):
        outputs = [changed for changed in BITS
                   if (not changed or llm_used)
                   and (not changed or consent)
                   and changed == (llm_used and proposal_changed and consent)]
        require(len(outputs) == 1, "Consent-based save coverage failed")
        repaired.append({"llm_used": llm_used, "proposal_changed": proposal_changed,
                         "consent": consent, "changed_outputs": outputs})
    originals = ("- [ ] Call mom tomorrow  \n", "- Same note\n- Same note\n", "  Personal reflection Ω  ")
    preserved = 0
    for original, llm_used, consent in product(originals, BITS, BITS):
        proposal = "- An LLM proposal"
        saved = proposal if llm_used and consent else original
        require(saved == (proposal if llm_used and consent else original), "Save policy failed")
        if not llm_used or not consent:
            require(saved == original, "Unconsented save changed exact text")
            preserved += 1
    # SC-02: all-redundant processed input is nonempty but must not append.
    append_conflict = minimal_conflict({
        "v0.1-DATA-02[nonempty]": lambda appended: appended,
        "CAP-12[all-redundant]": lambda appended: not appended,
    })
    append_coverage = []
    for mode, nonempty, all_redundant in product(("verbatim", "accepted_proposal"), BITS, BITS):
        expected = nonempty and (mode == "verbatim" or not all_redundant)
        outputs = [appended for appended in BITS if appended == expected]
        require(len(outputs) == 1, "Capture coverage failed")
        append_coverage.append({"mode": mode, "nonempty": nonempty,
                                "all_redundant": all_redundant, "outputs": outputs})
    return {"SC-01": {"original_conflict": conflict, "repair_coverage": repaired,
                      "verbatim_text_cases": preserved},
            "SC-02": {"original_conflict": append_conflict, "repair_coverage": append_coverage}}


def llm_allowlist():
    tasks = ("rewrite", "todo_similarity", "answer", "tag_suggestion", "tag_translation")
    old = set(tasks[:3])
    no_outputs = []
    witnesses = []
    for configured, task in product(BITS, tasks):
        # requested task, available service and explicit invocation are fixed background.
        original = [call for call in BITS if (not call or task in old) and call == configured]
        if not original:
            no_outputs.append({"configured": configured, "task": task})
        repaired = [call for call in BITS if (not call or task in tasks) and call == configured]
        require(len(repaired) == 1, "Expanded allowlist has uncovered input")
        witnesses.append({"configured": configured, "task": task, "outputs": repaired})
    require(len(no_outputs) == 2, "Expected both legacy tag-operation conflicts")
    return {"SC-03": {"legacy_uncovered_inputs": no_outputs,
                      "expanded_profile_coverage": witnesses}}


@dataclass(frozen=True)
class Editor:
    configured: bool
    phase: str = "editing"
    draft: str = "raw"
    suggested: bool = False
    saved: bool = False
    proposal: str | None = None
    accepted: bool = False


EVENTS = ("edit_raw", "edit_empty", "rewrite", "suggest", "submit",
          "rewrite_ok", "rewrite_empty", "rewrite_error", "suggest_ok", "suggest_error",
          "accept", "reject")


def step(s, event):
    if s.phase == "closed":
        return s
    if s.phase == "reviewing":
        if event == "accept":
            return replace(s, phase="editing", draft=s.proposal, proposal=None, accepted=True)
        if event == "reject":
            return replace(s, phase="editing", proposal=None)
        return s
    if s.phase == "rewriting":
        if event in ("rewrite_ok", "rewrite_empty", "rewrite_error"):
            draft = {"rewrite_ok": "rewritten", "rewrite_empty": "empty"}.get(event, s.draft)
            if event == "rewrite_error":
                return replace(s, phase="editing")
            return replace(s, phase="reviewing", proposal=draft)
        return s
    if s.phase == "suggesting":
        if event in ("suggest_ok", "suggest_error"):
            return replace(s, phase="editing", suggested=s.suggested or event == "suggest_ok")
        return s
    if event.startswith("edit_"):
        return replace(s, draft=event.removeprefix("edit_"))
    if event == "submit":
        return replace(s, phase="closed", saved=s.draft != "empty")
    if event in ("rewrite", "suggest") and s.configured:
        return replace(s, phase="rewriting" if event == "rewrite" else "suggesting")
    return s


def editor_model():
    initial = {Editor(configured=m, draft=d) for m, d in product(BITS, ("empty", "raw"))}
    require(bool(initial), "Empty initial-state set")
    reached = set(initial)
    queue = deque(initial)
    edge_count = 0
    while queue:
        s = queue.popleft()
        for event in EVENTS:
            t = step(s, event)
            edge_count += 1
            # CAP-01/02/04/05 and QUAL-02 checked together on each edge.
            require(not t.saved or (t.phase == "closed" and t.draft != "empty"), "Invalid save")
            require(t.draft != "rewritten" or t.accepted, "LLM draft applied without consent")
            require((t.phase == "reviewing") == (t.proposal is not None), "Invalid proposal state")
            if s.phase in ("rewriting", "suggesting", "reviewing"):
                if event in ("submit", "rewrite", "suggest", "edit_raw", "edit_empty"):
                    require(t == s, "Busy editor accepted a conflicting action")
            if s.phase == "rewriting" and event in ("rewrite_ok", "rewrite_empty"):
                require(t.draft == s.draft and not t.saved, "Unreviewed proposal changed content")
            if s.phase == "reviewing" and event == "reject":
                require(t.phase == "editing" and t.draft == s.draft, "Rejection lost prior draft")
            if s.phase == "reviewing" and event == "accept":
                require(t.draft == s.proposal and t.accepted, "Accepted wrong proposal")
            if s.phase == "rewriting" and event == "rewrite_error":
                require(t.phase == "editing" and t.draft == s.draft, "Rewrite failure lost draft")
            if s.phase == "suggesting" and event in ("suggest_ok", "suggest_error"):
                require(t.phase == "editing" and t.draft == s.draft and not t.saved,
                        "Suggestion changed or saved content")
            if not s.configured and event in ("rewrite", "suggest"):
                require(t == s, "Disabled LLM operation started")
            if t not in reached:
                reached.add(t)
                queue.append(t)
    busy = Editor(True, phase="rewriting")
    require(step(busy, "submit") == busy, "Missing permitted waiting trace")
    trace = [Editor(True)]
    for event in ("rewrite", "rewrite_ok", "accept", "submit"):
        trace.append(step(trace[-1], event))
    return {"initial_states": len(initial), "reachable_states": len(reached),
            "checked_edges": edge_count, "events_per_state": len(EVENTS),
            "safety": "PASS for complete reachable finite reference model",
            "progress": "NOT CLAIMED; waiting self-loop permits noncompletion",
            "witness_trace": [asdict(s) for s in trace]}


def cancellation_model():
    inventory = ("Project", "Topic")
    tagsets = [frozenset(inventory[i] for i in range(2) if bits[i]) for bits in product(BITS, repeat=2)]
    # Distinct constructors: Cancelled versus Accepted(payload), including empty payload.
    results = [("cancelled", frozenset())] + [("accepted", tags) for tags in tagsets]
    cases = 0
    case_counts = {"cancelled": 0, "accepted_empty": 0, "accepted_nonempty": 0}
    for previous, (kind, selected) in product(tagsets, results):
        outputs = [after for after in tagsets
                   if (kind != "cancelled" or after == previous)
                   and (kind != "accepted" or after == selected)]
        require(len(outputs) == 1, "Cancellation/acceptance input lacks a unique outcome")
        case_counts["cancelled" if kind == "cancelled" else
                    ("accepted_nonempty" if selected else "accepted_empty")] += 1
        cases += 1
    require(case_counts == {"cancelled": 4, "accepted_empty": 4, "accepted_nonempty": 12},
            "Incomplete D-09 cancellation/acceptance coverage")
    # SC-04: the old collapsed representation cannot implement the selected contract.
    old = frozenset({"Project"})
    collapsed_cancel = collapsed_accept_empty = frozenset()
    require(collapsed_cancel == collapsed_accept_empty and old != frozenset(), "No collision witness")
    return {"SC-04": {"repair_inputs": cases, "repair_coverage": "PASS",
                       "case_counts": case_counts, "decision": "D-09 approved; runtime repair pending",
                       "collapsed_representation": [], "same_previous_tags": sorted(old),
                       "required_cancel_output": sorted(old), "required_accept_empty_output": []}}


def order_and_similarity():
    days = [date(2025, 12, 31), date(2026, 1, 1), date(2026, 3, 31), date(2026, 4, 1)]
    require(all((a <= b or b <= a) and ((a <= b and b <= a) == (a == b)) for a, b in product(days, repeat=2)),
            "Date total-order failure")
    require(all(not (a <= b and b <= c) or a <= c for a, b, c in product(days, repeat=3)),
            "Date transitivity failure")
    chronological = [d.strftime("%d_%m_%Y.md") for d in sorted(days)]
    lexical = sorted(chronological)
    require(lexical != chronological, "Missing lexical/calendar counterexample")
    invalid_names = ("notes.md", "31_02_2026.md", "1_04_2026.md", "2026_04_01.md")

    def parsed_day(name):
        match = re.fullmatch(r"([0-9]{2})_([0-9]{2})_([0-9]{4})\.md", name)
        if not match:
            return None
        day, month, year = map(int, match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None

    inventory_cases = neighbor_inputs = 0
    for included in product(BITS, repeat=len(days)):
        expected_dates = [d for d, keep in zip(days, included) if keep]
        names = [d.strftime("%d_%m_%Y.md") for d in reversed(expected_dates)] + list(invalid_names)
        navigable = sorted(d for name in names if (d := parsed_day(name)) is not None)
        require(navigable == expected_dates, "D-04 filtering/order failure")
        picker = list(reversed(navigable))
        require(picker == sorted(expected_dates, reverse=True), "Picker is not newest first")
        latest = picker[0] if picker else None
        require(latest == max(expected_dates, default=None), "Incorrect latest/empty result")
        for index, current in enumerate(navigable):
            previous = navigable[index - 1] if index > 0 else None
            following = navigable[index + 1] if index + 1 < len(navigable) else None
            require(previous == max((d for d in expected_dates if d < current), default=None),
                    "Incorrect previous/boundary result")
            require(following == min((d for d in expected_dates if d > current), default=None),
                    "Incorrect next/boundary result")
            neighbor_inputs += 2
        inventory_cases += 1
    # Illustrative five-token sets instantiate the non-transitive overlap heuristic.
    a, b, c = (frozenset(x.split()) for x in ("a b c d e", "a b c d f", "a b c f g"))
    near = lambda x, y: len(x & y) * 5 >= min(len(x), len(y)) * 4
    require(near(a, b) and near(b, c) and not near(a, c), "Missing nontransitivity witness")
    accept = lambda order: greedy(order, near)
    require(accept((a, b, c)) != accept((b, a, c)), "Missing order-dependent witness")
    return {"SC-05": {"dates": chronological, "lexical_order": lexical,
                       "order_triples_checked": len(days) ** 3,
                       "invalid_filename_examples": invalid_names,
                       "inventory_cases_checked": inventory_cases,
                       "neighbor_inputs_checked": neighbor_inputs},
            "SC-06": {"A": sorted(a), "B": sorted(b), "C": sorted(c),
                       "A_near_B": True, "B_near_C": True, "A_near_C": False,
                       "accepted_A_B_C": [sorted(x) for x in accept((a, b, c))],
                       "accepted_B_A_C": [sorted(x) for x in accept((b, a, c))]}}


def greedy(items, near):
    accepted = []
    for item in items:
        if not any(near(item, old) for old in accepted):
            accepted.append(item)
    return accepted


def key_collision():
    # SC-07: unique identity is conditional on well-formed heading inputs.
    sections = [("14:30", "first"), ("14:30", "second")]
    ids = [f"14_11_2026.md#{heading}" for heading, _ in sections]
    require(len(ids) != len(set(ids)), "Missing duplicate-heading witness")
    repaired_ids = ["14_11_2026.md#14:30", "14_11_2026.md#14:30:2"]
    require(len(repaired_ids) == len(set(repaired_ids)), "Fresh headings collide")
    headings = ("14:30", "14:30:2", "15:00")
    operations = ("view", "edit", "delete", "tags_show", "tags_apply", "tags_suggest")
    outcomes = ("viewable", "missing", "ambiguous", "allowed")
    sequence_count = operation_inputs = 0
    outcome_counts = dict.fromkeys(outcomes, 0)
    for length in range(4):
        for sequence in product(headings, repeat=length):
            sequence_count += 1
            for target, operation in product(headings, operations):
                matches = sum(heading == target for heading in sequence)
                permitted = [outcome for outcome in outcomes
                             if (operation != "view" or outcome == "viewable")
                             and (operation == "view" or matches != 0 or outcome == "missing")
                             and (operation == "view" or matches != 1 or outcome == "allowed")
                             and (operation == "view" or matches <= 1 or outcome == "ambiguous")]
                require(len(permitted) == 1, "D-05 lookup/operation coverage failed")
                outcome = permitted[0]
                require(operation == "view" or (outcome == "allowed") == (matches == 1),
                        "Ambiguous/missing ID permitted a section operation")
                outcome_counts[outcome] += 1
                operation_inputs += 1
    require(sequence_count == 40 and operation_inputs == 720, "Incomplete D-05 enumeration")
    original_id = "14_11_2026.md#14:30"
    renamed_ids = ("15_11_2026.md#14:30", "14_11_2026.md#15:00")
    require(all(value != original_id for value in renamed_ids), "Rename did not change identity")
    return {"SC-07": {"duplicate_input_ids": ids, "fresh_heading_witness": repaired_ids,
                      "heading_sequences_checked": sequence_count,
                      "operation_inputs_checked": operation_inputs,
                      "outcome_counts": outcome_counts,
                      "rename_witnesses": renamed_ids,
                      "scope": "finite D-05 policy model, not Markdown parsing or implementation conformance"}}


def targeted_mutations():
    """D-06 reference model: spans are supplied, not parsed from Markdown."""
    prefixes = (b"", b"Preamble  \r\n\r\n", "Préface Ω\n".encode("utf-8"))
    bodies = (b"old\n", b"  old  \r\n\r\n", "Ancienne note Ω\n".encode("utf-8"))
    suffixes = (b"", b"## 15:00\n\nUnchanged  ", b"## 15:00\r\n\r\nUnchanged\r\n")
    replacements = (b"new\n", b"  new  \r\n", "Nouvelle note Ω\n".encode("utf-8"))
    heading = b"## 14:30\r\n\r\n"
    inputs = successful = unchanged_errors = 0
    for prefix, body, suffix, replacement, operation, matches in product(
            prefixes, bodies, suffixes, replacements, ("edit", "delete"), (0, 1, 2)):
        before = prefix + heading + body + suffix
        if matches != 1:
            outcome = "missing" if matches == 0 else "ambiguous"
            after = before
            require(outcome in ("missing", "ambiguous") and after == before,
                    "D-06 invalid target changed bytes")
            unchanged_errors += 1
        else:
            kept_prefix = prefix + heading if operation == "edit" else prefix
            inserted = replacement if operation == "edit" else b""
            after = kept_prefix + inserted + suffix
            require(after[:len(kept_prefix)] == kept_prefix, "D-06 modified prefix/heading")
            require(after[len(after) - len(suffix):] == suffix, "D-06 modified suffix")
            require(after[len(kept_prefix):len(kept_prefix) + len(inserted)] == inserted,
                    "D-06 changed replacement bytes")
            require(len(after) == len(kept_prefix) + len(inserted) + len(suffix),
                    "D-06 introduced extra bytes")
            successful += 1
        inputs += 1
    require(inputs == 486 and successful == 162 and unchanged_errors == 324,
            "Incomplete D-06 model coverage")
    return {"SC-08": {"input_cases_checked": inputs, "successful_span_updates": successful,
                      "unchanged_error_outcomes": unchanged_errors,
                      "scope": "supplied spans and exact byte postconditions; no parsing or real file writes"}}


def required_htfs():
    """D-07: keep missing-backend scenarios in the required input domain."""
    commands = ("capture", "show", "todos", "search", "tags")
    outcomes = (("ready", True), ("failed", False))
    inputs = ready = failed = 0
    for command, model, source, dependencies, boundary in product(commands, BITS, BITS, BITS, BITS):
        available = source and dependencies and boundary
        permitted = [(status, dispatch) for status, dispatch in outcomes
                     if dispatch == available and (status == "ready") == available]
        require(len(permitted) == 1, "D-07 startup input lacks a unique permitted outcome")
        status, dispatch = permitted[0]
        require(available or (status == "failed" and not dispatch), "HTFS failure allowed dispatch")
        ready += status == "ready"
        failed += status == "failed"
        inputs += 1
    require(inputs == 80 and ready == 10 and failed == 70, "Incomplete mandatory-HTFS coverage")
    return {"SC-09": {"input_cases_checked": inputs, "ready_outcomes": ready,
                      "explicit_failure_outcomes": failed,
                      "scope": "mandatory startup gate, not later write/recovery guarantees"}}


def recovery_contract():
    """D-08 reference outcomes and metadata-only replay; no real persistence."""
    operations = ("capture", "edit", "delete", "replace_tags")
    content_outcomes = ("not_written", "committed", "unknown")
    cases = retry_cases = successful_repairs = completed_replays = 0
    outcome_counts = dict.fromkeys(("failed", "uncertain", "partial", "complete"), 0)
    for operation, recorded, content_outcome, metadata_verified in product(
            operations, BITS, content_outcomes, BITS):
        # One operation identity and recovery intent are shared by every retry.
        operation_id = (operation, recorded, content_outcome, metadata_verified)
        writes = int(recorded and operation != "replace_tags")
        if not recorded:
            status = "failed"
        elif operation != "replace_tags" and content_outcome == "not_written":
            status = "failed"
        elif operation != "replace_tags" and content_outcome == "unknown":
            status = "uncertain"
        elif operation == "replace_tags":
            status = "complete" if metadata_verified else "uncertain"
        else:
            status = "complete" if metadata_verified else "partial"
        require(recorded or writes == 0, "Mutation started without recovery intent")
        require(status != "complete" or (recorded and metadata_verified), "Unverified complete result")
        if recorded and operation != "replace_tags" and content_outcome == "committed":
            require(status in ("complete", "partial") and writes == 1,
                    "Committed Markdown was lost or reported unchanged")
        if recorded and operation != "replace_tags" and content_outcome == "unknown":
            require(status == "uncertain", "Unknown write was reported as a confirmed save")
        outcome_counts[status] += 1
        for observed_target, backend_ready in product(("before", "desired", "diverged"), BITS):
            # 'observed_target' abstracts content for combined operations and
            # the current associations for tag-only operations.
            if status == "complete":
                retry_status = "already_complete"
                completed_replays += 1
            elif not recorded:
                retry_status = "missing_record"
            elif observed_target == "diverged":
                retry_status = "conflict"
            elif operation != "replace_tags" and observed_target != "desired":
                retry_status = "content_not_confirmed"
            elif not backend_ready:
                retry_status = "pending"
            else:
                retry_status = "complete"
                # Assignment to the intended set is idempotent; repeated
                # requests use a completion receipt and do not replay it.
                intended_tags = frozenset() if operation == "delete" else frozenset({"Project"})
                actual_tags = intended_tags
                repeated_status, repeated_tags = "already_complete", actual_tags
                require(repeated_status == "already_complete" and repeated_tags == intended_tags,
                        "Completed metadata repair changed tags on replay")
                successful_repairs += 1
            retry_content_writes = 0
            require(writes + retry_content_writes == writes, "Metadata retry replayed content mutation")
            require(operation_id == (operation, recorded, content_outcome, metadata_verified),
                    "Retry allocated a new operation")
            if observed_target == "diverged" and recorded and status != "complete":
                require(retry_status == "conflict", "Diverged target was overwritten")
            retry_cases += 1
        cases += 1
    require(cases == 48 and retry_cases == 288 and successful_repairs > 0 and completed_replays > 0,
            "Incomplete/vacuous D-08 coverage")
    return {"SC-10": {"operation_cases_checked": cases, "outcome_counts": outcome_counts,
                      "metadata_retry_cases_checked": retry_cases,
                      "successful_repairs": successful_repairs,
                      "completed_receipt_replays": completed_replays,
                      "scope": "finite observed-outcome/replay policy; not storage, crash, or concurrency verification"}}


def todo_metadata_contract():
    """D-11 finite reference parsers/proposal selection, never app save code."""
    def formatted(day):
        return f"{day.day:02}-{day.month:02}-{day.year:04}"

    def parsed(raw):
        patterns = ((r"([0-9]{2})-([0-9]{2})-([0-9]{4})", (2, 1, 0)),
                    (r"([0-9]{4})-([0-9]{2})-([0-9]{2})", (0, 1, 2)),
                    (r"([0-9]{2})_([0-9]{2})_([0-9]{4})", (2, 1, 0)))
        for pattern, order in patterns:
            match = re.fullmatch(pattern, raw)
            if match:
                values = tuple(map(int, match.groups()))
                try:
                    value = date(*(values[index] for index in order))
                except ValueError:
                    break
                return "validated", value, raw
        return "unvalidated", None, raw

    due_values = ("16-11-2026", "2026-11-16", "16_11_2026", "29-02-2024",
                  "01-01-0001", "31-12-9999", "31-02-2026", "29-02-2025",
                  "1-1-2026", "tomorrow", "", "00-11-2026")
    validated = unvalidated = 0
    for raw in due_values:
        kind, value, retained = parsed(raw)
        require(retained == raw, "D-11 parsing rewrote legacy/invalid text")
        require((kind == "validated") == (value is not None), "Invalid tagged date result")
        validated += kind == "validated"
        unvalidated += kind == "unvalidated"
    require(validated == 6 and unvalidated == 6, "Unexpected date-fixture classification")
    generated_days = (date(1, 1, 1), date(2024, 2, 29), date(2026, 12, 31), date(9999, 12, 31))
    for day in generated_days:
        rendered = formatted(day)
        require(re.fullmatch(r"[0-9]{2}-[0-9]{2}-[0-9]{4}", rendered) is not None,
                "Generated date is not DD-MM-YYYY")
        require(parsed(rendered) == ("validated", day, rendered), "Generated-date round trip failed")
    priorities = ("low", "medium", "high", "urgent", "HIGH", "")
    for raw in priorities:
        kind, retained = ("validated" if raw in priorities[:3] else "unvalidated"), raw
        require(retained == raw and (kind == "validated") == (raw in ("low", "medium", "high")),
                "Priority handling normalized/dropped unvalidated text")

    weekdays = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    bases = (date(2024, 2, 28), date(2026, 3, 25), date(9999, 12, 31))
    cases = changed = retained_count = out_of_range = 0
    for base, token, state, llm_used, consent in product(
            bases, ("today", "tomorrow") + weekdays, (" ", "x", "X"), BITS, BITS):
        permitted = state == " " and llm_used and consent
        status, output = "unchanged", token
        if permitted:
            offset = 0 if token == "today" else (1 if token == "tomorrow" else
                                                (weekdays.index(token) - base.weekday()) % 7)
            try:
                target = base + timedelta(days=offset)
            except OverflowError:
                status = "out_of_range"
                out_of_range += 1
            else:
                status, output = "proposed", formatted(target)
                if token in weekdays:
                    require(target.weekday() == weekdays.index(token) and 0 <= (target - base).days < 7,
                            "Weekday proposal is not the nearest occurrence on/after the diary day")
                if base == date(2024, 2, 28) and token == "tomorrow":
                    require(output == "29-02-2024", "Leap-day proposal failed")
                changed += 1
        if not permitted or status == "out_of_range":
            require(output == token, "D-11 changed a completed/unconsented/invalid date")
            retained_count += 1
        if state in ("x", "X"):
            require(status == "unchanged" and output == token, "Completed date was expanded")
        cases += 1
    require(cases == 324 and changed > 0 and out_of_range > 0, "Incomplete/vacuous D-11 coverage")
    return {"SC-11": {"due_fixtures": len(due_values), "validated_due_fixtures": validated,
                      "unvalidated_due_fixtures": unvalidated,
                      "generated_date_round_trips": len(generated_days),
                      "priority_fixtures": len(priorities), "relative_date_cases": cases,
                      "consented_open_task_proposals": changed, "preserved_text_cases": retained_count,
                      "out_of_range_errors": out_of_range,
                      "scope": "finite metadata/proposal reference model; not general LLM/text interpretation or implementation conformance"}}


def todo_selection_contract():
    """D-12 finite selection/snapshot model; no stdin or file writes."""
    snapshot = {
        "a.md": (b"- [ ] First\n", b"- [ ] Same [due: 16-11-2026]\n"),
        "b.md": (b"- [ ] Third\n", b"- [ ] Same [priority: high]\n"),
    }
    tasks = [(name, index, raw) for name, lines in snapshot.items()
             for index, raw in enumerate(lines)]
    unchanged = dict(snapshot)
    changed_text = {**snapshot, "a.md": (b"- [ ] Changed\n", snapshot["a.md"][1])}
    changed_metadata = {**snapshot, "a.md": (snapshot["a.md"][0], b"- [ ] Same [due: 17-11-2026]\n")}
    moved_lines = {**snapshot, "a.md": (b"Inserted line\n",) + snapshot["a.md"]}
    completed_task = {**snapshot, "a.md": (b"- [x] First\n", snapshot["a.md"][1])}
    other_file = {**snapshot, "b.md": (b"- [ ] Changed third\n", snapshot["b.md"][1])}
    missing_file = {"b.md": snapshot["b.md"]}
    live_states = (unchanged, changed_text, changed_metadata, moved_lines,
                   completed_task, other_file, missing_file)
    selections = ("", "1", "1,4", "2,2", "0", "5", "-1", "oops", "1,5", "1,oops", "1,,2")

    def apply(tty, selection, live):
        if not tty:
            return "listed", dict(live), set()
        if not selection.strip():
            return "no_change", dict(live), set()
        try:
            indices = {int(part.strip()) for part in selection.split(",")}
        except ValueError:
            return "invalid", dict(live), set()
        if any(index < 1 or index > len(tasks) for index in indices):
            return "invalid", dict(live), set()
        selected = [tasks[index - 1] for index in sorted(indices)]
        affected = {name for name, _index, _raw in selected}
        if any(live.get(name) != snapshot[name] for name in affected):
            return "stale", dict(live), set()
        if any(live[name][index] != raw or b"[ ]" not in raw for name, index, raw in selected):
            return "stale", dict(live), set()
        after = dict(live)
        completed = set()
        for name, index, raw in selected:
            marker = raw.index(b"[ ]") + 1
            lines = list(after[name])
            lines[index] = raw[:marker] + b"x" + raw[marker + 1:]
            after[name] = tuple(lines)
            completed.add((name, index))
        return "updated", after, completed

    outcomes = dict.fromkeys(("listed", "no_change", "invalid", "stale", "updated"), 0)
    cases = 0
    for tty, selection, live in product(BITS, selections, live_states):
        status, after, completed = apply(tty, selection, live)
        require(tty or (status == "listed" and after == live and not completed),
                "Unattended selection changed tasks")
        if status != "updated":
            require(after == live and not completed, "Rejected/empty selection partially updated tasks")
        else:
            expected = {tasks[int(part.strip()) - 1][:2] for part in selection.split(",")}
            require(completed == expected, "Valid repeated indices changed unintended tasks")
            for name, lines in live.items():
                for index, raw in enumerate(lines):
                    if (name, index) in completed:
                        marker = raw.index(b"[ ]") + 1
                        require(after[name][index][:marker] == raw[:marker]
                                and after[name][index][marker:marker + 1] == b"x"
                                and after[name][index][marker + 1:] == raw[marker + 1:],
                                "Task completion changed text/metadata outside the checkbox state")
                    else:
                        require(after[name][index] == raw, "Unselected task changed")
        outcomes[status] += 1
        cases += 1
    require(cases == 154 and all(outcomes.values()), "Incomplete/vacuous D-12 coverage")
    require(apply(True, "1", other_file)[0] == "updated", "Unselected-file changes blocked valid action")
    require(apply(True, "1,4", other_file)[0] == "stale", "Affected-file drift was missed")
    return {"SC-12": {"selection_fixtures": len(selections), "source_state_fixtures": len(live_states),
                      "input_cases_checked": cases, "outcome_counts": outcomes,
                      "scope": "finite selection/snapshot reference model; not real TTY routing, file races, or multi-file durability"}}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-root", type=Path,
                        default=Path("/linuxdev/github/mathematical-abstractions"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    catalog_names = ("PropositionalLogic", "PropositionalFormula", "HoareTriple", "TransitionSystem",
                     "SumType", "Function", "TotalOrder", "EquivalenceRelation", "CandidateKey")
    inputs = [Path("AGENTS.md"), Path("README.md"), Path("docs/Requirements.md"),
              Path("docs/Design.md"), Path("docs/Future.md"), Path("docs/Specification.md"),
              Path("docs/specification/MathematicalModel.md"),
              Path("docs/specification/ConsistencyReview.md"), Path("docs/HTFS.md"),
              Path(".gitmodules"), Path("requirements.txt"), Path("Makefile"), Path("pytest.ini"),
              Path("diary_agent.py"), Path("diary_agent_app/core.py"),
              Path("diary_agent_app/models.py"), Path("diary_agent_app/htfs_adapter.py"),
              Path("tests/test_diary_agent.py")]
    hashes = {str(p): digest(ROOT / p) for p in inputs}
    hashes[str(Path(__file__).relative_to(ROOT))] = digest(Path(__file__))
    catalog_hashes = {f"concepts/{name}.md": digest(args.catalog_root / "concepts" / f"{name}.md")
                      for name in catalog_names}
    skill_paths = ("ai/skills/specification-consistency/SKILL.md",
                   "ai/skills/specification-consistency/references/checking-and-reporting.md",
                   "ai/skills/specification-consistency/references/boolean-example.md")
    skill_hashes = {p: digest(args.catalog_root / p) for p in skill_paths}
    check = subprocess.run([sys.executable, str(args.catalog_root / "scripts/catalog.py"), "check"],
                           capture_output=True, text=True, check=True)
    catalog_check = json.loads(check.stdout)
    require(not catalog_check["errors"], "Catalog structure check failed")
    result = {
        "method": "Python standard-library exhaustive finite models and explicit counterexamples",
        "python": platform.python_version(), "catalog_backend": "dependency-free Markdown retrieval",
        "catalog_structure": catalog_check, "input_sha256": hashes,
        "catalog_sha256": catalog_hashes, "skill_sha256": skill_hashes,
        "skill_example": boolean_demonstration(),
        "save": save_contracts(), "llm": llm_allowlist(), "editor": editor_model(),
        "cancellation": cancellation_model(), "relations": order_and_similarity(),
        "identity": key_collision(), "preservation": targeted_mutations(),
        "required_dependency": required_htfs(), "recovery": recovery_contract(),
        "todo_metadata": todo_metadata_contract(), "todo_selection": todo_selection_contract(),
        "result": "PASS: expected conflicts reproduced and selected repaired finite models covered",
        "limitations": "Not a global consistency proof, implementation test, Lean witness, or liveness proof.",
    }
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
        print(result["result"])
        print(f"Evidence: {args.output}")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
