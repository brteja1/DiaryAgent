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
from diary_agent_app.models import AppConfig, PendingTask, SimilarTodoMatch

TODO_RE = core.TODO_RE
DATE_FMT = core.DATE_FMT
CONFIG_RELATIVE_PATH = core.CONFIG_RELATIVE_PATH
DIALOG_STYLE = ui.DIALOG_STYLE


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
        existing_lines = self.extract_entry_lines(existing)
        existing_texts = [self.entry_line_text(line) for line in existing_lines]
        accepted_texts: list[str] = []
        new_lines: list[str] = []
        for line in entry.strip().splitlines():
            line = line.strip()
            if not line:
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

        if not new_lines:
            return path, False

        pieces = [part for part in [existing, "\n".join(new_lines)] if part]
        path.write_text("\n\n".join(pieces) + "\n", encoding="utf-8")
        return path, True

    def extract_entry_lines(self, entry: str) -> list[str]:
        return [line.strip() for line in entry.splitlines() if line.strip()]

    def entry_line_text(self, line: str) -> str:
        match = TODO_RE.match(line)
        if match:
            return match.group("text").strip()
        if line.startswith("- ") and not line.startswith("- ["):
            return line[2:].strip()
        return line.strip()

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

    def get_all_entry_keys(self, entry: str) -> set[str]:
        """Extract normalized keys from an entry (both todos and regular notes)."""
        keys: set[str] = set()
        for line in entry.splitlines():
            line = line.strip()
            match = TODO_RE.match(line)
            if match:
                keys.add(normalize_todo_text(match.group("text")))
            elif line.startswith("- ") and not line.startswith("- ["):
                text = line[2:].strip()
                if text:
                    keys.add(normalize_todo_text(text))
            elif line:
                keys.add(normalize_todo_text(line))
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

    def _todos_are_semantically_similar(self, candidate_text: str, existing_text: str) -> bool:
        return llm.todos_are_semantically_similar(
            model=self.model,
            candidate_text=candidate_text,
            existing_text=existing_text,
        )

    def _require_ollama(self) -> None:
        llm.require_ollama()


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


def detect_todo_candidates(raw_update: str) -> list[str]:
    return core.detect_todo_candidates(raw_update)


def parse_explicit_day_input(day_text: str) -> str:
    normalized = day_text.strip()
    if not re.fullmatch(r"\d{2}_\d{2}_\d{4}", normalized):
        raise RuntimeError(
            "Invalid day format. Use dd_mm_yyyy, for example 05_03_2026."
        )
    return normalized


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


def launch_editor(initial_text: str = "") -> str:
    return ui.launch_editor(initial_text)


def show_diary_entry(
    title: str,
    body: str,
    previous_entry=None,
    next_entry=None,
) -> None:
    ui.show_diary_entry(
        title,
        body,
        previous_entry=previous_entry,
        next_entry=next_entry,
    )


def run_capture(agent: DiaryAgent, raw_text: str | None = None) -> int:
    agent.ensure_storage()
    update_text = raw_text if raw_text is not None else launch_editor()
    if update_text.strip():
        entry, skipped_matches = agent.review_entry_todos(
            agent.synthesize_entry(update_text),
            interactive=raw_text is None,
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
    else:
        print("No update captured.")

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
        )
    except RuntimeError:
        print(f"[{path.name}]")
        print(body)
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
