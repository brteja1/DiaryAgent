from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PendingTask:
    file_path: Path
    line_number: int
    text: str

    @property
    def key(self) -> str:
        return f"{self.file_path}:{self.line_number}"


@dataclass(frozen=True)
class SimilarTodoMatch:
    candidate_text: str
    existing_task: PendingTask


@dataclass(frozen=True)
class AppConfig:
    diary_dir: Path
    llm_model: str
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
