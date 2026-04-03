#!/usr/bin/env python3
"""Offline diary agent powered by Ollama and prompt_toolkit."""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path
from typing import List, Sequence

from diary_agent_app import core, llm, ui
from diary_agent_app.htfs_adapter import HTFSAdapter
from diary_agent_app.models import AppConfig, DiaryEntryOption, DiarySection, PendingTask, SimilarTodoMatch

TODO_RE = core.TODO_RE
DATE_FMT = core.DATE_FMT
CONFIG_RELATIVE_PATH = core.CONFIG_RELATIVE_PATH
DIALOG_STYLE = ui.DIALOG_STYLE
SECTION_HEADING_RE = re.compile(r"^## (?P<time>\d{2}:\d{2})\s*$")


class DiaryAgent:
    def __init__(self, diary_dir: Path, model: str) -> None:
        self.diary_dir = diary_dir
        self.model = model

    def ensure_storage(self) -> None:
        self.diary_dir.mkdir(parents=True, exist_ok=True)

    def today_file(self, date: dt.date | None = None) -> Path:
        date = date or dt.date.today()
        return self.diary_dir / f"{date.strftime(DATE_FMT)}.md"

    def read_today_context(self) -> str:
        path = self.today_file()
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()

    def file_for_day_input(self, day_text: str) -> Path:
        normalized_date = parse_explicit_day_input(day_text)
        return self.diary_dir / f"{normalized_date}.md"

    def diary_files(self) -> list[Path]:
        return sorted(self.diary_dir.glob("*.md"))

    def entry_options(self) -> list[DiaryEntryOption]:
        options: list[DiaryEntryOption] = []
        for file_path in reversed(self.diary_files()):
            body = file_path.read_text(encoding="utf-8").rstrip()
            preview = next((line.strip() for line in body.splitlines() if line.strip()), "(empty entry)")
            title = format_entry_title(file_path.stem)
            search_text = build_entry_search_text(file_path.stem, title)
            options.append(
                DiaryEntryOption(
                    file_path=file_path,
                    title=title,
                    preview=preview,
                    search_text=search_text,
                )
            )
        return options

    def parse_day_sections(self, file_path: Path) -> list[DiarySection]:
        if not file_path.exists():
            return []

        sections: list[DiarySection] = []
        current_heading: str | None = None
        current_lines: list[str] = []

        def flush_section() -> None:
            if current_heading is None:
                return
            sections.append(
                DiarySection(
                    file_path=file_path,
                    heading=current_heading,
                    body="\n".join(current_lines).strip(),
                )
            )

        for raw_line in file_path.read_text(encoding="utf-8").splitlines():
            match = SECTION_HEADING_RE.fullmatch(raw_line.strip())
            if match:
                flush_section()
                current_heading = match.group("time")
                current_lines = []
                continue

            if current_heading is None:
                continue
            current_lines.append(raw_line.rstrip())

        flush_section()
        return sections

    def section_for_id(self, section_id: str) -> DiarySection | None:
        if "#" not in section_id:
            return None
        file_name, heading = section_id.split("#", 1)
        target = self.diary_dir / file_name
        for section in self.parse_day_sections(target):
            if section.heading == heading:
                return section
        return None

    def latest_section_for_file(self, file_path: Path) -> DiarySection | None:
        sections = self.parse_day_sections(file_path)
        return sections[-1] if sections else None

    def adjacent_entry(self, current_path: Path, step: int) -> tuple[str, str] | None:
        files = self.diary_files()
        try:
            index = files.index(current_path)
        except ValueError:
            return None

        next_index = index + step
        if next_index < 0 or next_index >= len(files):
            return None

        target = files[next_index]
        return target.name, target.read_text(encoding="utf-8").rstrip()

    def append_entry(self, entry: str) -> tuple[Path, bool]:
        path = self.today_file()
        existing = path.read_text(encoding="utf-8").rstrip() if path.exists() else ""
        new_lines = self.filter_new_entry_lines(entry, existing)

        if not new_lines:
            return path, False

        timestamp_heading = self.entry_timestamp_heading()
        timestamped_entry = "\n".join([timestamp_heading, "", "\n".join(new_lines)])
        pieces = [part for part in [existing, timestamped_entry] if part]
        path.write_text("\n\n".join(pieces) + "\n", encoding="utf-8")
        return path, True

    def prepare_rewrite_for_review(self, entry: str) -> str:
        existing = self.read_today_context()
        return "\n".join(self.filter_new_entry_lines(entry, existing)).strip()

    def append_entry_verbatim(self, entry: str) -> tuple[Path, bool]:
        path = self.today_file()
        rendered_entry = entry.rstrip()
        if not rendered_entry.strip():
            return path, False

        existing = path.read_text(encoding="utf-8").rstrip() if path.exists() else ""
        timestamped_entry = "\n".join([self.entry_timestamp_heading(), "", rendered_entry])
        pieces = [part for part in [existing, timestamped_entry] if part]
        path.write_text("\n\n".join(pieces) + "\n", encoding="utf-8")
        return path, True

    def extract_entry_lines(self, entry: str) -> list[str]:
        return [
            line.rstrip()
            for line in entry.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

    def filter_new_entry_lines(self, entry: str, existing: str) -> list[str]:
        existing_lines = self.extract_entry_lines(existing)
        existing_texts = [self.entry_line_text(line) for line in existing_lines]
        accepted_texts: list[str] = []
        new_lines: list[str] = []
        for raw_line in entry.strip().splitlines():
            line = raw_line.rstrip()
            if not line.strip():
                continue

            line_text = self.entry_line_text(line)
            if not line_text:
                continue

            if any(lines_are_redundant(line_text, text) for text in existing_texts):
                continue
            if any(lines_are_redundant(line_text, text) for text in accepted_texts):
                continue

            accepted_texts.append(line_text)
            new_lines.append(line)
        return new_lines

    def entry_line_text(self, line: str) -> str:
        if line.lstrip().startswith("#"):
            return ""
        match = TODO_RE.match(line)
        if match:
            return match.group("text").strip()
        normalized = line.lstrip()
        if normalized.startswith("- ") and not normalized.startswith("- ["):
            return normalized[2:].strip()
        return normalized.strip()

    def entry_timestamp_heading(self, now: dt.datetime | None = None) -> str:
        current = now or dt.datetime.now()
        return f"## {current.strftime('%H:%M')}"

    def open_todo_keys(self) -> set[str]:
        """Get normalized text for ALL todos (pending and completed)."""
        keys: set[str] = set()
        self.ensure_storage()
        for file_path in self.diary_dir.glob("*.md"):
            for line in file_path.read_text(encoding="utf-8").splitlines():
                match = TODO_RE.match(line)
                if match:
                    keys.add(normalize_todo_text(match.group("text")))
        return keys

    def dedupe_entry(self, entry: str) -> str:
        existing_todos = self.open_todo_keys()
        seen_new_todos: set[str] = set()
        filtered_lines: list[str] = []

        for line in entry.splitlines():
            match = TODO_RE.match(line)
            if not match or match.group("state") != " ":
                filtered_lines.append(line)
                continue

            todo_key = normalize_todo_text(match.group("text"))
            if todo_key in existing_todos or todo_key in seen_new_todos:
                continue

            seen_new_todos.add(todo_key)
            filtered_lines.append(line)

        return "\n".join(filtered_lines).strip()

    def review_entry_todos(self, entry: str, interactive: bool) -> tuple[str, list[SimilarTodoMatch]]:
        filtered_lines: list[str] = []
        flagged_matches: list[SimilarTodoMatch] = []

        for line in self.dedupe_entry(entry).splitlines():
            match = TODO_RE.match(line)
            if not match or match.group("state") != " ":
                filtered_lines.append(line)
                continue

            similar_match = self.find_similar_open_todo(match.group("text").strip())
            if similar_match is None:
                filtered_lines.append(line)
                continue

            if interactive and confirm_similar_todo_addition(similar_match):
                filtered_lines.append(line)
                continue

            if not interactive and confirm_similar_todo_addition_cli(similar_match):
                filtered_lines.append(line)
                continue

            flagged_matches.append(similar_match)

        return "\n".join(filtered_lines).strip(), flagged_matches

    def scan_pending_tasks(self) -> List[PendingTask]:
        tasks: list[PendingTask] = []
        self.ensure_storage()
        for file_path in sorted(self.diary_dir.glob("*.md")):
            for line_number, line in enumerate(
                file_path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                match = TODO_RE.match(line)
                if match and match.group("state") == " ":
                    tasks.append(
                        PendingTask(
                            file_path=file_path,
                            line_number=line_number,
                            text=match.group("text").strip(),
                        )
                    )
        return tasks

    def mark_tasks_complete(self, selected: Sequence[PendingTask]) -> int:
        by_file: dict[Path, list[PendingTask]] = {}
        for task in selected:
            by_file.setdefault(task.file_path, []).append(task)

        updates = 0
        for file_path, tasks in by_file.items():
            lines = file_path.read_text(encoding="utf-8").splitlines()
            line_numbers = {task.line_number for task in tasks}
            for index, line in enumerate(lines, start=1):
                if index not in line_numbers:
                    continue
                match = TODO_RE.match(line)
                if not match or match.group("state") != " ":
                    continue
                lines[index - 1] = f"{match.group('indent')}- [x] {match.group('text').strip()}"
                updates += 1
            file_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        return updates

    def search(self, query: str, limit: int = 6) -> list[tuple[Path, str, int]]:
        tokens = tokenize(query)
        if not tokens:
            return []

        results: list[tuple[Path, str, int]] = []
        for file_path in sorted(self.diary_dir.glob("*.md")):
            text = file_path.read_text(encoding="utf-8")
            for chunk in split_chunks(text):
                score = score_text(chunk, tokens)
                if score > 0:
                    results.append((file_path, chunk, score))

        results.sort(key=lambda item: item[2], reverse=True)
        return results[:limit]

    def find_similar_open_todo(self, candidate_text: str) -> SimilarTodoMatch | None:
        llm.require_ollama()

        candidate_key = normalize_todo_text(candidate_text)
        if not candidate_key:
            return None

        shortlist = shortlist_similar_tasks(candidate_text, self.scan_pending_tasks(), limit=5)
        for task in shortlist:
            if normalize_todo_text(task.text) == candidate_key:
                return SimilarTodoMatch(candidate_text=candidate_text, existing_task=task)

        for task in shortlist:
            if self._todos_are_semantically_similar(candidate_text, task.text):
                return SimilarTodoMatch(candidate_text=candidate_text, existing_task=task)
        return None

    def synthesize_entry(self, raw_update: str) -> str:
        return llm.synthesize_entry(
            model=self.model,
            raw_update=raw_update,
            today_context=self.read_today_context(),
            now=dt.datetime.now(),
        )

    def answer_query(self, query: str, matches: Sequence[tuple[Path, str, int]]) -> str:
        return llm.answer_query(model=self.model, query=query, matches=matches)

    def suggest_section_tags(self, section: DiarySection, available_tags: Sequence[str]) -> list[str]:
        return llm.suggest_section_tags(self.model, section.body, available_tags)

    def suggest_tags_for_text(self, text: str, available_tags: Sequence[str]) -> list[str]:
        if not self.model:
            return []
        return llm.suggest_section_tags(self.model, text, available_tags)

    def _todos_are_semantically_similar(self, candidate_text: str, existing_text: str) -> bool:
        return llm.todos_are_semantically_similar(
            model=self.model,
            candidate_text=candidate_text,
            existing_text=existing_text,
        )


def tokenize(text: str) -> list[str]:
    return core.tokenize(text)


def normalize_todo_text(text: str) -> str:
    return core.normalize_todo_text(text)


def lines_are_redundant(first: str, second: str) -> bool:
    first_key = normalize_todo_text(first)
    second_key = normalize_todo_text(second)
    if not first_key or not second_key:
        return False
    if first_key == second_key:
        return True

    first_tokens = first_key.split()
    second_tokens = second_key.split()
    if min(len(first_tokens), len(second_tokens)) < 4:
        return False

    first_words = set(first_tokens)
    second_words = set(second_tokens)
    overlap = len(first_words & second_words)
    shorter = min(len(first_words), len(second_words))
    if shorter == 0:
        return False

    overlap_ratio = overlap / shorter
    return (
        first_key in second_key
        or second_key in first_key
        or overlap_ratio >= 0.8
    )


def config_file_path() -> Path:
    return core.config_file_path(home=Path.home())


def parse_config_text(text: str) -> dict[str, str]:
    return core.parse_config_text(text)


def write_config(config_path: Path, diary_dir: Path, llm_model: str) -> None:
    core.write_config(config_path, diary_dir, llm_model)


def prompt_for_config_entries(config_path: Path) -> AppConfig:
    return core.prompt_for_config_entries(config_path, stdin=sys.stdin)


def load_or_initialize_config() -> AppConfig:
    return core.load_or_initialize_config(home=Path.home(), stdin=sys.stdin)


def shortlist_similar_tasks(
    candidate_text: str, tasks: Sequence[PendingTask], limit: int = 5
) -> list[PendingTask]:
    return core.shortlist_similar_tasks(candidate_text, tasks, limit=limit)


def split_chunks(text: str) -> Iterable[str]:
    return core.split_chunks(text)


def score_text(text: str, tokens: Sequence[str]) -> int:
    return core.score_text(text, tokens)


def overlap_count(text: str, tokens: Sequence[str]) -> int:
    return core.overlap_count(text, tokens)


def parse_explicit_day_input(day_text: str) -> str:
    normalized = day_text.strip()
    if not re.fullmatch(r"\d{2}_\d{2}_\d{4}", normalized):
        raise RuntimeError(
            "Invalid day format. Use dd_mm_yyyy, for example 05_03_2026."
        )
    return normalized


def format_entry_title(day_text: str) -> str:
    try:
        parsed = dt.datetime.strptime(day_text, DATE_FMT)
    except ValueError:
        return day_text
    return parsed.strftime("%d %b %Y")


def build_entry_search_text(day_text: str, title: str) -> str:
    variants = [
        day_text.lower(),
        day_text.replace("_", "").lower(),
        day_text.replace("_", " ").lower(),
        " ".join(reversed(day_text.split("_"))).lower(),
        title.lower(),
    ]
    return " ".join(dict.fromkeys(variants))


def resource_tags_for_specs(tags: Sequence[str]) -> list[str]:
    return [tag.rsplit("/", 1)[-1].strip() for tag in tags if tag.strip()]


def require_prompt_toolkit() -> None:
    ui.require_prompt_toolkit()


def status_toolbar(state: str) -> HTML:
    return ui.status_toolbar(state)


def prompt_for_task_completion(agent: DiaryAgent) -> None:
    ui.require_prompt_toolkit()
    tasks = agent.scan_pending_tasks()
    if not tasks:
        return

    values = [
        (
            task.key,
            f"{task.file_path.name}:{task.line_number}  {task.text}",
        )
        for task in tasks
    ]
    selected_keys = ui.checkboxlist_dialog(
        title="Pending TODOs",
        text="Select tasks to mark complete before adding today's update.",
        values=values,
        ok_text="Complete",
        cancel_text="Skip",
        style=DIALOG_STYLE,
    ).run()

    if not selected_keys:
        return

    selected = [task for task in tasks if task.key in selected_keys]
    updated = agent.mark_tasks_complete(selected)
    ui.message_dialog(
        title="Tasks Updated",
        text=f"Marked {updated} task(s) complete.",
        style=DIALOG_STYLE,
    ).run()


def confirm_similar_todo_addition(match: SimilarTodoMatch) -> bool:
    return ui.confirm_similar_todo_addition(match)


def confirm_similar_todo_addition_cli(match: SimilarTodoMatch) -> bool:
    return ui.confirm_similar_todo_addition_cli(match, stdin=sys.stdin)


def launch_editor(
    initial_text: str = "",
    state: str = "Capturing update",
    rewrite=None,
    suggest_tags=None,
) -> tuple[str, list[str]]:
    return ui.launch_editor(initial_text, state=state, rewrite=rewrite, suggest_tags=suggest_tags)


def prompt_for_section_tags(
    all_tags: Sequence[str],
    top_level_tags: Sequence[str],
    all_paths: Sequence[str],
    suggested_tags: Sequence[str] = [],
) -> list[str]:
    return ui.prompt_for_section_tags(all_tags, top_level_tags, all_paths, suggested_tags)


def show_diary_entry(
    title: str,
    body: str,
    previous_entry=None,
    next_entry=None,
    pick_entry=None,
) -> None:
    ui.show_diary_entry(
        title,
        body,
        previous_entry=previous_entry,
        next_entry=next_entry,
        pick_entry=pick_entry,
    )


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


def run_capture(agent: DiaryAgent, raw_text: str | None = None) -> int:
    agent.ensure_storage()
    if raw_text is None:
        adapter = get_htfs_adapter(agent.diary_dir)
        all_tags = adapter.list_tags()

        final_entry, suggested_tags = launch_editor(
            state="Capturing update",
            rewrite=lambda text: agent.prepare_rewrite_for_review(agent.synthesize_entry(text)),
            suggest_tags=lambda text: agent.suggest_tags_for_text(text, all_tags),
        )
        if not final_entry.strip():
            print("No update captured.")
            return 0

        path, appended = agent.append_entry_verbatim(final_entry)
        if appended:
            section = agent.latest_section_for_file(path)
            if section is not None:
                top_level_tags = adapter.get_top_level_tags()
                all_paths = adapter.get_all_tag_paths()
                selected_tags = prompt_for_section_tags(
                    all_tags, top_level_tags, all_paths, suggested_tags=suggested_tags
                )
                if selected_tags:
                    adapter.add_tags(selected_tags)
                    adapter.tag_section(section, resource_tags_for_specs(selected_tags))
            print(f"Updated {path.name}")
            print()
            print(final_entry.rstrip())
        else:
            print("No update captured.")
        return 0

    update_text = raw_text
    if not update_text.strip():
        print("No update captured.")
        return 0

    entry, skipped_matches = agent.review_entry_todos(
        agent.synthesize_entry(update_text),
        interactive=False,
    )
    if entry:
        path, appended = agent.append_entry(entry)
        if appended:
            print(f"Updated {path.name}")
            print()
            print(entry)
        else:
            print("This update has already been added.")
    else:
        print("This update has already been added.")
    for match in skipped_matches:
        print(
            "Skipped similar TODO:"
            f" {match.candidate_text} "
            f"(matches {match.existing_task.file_path.name}:{match.existing_task.line_number})"
        )
    return 0


def run_search(agent: DiaryAgent, query: str) -> int:
    agent.ensure_storage()
    matches = agent.search(query)
    answer = agent.answer_query(query, matches)
    print(answer)
    if matches:
        print("\nRelevant excerpts:")
        for path, snippet, _score in matches:
            print(f"\n[{path.name}]")
            print(snippet)
    return 0


def run_show_day(agent: DiaryAgent, day_text: str | None = None) -> int:
    agent.ensure_storage()
    path = agent.today_file() if day_text is None else agent.file_for_day_input(day_text)
    if not path.exists():
        print(f"No diary entry found for {path.stem}.")
        return 0

    body = path.read_text(encoding="utf-8").rstrip()
    try:
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
            pick_entry=lambda: agent.entry_options(),
        )
    except RuntimeError:
        print(f"[{path.name}]")
        print(body)
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
    adapter = get_htfs_adapter(agent.diary_dir)
    adapter.add_tags(tags)
    unsuccessful = adapter.tag_section(section, resource_tags_for_specs(tags))
    if unsuccessful:
        print("Some tags could not be applied:")
        for tag in unsuccessful:
            print(tag)
        return 1
    print(f"Tagged {section.section_id} with {', '.join(tags)}")
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Offline diary agent powered by Ollama.",
    )
    parser.add_argument(
        "--model",
        help="Optional Ollama model override. Otherwise the config file value is used.",
    )

    subparsers = parser.add_subparsers(dest="command")

    capture_parser = subparsers.add_parser(
        "capture",
        help="Open the editor and append a polished note to today's diary file.",
    )
    capture_parser.add_argument(
        "--text",
        help="Optional raw text to process without opening the editor.",
    )

    search_parser = subparsers.add_parser(
        "search",
        help="Search diary history and ask the local model to answer a question.",
    )
    search_parser.add_argument("query", help="Natural-language query to search for.")

    show_parser = subparsers.add_parser(
        "show",
        help="Show the diary entry for a particular day.",
    )
    show_parser.add_argument(
        "day",
        nargs="?",
        help="Day in dd_mm_yyyy format, for example 05_03_2026.",
    )

    todos_parser = subparsers.add_parser(
        "todos",
        help="List and manage pending todos.",
    )

    tags_parser = subparsers.add_parser(
        "tags",
        help="Show, apply, or suggest HTFS tags for a diary section.",
    )
    tags_subparsers = tags_parser.add_subparsers(dest="tags_command", required=True)

    tags_show_parser = tags_subparsers.add_parser(
        "show",
        help="Show HTFS tags for a specific diary section.",
    )
    tags_show_parser.add_argument("day", help="Day in dd_mm_yyyy format.")
    tags_show_parser.add_argument("time", nargs="?", help="Section time in HH:MM format.")

    tags_apply_parser = tags_subparsers.add_parser(
        "apply",
        help="Apply HTFS tags to a specific diary section.",
    )
    tags_apply_parser.add_argument("day", help="Day in dd_mm_yyyy format.")
    tags_apply_parser.add_argument("time", help="Section time in HH:MM format.")
    tags_apply_parser.add_argument("tags", nargs="+", help="HTFS tags to apply.")

    tags_suggest_parser = tags_subparsers.add_parser(
        "suggest",
        help="Suggest HTFS tags for a specific diary section using the configured model.",
    )
    tags_suggest_parser.add_argument("day", help="Day in dd_mm_yyyy format.")
    tags_suggest_parser.add_argument("time", help="Section time in HH:MM format.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    command = args.command or "capture"
    try:
        config = load_or_initialize_config()
        agent = DiaryAgent(
            diary_dir=config.diary_dir,
            model=args.model or config.llm_model,
        )
        if command == "capture":
            return run_capture(agent, raw_text=getattr(args, "text", None))
        if command == "search":
            return run_search(agent, query=args.query)
        if command == "show":
            return run_show_day(agent, day_text=args.day)
        if command == "todos":
            return run_todos(agent)
        if command == "tags":
            tags_command = args.tags_command
            if tags_command == "show":
                return run_tags_show(agent, args.day, args.time)
            if tags_command == "apply":
                return run_tags_apply(agent, args.day, args.time, args.tags)
            if tags_command == "suggest":
                return run_tags_suggest(agent, args.day, args.time)
        parser.error(f"Unknown command: {command}")
    except KeyboardInterrupt:
        print("\nAborted.")
        return 130
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1
    return 0


def run_todos(agent: DiaryAgent) -> int:
    """Show all pending todos and allow marking them complete via CLI or GUI."""
    agent.ensure_storage()
    tasks = agent.scan_pending_tasks()
    if not tasks:
        print("No pending todos found.")
        return 0

    try:
        ui.require_prompt_toolkit()
        prompt_for_task_completion(agent)
    except RuntimeError:
        # Fall back to CLI if prompt_toolkit not available
        print(f"Found {len(tasks)} pending todo(s):\n")
        for i, task in enumerate(tasks, 1):
            print(f"  {i}. {task.text}")
            print(f"     [{task.file_path.name}:{task.line_number}]\n")

        selected_indices = input("Enter numbers to mark complete (comma-separated), or press Enter to skip: ").strip()
        if not selected_indices:
            print("No tasks selected.")
            return 0

        try:
            selected_nums = {int(n.strip()) for n in selected_indices.split(",") if n.strip()}
            selected = [task for i, task in enumerate(tasks, 1) if i in selected_nums]
        except ValueError:
            print("Invalid input. No tasks updated.")
            return 1

        if not selected:
            print("No valid tasks selected.")
            return 0

        updated = agent.mark_tasks_complete(selected)
        print(f"Marked {updated} task(s) as complete.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
