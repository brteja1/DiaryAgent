"""Diary domain operations; command presentation lives in commands.py."""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter
from pathlib import Path
from collections.abc import Callable, Sequence

from . import core, llm
from .core import (
    TODO_RE,
    DATE_FMT,
    tokenize,
    normalize_todo_text,
    shortlist_similar_tasks,
    split_chunks,
    score_text,
    parse_explicit_day_input,
    format_entry_title,
    build_entry_search_text,
    resource_tags_for_specs,
    lines_are_redundant,
    todo_reference_date,
    normalize_todo_dates,
)
from .htfs_adapter import HTFSAdapter
from .markdown import DiaryDocument, read_markdown, write_markdown
from .models import (
    DiaryEntryOption,
    DiarySection,
    PendingTask,
    SearchResult,
    SimilarTodoMatch,
)

SECTION_ID_HEADING_RE = re.compile(r"^(?P<base>\d{2}:\d{2})(?::(?P<serial>[1-9]\d*))?$")


class DiaryAgent:
    def __init__(self, diary_dir: Path, model: str | None) -> None:
        self.diary_dir = diary_dir
        self.model = model.strip() if isinstance(model, str) and model.strip() else None

    @property
    def llm_enabled(self) -> bool:
        return self.model is not None

    def ensure_storage(self) -> None:
        self.diary_dir.mkdir(parents=True, exist_ok=True)

    def today_file(self, date: dt.date | None = None) -> Path:
        date = date or dt.date.today()
        return self.diary_dir / f"{date.strftime(DATE_FMT)}.md"

    def day_file(self, day_text: str | None = None) -> Path:
        if day_text is None:
            return self.today_file()
        return self.file_for_day_input(day_text)

    def read_day_context(self, day_text: str | None = None) -> str:
        return read_markdown(self.day_file(day_text)).strip()

    def file_for_day_input(self, day_text: str) -> Path:
        normalized_date = parse_explicit_day_input(day_text)
        return self.diary_dir / f"{normalized_date}.md"

    def diary_files(self) -> list[Path]:
        return sorted(path for path in self.diary_dir.glob("*.md") if path.is_file())

    def dated_diary_files(self) -> list[Path]:
        dated = [(core.date_for_diary_file(path), path) for path in self.diary_files()]
        return [
            path
            for day, path in sorted(
                (day, path) for day, path in dated if day is not None
            )
        ]

    def latest_diary_file(self) -> Path | None:
        files = self.dated_diary_files()
        return files[-1] if files else None

    def entry_options(self) -> list[DiaryEntryOption]:
        options: list[DiaryEntryOption] = []
        for file_path in reversed(self.dated_diary_files()):
            body = file_path.read_text(encoding="utf-8").rstrip()
            preview = next(
                (line.strip() for line in body.splitlines() if line.strip()),
                "(empty entry)",
            )
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
        return DiaryDocument.parse(read_markdown(file_path)).sections(file_path)

    def section_for_id(self, section_id: str) -> DiarySection | None:
        if "#" not in section_id:
            return None
        file_name, heading = section_id.split("#", 1)
        if Path(file_name).name != file_name:
            return None
        target = self.diary_dir / file_name
        document = DiaryDocument.parse(read_markdown(target))
        span = document.unique_section(heading)
        return (
            DiarySection(target, heading, document.body(span).strip()) if span else None
        )

    def latest_section_for_file(self, file_path: Path) -> DiarySection | None:
        sections = self.parse_day_sections(file_path)
        if not sections:
            return None
        latest = sections[-1]
        return (
            latest
            if sum(section.heading == latest.heading for section in sections) == 1
            else None
        )

    def get_section_tags(self, file_path: Path) -> dict[str, list[str]]:
        adapter = HTFSAdapter(self.diary_dir)
        sections = self.parse_day_sections(file_path)
        counts = Counter(section.heading for section in sections)
        return {
            section.heading: adapter.section_tags(section)
            for section in sections
            if counts[section.heading] == 1
        }

    def adjacent_entry(self, current_path: Path, step: int) -> tuple[str, str] | None:
        files = self.dated_diary_files()
        try:
            index = files.index(current_path)
        except ValueError:
            return None

        next_index = index + step
        if next_index < 0 or next_index >= len(files):
            return None

        target = files[next_index]
        return target.name, target.read_text(encoding="utf-8").rstrip()

    def append_entry(
        self, entry: str, day_text: str | None = None
    ) -> tuple[Path, bool]:
        """Save a final draft; transformations belong to proposal preparation."""
        return self.append_entry_verbatim(entry, day_text)

    def prepare_rewrite_for_review(
        self, entry: str, day_text: str | None = None
    ) -> str:
        entry = normalize_todo_dates(entry, todo_reference_date(day_text=day_text))
        existing = self.read_day_context(day_text)
        return "\n".join(self.filter_new_entry_lines(entry, existing)).strip()

    def append_entry_verbatim(
        self, entry: str, day_text: str | None = None
    ) -> tuple[Path, bool]:
        return self._append_body(self.day_file(day_text), entry)

    def _append_body(self, path: Path, body: str) -> tuple[Path, bool]:
        if not body.strip():
            return path, False
        existing = read_markdown(path)
        separator = ""
        if existing and not existing.endswith("\n\n"):
            separator = "\n" if existing.endswith("\n") else "\n\n"
        ending = "" if body.endswith("\n") else "\n"
        heading = self.unique_entry_timestamp_heading(path)
        write_markdown(path, f"{existing}{separator}{heading}\n\n{body}{ending}")
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

    def unique_entry_timestamp_heading(
        self,
        file_path: Path,
        now: dt.datetime | None = None,
    ) -> str:
        current = now or dt.datetime.now()
        base_heading = current.strftime("%H:%M")
        max_serial = 0

        for section in self.parse_day_sections(file_path):
            match = SECTION_ID_HEADING_RE.fullmatch(section.heading)
            if not match or match.group("base") != base_heading:
                continue
            serial = int(match.group("serial")) if match.group("serial") else 1
            max_serial = max(max_serial, serial)

        if max_serial == 0:
            return f"## {base_heading}"
        return f"## {base_heading}:{max_serial + 1}"

    def open_todo_keys(self) -> set[str]:
        return {normalize_todo_text(task.text) for task in self.scan_pending_tasks()}

    def dedupe_entry(self, entry: str) -> str:
        existing_todos = self.open_todo_keys()
        seen_new_todos: set[str] = set()
        filtered_lines: list[str] = []

        for line in entry.splitlines():
            match = TODO_RE.match(line)
            if not match or match.group("state") != " ":
                filtered_lines.append(line)
                continue

            todo_text, _due, _priority = core.parse_todo_details(match.group("text"))
            todo_key = normalize_todo_text(todo_text)
            if todo_key in existing_todos or todo_key in seen_new_todos:
                continue

            seen_new_todos.add(todo_key)
            filtered_lines.append(line)

        return "\n".join(filtered_lines).strip()

    def review_entry_todos(
        self, entry: str, confirm: Callable[[SimilarTodoMatch], bool] | None = None
    ) -> tuple[str, list[SimilarTodoMatch]]:
        filtered_lines: list[str] = []
        flagged_matches: list[SimilarTodoMatch] = []

        for line in self.dedupe_entry(entry).splitlines():
            match = TODO_RE.match(line)
            if not match or match.group("state") != " ":
                filtered_lines.append(line)
                continue

            candidate_text, _due, _priority = core.parse_todo_details(
                match.group("text").strip()
            )
            similar_match = self.find_similar_open_todo(candidate_text)
            if similar_match is None:
                filtered_lines.append(line)
                continue

            if confirm is not None and confirm(similar_match):
                filtered_lines.append(line)
                continue

            flagged_matches.append(similar_match)

        return "\n".join(filtered_lines).strip(), flagged_matches

    def scan_pending_tasks(self) -> list[PendingTask]:
        tasks: list[PendingTask] = []
        self.ensure_storage()
        for file_path in self.diary_files():
            snapshot = read_markdown(file_path)
            for line_number, line in enumerate(snapshot.splitlines(), start=1):
                match = TODO_RE.match(line)
                if match and match.group("state") == " ":
                    todo_text, due, priority = core.parse_todo_details(
                        match.group("text").strip()
                    )
                    tasks.append(
                        PendingTask(
                            file_path=file_path,
                            line_number=line_number,
                            text=todo_text,
                            due=due,
                            priority=priority,
                            source_snapshot=snapshot,
                        )
                    )
        return tasks

    def mark_tasks_complete(self, selected: Sequence[PendingTask]) -> int:
        """Validate the whole selection against its scan before writing any file."""
        by_file: dict[Path, list[PendingTask]] = {}
        for task in selected:
            by_file.setdefault(task.file_path, []).append(task)

        changes: dict[Path, str] = {}
        updates = 0
        for file_path, tasks in by_file.items():
            current = read_markdown(file_path)
            if any(
                task.source_snapshot is None or task.source_snapshot != current
                for task in tasks
            ):
                raise RuntimeError(
                    "TODO history changed; reselect tasks before completing them."
                )
            lines = current.splitlines(keepends=True)
            for number in {task.line_number for task in tasks}:
                if not 1 <= number <= len(lines):
                    raise RuntimeError("Invalid TODO selection; no tasks updated.")
                match = TODO_RE.match(lines[number - 1])
                if match is None or match.group("state") != " ":
                    raise RuntimeError(
                        "TODO history changed; reselect tasks before completing them."
                    )
                lines[number - 1] = core.todo_with_state(lines[number - 1], "x")
                updates += 1
            changes[file_path] = "".join(lines)
        for file_path, content in changes.items():
            write_markdown(file_path, content)
        return updates

    def toggle_todo(self, file_path: Path, line_number: int) -> str | None:
        """Toggle only the selected checkbox, preserving all other source bytes."""
        lines = read_markdown(file_path).splitlines(keepends=True)
        if not 1 <= line_number <= len(lines):
            return None
        match = TODO_RE.match(lines[line_number - 1])
        if match is None:
            return None
        state = " " if match.group("state") != " " else "x"
        lines[line_number - 1] = core.todo_with_state(lines[line_number - 1], state)
        content = "".join(lines)
        write_markdown(file_path, content)
        return content.rstrip()

    def update_section(
        self, file_path: Path, heading: str, new_body: str
    ) -> str | None:
        document = DiaryDocument.parse(read_markdown(file_path))
        updated = document.replace_body(heading, new_body)
        if updated is not None:
            write_markdown(file_path, updated)
        return updated.rstrip() if updated is not None else None

    def delete_section(self, file_path: Path, heading: str) -> str | None:
        document = DiaryDocument.parse(read_markdown(file_path))
        updated = document.delete_section(heading)
        if updated is None:
            return None
        section = DiarySection(file_path, heading, "")
        # Cross-store recovery remains the separately tracked PERSIST-01–05 target.
        HTFSAdapter(self.diary_dir).delete_section_resource(section)
        write_markdown(file_path, updated)
        return updated.rstrip()

    def set_section_tags(self, section: DiarySection, tags: list[str]) -> list[str]:
        """Clear and set new tags for a section."""
        resolved = self.section_for_id(section.section_id)
        if resolved is None:
            raise RuntimeError(f"No section found for {section.section_id}.")
        section = resolved
        adapter = HTFSAdapter(self.diary_dir)
        adapter.clear_section_tags(section)
        if tags:
            adapter.add_tags(tags)
            adapter.tag_section(section, resource_tags_for_specs(tags))
        return adapter.section_tags(section)

    def search(
        self,
        query: str,
        limit: int = 6,
        section_ids: set[str] | None = None,
    ) -> list[SearchResult]:
        tokens = tokenize(query)
        if not tokens:
            return []

        results: list[SearchResult] = []
        adapter = HTFSAdapter(self.diary_dir)
        allowed_sections = section_ids if section_ids is not None else None
        for file_path in self.diary_files():
            sections = self.parse_day_sections(file_path)
            if sections:
                for section in sections:
                    if (
                        allowed_sections is not None
                        and section.section_id not in allowed_sections
                    ):
                        continue
                    section_tags = tuple(adapter.section_tags(section))
                    tag_score = (
                        score_text(" ".join(section_tags), tokens)
                        if section_tags
                        else 0
                    )
                    section_chunks = list(split_chunks(section.body))
                    if not section_chunks and tag_score > 0:
                        results.append(
                            SearchResult(
                                file_path=file_path,
                                snippet=f"(tag match) {section.body}".strip(),
                                score=tag_score,
                                section_tags=section_tags,
                                section_id=section.section_id,
                            )
                        )
                        continue

                    for chunk in section_chunks:
                        content_score = score_text(chunk, tokens)
                        combined_score = content_score + tag_score
                        if combined_score > 0:
                            results.append(
                                SearchResult(
                                    file_path=file_path,
                                    snippet=chunk,
                                    score=combined_score,
                                    section_tags=section_tags,
                                    section_id=section.section_id,
                                )
                            )
                continue

            if allowed_sections is not None:
                continue
            text = file_path.read_text(encoding="utf-8")
            for chunk in split_chunks(text):
                score = score_text(chunk, tokens)
                if score > 0:
                    results.append(
                        SearchResult(
                            file_path=file_path,
                            snippet=chunk,
                            score=score,
                        )
                    )

        results.sort(key=lambda item: item.score, reverse=True)
        return results[:limit]

    def sections_for_ids(self, section_ids: set[str]) -> list[DiarySection]:
        if not section_ids:
            return []

        sections: list[DiarySection] = []
        for file_path in self.diary_files():
            for section in self.parse_day_sections(file_path):
                if section.section_id in section_ids:
                    sections.append(section)
        return sections

    def find_similar_open_todo(self, candidate_text: str) -> SimilarTodoMatch | None:
        if not self.llm_enabled:
            return None

        candidate_key = normalize_todo_text(candidate_text)
        if not candidate_key:
            return None

        shortlist = shortlist_similar_tasks(
            candidate_text, self.scan_pending_tasks(), limit=5
        )
        for task in shortlist:
            if normalize_todo_text(task.text) == candidate_key:
                return SimilarTodoMatch(
                    candidate_text=candidate_text, existing_task=task
                )

        for task in shortlist:
            if self._todos_are_semantically_similar(candidate_text, task.text):
                return SimilarTodoMatch(
                    candidate_text=candidate_text, existing_task=task
                )
        return None

    def synthesize_entry(self, raw_update: str, day_text: str | None = None) -> str:
        if not self.llm_enabled:
            return raw_update
        return llm.synthesize_entry(
            model=self.model,
            raw_update=raw_update,
            today_context=self.read_day_context(day_text),
            now=dt.datetime.now(),
        )

    def answer_query(self, query: str, matches: Sequence[SearchResult]) -> str:
        if not self.llm_enabled:
            raise RuntimeError("LLM model is not configured.")
        return llm.answer_query(model=self.model, query=query, matches=matches)

    def suggest_section_tags(
        self, section: DiarySection, available_tags: Sequence[str]
    ) -> list[str]:
        return self.suggest_tags_for_text(section.body, available_tags)

    def suggest_tags_for_text(
        self, text: str, available_tags: Sequence[str]
    ) -> list[str]:
        if not self.model:
            return []
        return llm.suggest_section_tags(self.model, text, available_tags)

    def tag_expression_from_natural_language(
        self,
        request: str,
        available_tags: Sequence[str],
    ) -> str:
        if not self.llm_enabled:
            return request.strip()
        return llm.tag_expression_from_natural_language(
            self.model, request, available_tags
        )

    def _todos_are_semantically_similar(
        self, candidate_text: str, existing_text: str
    ) -> bool:
        if not self.llm_enabled:
            return False
        return llm.todos_are_semantically_similar(
            model=self.model,
            candidate_text=candidate_text,
            existing_text=existing_text,
        )
