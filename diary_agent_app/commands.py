"""User-facing workflows: domain calls, terminal interaction and output."""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from collections.abc import Sequence

from . import ui
from .core import (
    format_diary_date,
    parse_explicit_day_input,
    format_entry_title,
)
from .models import DiarySection, PendingTask, SearchResult
from .service import DiaryAgent
from .htfs_adapter import HTFSAdapter
from .persistence import OperationJournal, PersistenceError
from .ui import (
    launch_editor,
    prompt_for_section_tags,
    confirm_show_latest_entry_cli,
    prompt_yes_no,
)
from .viewer import show_diary_entry


def prompt_for_task_completion(
    agent: DiaryAgent, tasks: Sequence[PendingTask] | None = None
) -> None:
    tasks = agent.scan_pending_tasks() if tasks is None else tasks
    if not tasks:
        return
    selected = ui.select_pending_tasks(tasks)
    if selected:
        ui.show_completed_task_count(agent.mark_tasks_complete(selected))


def confirm_show_latest_entry(requested_title: str, latest_title: str) -> bool:
    try:
        return ui.confirm_show_latest_entry(requested_title, latest_title)
    except RuntimeError:
        return confirm_show_latest_entry_cli(requested_title, latest_title)


def resolve_section(agent: DiaryAgent, day_text: str, time_text: str) -> DiarySection:
    path = agent.file_for_day_input(day_text)
    section = agent.section_for_id(f"{path.name}#{time_text}")
    if section is None:
        raise RuntimeError(f"No section found for {path.name} at {time_text}.")
    return section


def get_htfs_adapter(diary_dir: Path) -> HTFSAdapter:
    adapter = HTFSAdapter(diary_dir)
    adapter.ensure_initialized()
    return adapter


def capture_info_message(day_text: str | None = None) -> str:
    normalized_day = (
        format_diary_date(dt.date.today())
        if day_text is None
        else parse_explicit_day_input(day_text)
    )
    return f"Capturing update for {format_entry_title(normalized_day)}"


def _print_saved_capture(path: Path, body: str) -> None:
    print(f"Updated {path.name}")
    print()
    print(body.rstrip())


def run_capture(
    agent: DiaryAgent, raw_text: str | None = None, day_text: str | None = None
) -> int:
    agent.ensure_storage()
    agent.day_file(day_text)  # Validate the target before opening any editor.
    if raw_text is None:
        return _capture_in_editor(agent, day_text)
    return _capture_text(agent, raw_text, day_text)


def _capture_in_editor(agent: DiaryAgent, day_text: str | None) -> int:
    adapter = get_htfs_adapter(agent.diary_dir)
    all_tags = adapter.list_tags()

    def rewrite(text: str) -> str:
        candidate = agent.synthesize_entry(text, day_text=day_text)
        return agent.prepare_rewrite_for_review(
            candidate, day_text=day_text, original=text
        )

    final_entry, suggested_tags = launch_editor(
        state="Capturing update",
        info_message=capture_info_message(day_text),
        rewrite=rewrite if agent.llm_enabled else None,
        suggest_tags=(
            (lambda text: agent.suggest_tags_for_text(text, all_tags))
            if agent.llm_enabled
            else None
        ),
    )
    path, appended = agent.append_entry_verbatim(final_entry, day_text=day_text)
    if not appended:
        print("No update captured.")
        return 0
    _print_saved_capture(path, final_entry)
    try:
        section = agent.latest_section_for_file(path)
        if section is not None:
            selected = prompt_for_section_tags(
                all_tags,
                adapter.get_top_level_tags(),
                adapter.get_all_tag_paths(),
                suggested_tags=suggested_tags,
            )
            if selected:
                agent.set_section_tags(section, selected, additive=True)
    except PersistenceError as exc:
        print(f"Note saved; tagging pending. {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(
            f"Note saved; tagging could not start. Capture operation {agent.last_operation_id}: {exc}",
            file=sys.stderr,
        )
        return 1
    return 0


def _capture_text(agent: DiaryAgent, text: str, day_text: str | None) -> int:
    if not text.strip():
        print("No update captured.")
        return 0
    entry = text
    if agent.llm_enabled and sys.stdin.isatty():
        try:
            candidate = agent.synthesize_entry(text, day_text=day_text)
            candidate = agent.prepare_rewrite_for_review(
                candidate, day_text=day_text, original=text
            )
            candidate, skipped = agent.review_entry_todos(candidate)
            if candidate != text:
                print("Proposed content (empty means no append):\n")
                print(candidate)
                if prompt_yes_no("Save this complete proposal?"):
                    entry = candidate
                    for match in skipped:
                        task = match.existing_task
                        print(
                            f"Accepted omission of similar TODO: {match.candidate_text} "
                            f"(matches {task.file_path.name}:{task.line_number})"
                        )
                else:
                    print("Proposal declined; saving original text.")
        except RuntimeError as exc:
            print(
                f"Rewrite unavailable; saving original text. ({exc})", file=sys.stderr
            )
    elif agent.llm_enabled:
        print("Unattended capture: saving original text without LLM changes.")
    path, appended = agent.append_entry_verbatim(entry, day_text=day_text)
    if appended:
        _print_saved_capture(path, entry)
    else:
        print("No update captured.")
    return 0


