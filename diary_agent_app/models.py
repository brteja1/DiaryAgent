from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .todo_metadata import PRIORITIES, field_status, parsed_due_date


@dataclass(frozen=True)
class PendingTask:
    file_path: Path
    line_number: int
    text: str
    due: str | None = None
    priority: str | None = None
    source_snapshot: str | None = field(default=None, repr=False, compare=False)

    @property
    def key(self) -> str:
        return f"{self.file_path}:{self.line_number}"

    @property
    def due_status(self) -> str:
        return field_status(self.due, parsed_due_date(self.due) is not None)

    @property
    def priority_status(self) -> str:
        return field_status(self.priority, self.priority in PRIORITIES)

    @property
    def display_text(self) -> str:
        parts = [self.text]
        if self.due is not None:
            suffix = " (unvalidated)" if self.due_status == "unvalidated" else ""
            parts.append(f"[due: {self.due}]{suffix}")
        if self.priority is not None:
            suffix = " (unvalidated)" if self.priority_status == "unvalidated" else ""
            parts.append(f"[priority: {self.priority}]{suffix}")
        return " ".join(parts)


@dataclass(frozen=True)
class SimilarTodoMatch:
    candidate_text: str
    existing_task: PendingTask


@dataclass(frozen=True)
class AppConfig:
    diary_dir: Path
    llm_model: str | None


@dataclass(frozen=True)
class DiaryEntryOption:
    file_path: Path
    title: str
    preview: str
    search_text: str


@dataclass(frozen=True)
class DiarySection:
    file_path: Path
    heading: str
    body: str

    @property
    def section_id(self) -> str:
        return f"{self.file_path.name}#{self.heading}"


@dataclass(frozen=True)
class SearchResult:
    file_path: Path
    snippet: str
    score: int
    section_tags: tuple[str, ...] = ()
    section_id: str | None = None
