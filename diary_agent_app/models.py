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