def _search_result_label(match: SearchResult) -> str:
    if match.section_id:
        return f"{match.file_path.name}#{match.section_id.split('#', 1)[1]}"
    return match.file_path.name


def _print_search_results(matches: Sequence[SearchResult], heading: str) -> None:
    if not matches:
        print("No relevant diary history found.")
        return
    print(heading)
    for match in matches:
        tag_suffix = (
            f" [tags: {', '.join(match.section_tags)}]" if match.section_tags else ""
        )
        print(f"\n[{_search_result_label(match)}]{tag_suffix}")
        print(match.snippet)


def _resolve_tag_expression(
    agent: DiaryAgent, adapter: HTFSAdapter, raw_tag_filter: str
) -> str:
    normalized = raw_tag_filter.strip()
    if not normalized:
        return ""
    if any(operator in normalized for operator in "&|~()"):
        return normalized
    available_tags = adapter.get_all_tag_paths()
    return agent.tag_expression_from_natural_language(normalized, available_tags)


def _section_ids_for_tag_expression(
    agent: DiaryAgent,
    adapter: HTFSAdapter,
    tag_expression: str,
) -> set[str]:
    section_ids: set[str] = set()
    for resource_path in adapter.query_resource_paths(tag_expression):
        section = adapter.load_section_by_resource_path(agent, resource_path)
        if section is not None:
            section_ids.add(section.section_id)
    return section_ids


def run_search(
    agent: DiaryAgent, query: str | None = None, tag_filter: str | None = None
) -> int:
    agent.ensure_storage()
    if query is not None and not query.strip():
        query = None
    if tag_filter is not None and not tag_filter.strip():
        tag_filter = None
    section_ids: set[str] | None = None
    tag_expression: str | None = None
    adapter: HTFSAdapter | None = None

    if tag_filter:
        adapter = get_htfs_adapter(agent.diary_dir)
        tag_expression = _resolve_tag_expression(agent, adapter, tag_filter)
        if not tag_expression:
            print("No diary sections matched the provided tag filter.")
            return 0
        try:
            section_ids = _section_ids_for_tag_expression(
                agent, adapter, tag_expression
            )
        except RuntimeError as exc:
            print(f"Tag search failed: {exc}", file=sys.stderr)
            return 1
        if not section_ids:
            print("No diary sections matched the provided tag filter.")
            return 0

    if query is None:
        if section_ids is None:
            print("No search query or tag filter provided.")
            return 1
        assert adapter is not None
        tagged_sections = agent.sections_for_ids(section_ids)
        tag_results: list[SearchResult] = []
        for section in tagged_sections:
            section_tags = tuple(adapter.section_tags(section))
            tag_results.append(
                SearchResult(
                    file_path=section.file_path,
                    snippet=section.body.strip() or "(empty section)",
                    score=1,
                    section_tags=section_tags,
                    section_id=section.section_id,
                )
            )
        _print_search_results(tag_results, "Tag search results:")
        return 0

    matches = agent.search(query, section_ids=section_ids)
    if not agent.llm_enabled:
        if section_ids is not None:
            print(
                "LLM model is not configured; showing basic text search results for the provided tag filter.",
                file=sys.stderr,
            )
        else:
            print(
                "LLM model is not configured; showing basic text search results.",
                file=sys.stderr,
            )
        _print_search_results(matches, "Basic text search results:")
        return 0
    try:
        answer = agent.answer_query(query, matches)
    except RuntimeError as exc:
        warning = "Warning: LLM search is unavailable; showing basic text search results instead."
        if str(exc):
            warning = f"{warning} ({exc})"
        print(warning, file=sys.stderr)
        _print_search_results(matches, "Basic text search results:")
        return 0

    print(answer)
    if matches:
        print("\nRelevant excerpts:")
        for match in matches:
            tag_suffix = (
                f" [tags: {', '.join(match.section_tags)}]"
                if match.section_tags
                else ""
            )
            print(f"\n[{_search_result_label(match)}]{tag_suffix}")
            print(match.snippet)
    return 0


