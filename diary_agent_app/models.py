from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PendingTask:
    file_path: Path
    line_number: int
    text: str
    due: str | None = None
    priority: str | None = None

    @property
    def key(self) -> str:
        return f"{self.file_path}:{self.line_number}"

    @property
    def display_text(self) -> str:
        parts = [self.text]
        if self.due:
            parts.append(f"[due: {self.due}]")
        if self.priority:
            parts.append(f"[priority: {self.priority}]")
        return " ".join(parts)


@dataclass(frozen=True)
class SimilarTodoMatch:
    candidate_text: str
    existing_task: PendingTask


@dataclass(frozen=True)
class AppConfig:
    diary_dir: Path
    llm_model: str | None
    htfs_path: Path


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