def run_show_day(agent: DiaryAgent, day_text: str | None = None) -> int:
    agent.ensure_storage()
    path = (
        agent.today_file() if day_text is None else agent.file_for_day_input(day_text)
    )
    if not path.exists():
        if day_text is None:
            latest_path = agent.latest_diary_file()
            if latest_path is not None and confirm_show_latest_entry(
                path.stem, latest_path.stem
            ):
                path = latest_path
            else:
                print(f"No diary entry found for {path.stem}.")
                return 0
        else:
            print(f"No diary entry found for {path.stem}.")
            return 0

    if not path.exists():
        print(f"No diary entry found for {path.stem}.")
        return 0

    body = path.read_text(encoding="utf-8").rstrip()
    adapter = get_htfs_adapter(agent.diary_dir)
    try:
        ui.require_prompt_toolkit()
    except RuntimeError:
        print(f"[{path.name}]")
        print(body)
        return 0
    show_suggest_tags = (
        (lambda text: agent.suggest_tags_for_text(text, adapter.list_tags()))
        if agent.llm_enabled
        else None
    )
    show_diary_entry(
        path.name,
        body,
        previous_entry=lambda current_title: agent.adjacent_entry(
            agent.diary_dir / current_title,
            -1,
        ),
        next_entry=lambda current_title: agent.adjacent_entry(
            agent.diary_dir / current_title,
            1,
        ),
        pick_entry=agent.entry_options,
        get_tags=lambda current_title: agent.get_section_tags(
            agent.diary_dir / current_title
        ),
        toggle_todo=lambda current_title, line: agent.toggle_todo(
            agent.diary_dir / current_title, line
        ),
        update_section=lambda current_title, heading, body: agent.update_section(
            agent.diary_dir / current_title, heading, body
        ),
        set_tags=lambda current_title, heading, tags: agent.set_section_tags(
            DiarySection(agent.diary_dir / current_title, heading, ""), tags
        ),
        get_all_tags=lambda: (
            adapter.list_tags(),
            adapter.get_top_level_tags(),
            adapter.get_all_tag_paths(),
        ),
        suggest_tags=show_suggest_tags,
        delete_section=lambda current_title, heading: agent.delete_section(
            agent.diary_dir / current_title,
            heading,
        ),
        reload_entry=lambda current_title: (agent.diary_dir / current_title)
        .read_text(encoding="utf-8")
        .rstrip(),
    )
    return 0


def run_tags_show(agent: DiaryAgent, day_text: str, time_text: str | None) -> int:
    adapter = get_htfs_adapter(agent.diary_dir)
    if time_text:
        section = resolve_section(agent, day_text, time_text)
        tags = adapter.section_tags(section)
        if not tags:
            print(f"No HTFS tags found for {section.section_id}.")
            return 0
        print(f"[{section.section_id}]")
        for tag in tags:
            print(tag)
    else:
        path = agent.file_for_day_input(day_text)
        sections = agent.parse_day_sections(path)
        if not sections:
            print(f"No sections found for {path.name}.")
            return 0

        found_any = False
        for section in sections:
            tags = adapter.section_tags(section)
            if tags:
                found_any = True
                print(f"[{section.section_id}]")
                for tag in tags:
                    print(f"  {tag}")
        if not found_any:
            print(f"No HTFS tags found for any section in {path.name}.")
    return 0


def run_tags_apply(
    agent: DiaryAgent,
    day_text: str,
    time_text: str,
    tags: Sequence[str],
) -> int:
    section = resolve_section(agent, day_text, time_text)
    agent.set_section_tags(section, list(tags), additive=True)
    print(f"Tagged {section.section_id} with {', '.join(tags)}")
    return 0


def run_recovery(
    agent: DiaryAgent,
    action: str,
    identifier: str | None = None,
    *,
    include_complete: bool = False,
    reason: str = "",
    yes: bool = False,
) -> int:
    journal = OperationJournal(agent.diary_dir)
    if action == "list":
        operations = journal.list(include_complete)
        if not operations:
            print("No recovery operations found.")
        for operation in operations:
            print(f"{operation.id}  {operation.kind}  {operation.status}")
        return 0
    if action == "show":
        from dataclasses import asdict
        import json

        print(
            json.dumps(asdict(journal.load(identifier)), indent=2, ensure_ascii=False)
        )
        return 0
    if action == "resolve":
        if not yes and (
            not sys.stdin.isatty()
            or not prompt_yes_no(
                "Resolve this operation without retrying its metadata changes?"
            )
        ):
            print("Resolution cancelled; operation retained.")
            return 1
        operation = journal.resolve(identifier, reason)
    else:
        operation = agent.persistence().retry(identifier)
    print(f"Operation {operation.id}: {operation.status}")
    return 0


def run_tags_suggest(agent: DiaryAgent, day_text: str, time_text: str) -> int:
    section = resolve_section(agent, day_text, time_text)
    adapter = get_htfs_adapter(agent.diary_dir)
    available_tags = adapter.list_tags()
    if not available_tags:
        print("No HTFS tags are available to suggest from.")
        return 0
    suggestions = agent.suggest_section_tags(section, available_tags)
    if not suggestions:
        print(f"No tag suggestions for {section.section_id}.")
        return 0
    print(f"[{section.section_id}]")
    for tag in suggestions:
        print(tag)
    return 0


def run_tags_list(agent: DiaryAgent) -> int:
    adapter = get_htfs_adapter(agent.diary_dir)
    tags = adapter.list_tags()
    if not tags:
        print("No HTFS tags found.")
        return 0
    for tag in tags:
        print(tag)
    return 0


def run_tags_tree(agent: DiaryAgent, root_tag: str | None = None) -> int:
    adapter = get_htfs_adapter(agent.diary_dir)
    available_tags = set(adapter.list_tags())
    if root_tag is not None and root_tag not in available_tags:
        print(f"Tag not found: {root_tag}")
        return 1

    roots = [root_tag] if root_tag else adapter.get_top_level_tags()
    if not roots:
        print("No HTFS tags found.")
        return 0

    visited: set[str] = set()

    def render(tag_name: str, indent: int = 0) -> None:
        print(f"{'  ' * indent}{tag_name}")
        if tag_name in visited:
            return
        visited.add(tag_name)
        for child_tag in adapter.get_child_tags(tag_name):
            render(child_tag, indent + 1)

    for tag_name in roots:
        render(tag_name)
    return 0


def run_tags_delete(
    agent: DiaryAgent,
    tag_name: str,
    descendants: bool | None = None,
    only_unused: bool | None = None,
    yes: bool = False,
) -> int:
    adapter = get_htfs_adapter(agent.diary_dir)
    available_tags = adapter.list_tags()
    if tag_name not in available_tags:
        print(f"Tag not found: {tag_name}")
        return 1

    if descendants is None:
        descendants = (
            prompt_yes_no(
                f"Delete descendant tags under {tag_name} too?",
                default=False,
            )
            if sys.stdin.isatty()
            else False
        )

    if only_unused is None:
        only_unused = (
            prompt_yes_no(
                "Only delete tags that are unused?",
                default=False,
            )
            if sys.stdin.isatty()
            else False
        )

    delete_order = adapter.get_tag_descendants(tag_name) if descendants else []
    delete_order.append(tag_name)

    if only_unused:
        used_tags = [name for name in delete_order if adapter.tag_has_usage(name)]
        if used_tags:
            print(
                "Cannot delete tags that are still used by diary resources:"
                f" {', '.join(used_tags)}"
            )
            return 1

    if not yes and not sys.stdin.isatty():
        print("Refusing to delete tags without a TTY. Re-run with --yes to confirm.")
        return 1

    summary = f"Delete tag {tag_name}"
    if descendants:
        summary += f" and {len(delete_order) - 1} descendant(s)"
    if not yes and not prompt_yes_no(summary, default=False):
        print("Aborted.")
        return 0

    agent.delete_taxonomy_tags(delete_order)
    print(f"Deleted {len(delete_order)} tag(s): {', '.join(delete_order)}")
    return 0


def run_todos(agent: DiaryAgent) -> int:
    """Show all pending todos and allow marking them complete via CLI or GUI."""
    agent.ensure_storage()
    tasks = agent.scan_pending_tasks()
    if not tasks:
        print("No pending todos found.")
        return 0

    if not sys.stdin.isatty():
        for task in tasks:
            print(f"{task.file_path.name}:{task.line_number}  {task.display_text}")
        return 0

    try:
        ui.require_prompt_toolkit()
    except RuntimeError:
        # Fall back to CLI if prompt_toolkit not available
        print(f"Found {len(tasks)} pending todo(s):\n")
        for i, task in enumerate(tasks, 1):
            print(f"  {i}. {task.display_text}")
            print(f"     [{task.file_path.name}:{task.line_number}]\n")

        selected_indices = input(
            "Enter numbers to mark complete (comma-separated), or press Enter to skip: "
        ).strip()
        if not selected_indices:
            print("No tasks selected.")
            return 0

        try:
            selected_nums = {int(n.strip()) for n in selected_indices.split(",")}
            if not all(1 <= number <= len(tasks) for number in selected_nums):
                raise ValueError("Selection outside the displayed tasks")
            selected = [task for i, task in enumerate(tasks, 1) if i in selected_nums]
        except ValueError:
            print("Invalid input. No tasks updated.")
            return 1

        if not selected:
            print("No valid tasks selected.")
            return 0

        updated = agent.mark_tasks_complete(selected)
        print(f"Marked {updated} task(s) as complete.")
    else:
        prompt_for_task_completion(agent, tasks)

    return 0
