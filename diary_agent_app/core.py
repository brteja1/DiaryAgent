from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, Sequence

from .models import AppConfig, PendingTask

TODO_RE = re.compile(r"^(?P<indent>\s*)- \[(?P<state>[ xX])\] (?P<text>.+?)\s*$")
DATE_FMT = "%d_%m_%Y"
CONFIG_RELATIVE_PATH = Path(".config/diary_agent/config.txt")


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def normalize_todo_text(text: str) -> str:
    return " ".join(tokenize(text))


def config_file_path(home: Path | None = None) -> Path:
    base = home if home is not None else Path.home()
    return base / CONFIG_RELATIVE_PATH


def parse_config_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def write_config(config_path: Path, diary_dir: Path, llm_model: str, htfs_path: Path) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        f"diary_path={diary_dir}\nllm_model={llm_model}\nhtfs_path={htfs_path}\n",
        encoding="utf-8",
    )


def prompt_for_config_entries(config_path: Path, stdin=None) -> AppConfig:
    stdin = stdin if stdin is not None else sys.stdin
    if not stdin.isatty():
        raise RuntimeError(
            f"Missing or invalid config at {config_path}. Create it with 'diary_path=', 'llm_model=', and 'htfs_path=' entries."
        )

    print(f"Config file required: {config_path}")
    print("Populate the diary storage location, Ollama model, and HTFS project path to continue.")
    while True:
        diary_answer = input("Diary folder path: ").strip()
        if not diary_answer:
            print("Diary folder path is required.")
            continue
        model_answer = input("LLM model name: ").strip()
        if not model_answer:
            print("LLM model name is required.")
            continue
        htfs_answer = input("HTFS project path: ").strip()
        if not htfs_answer:
            print("HTFS project path is required.")
            continue
        diary_dir = Path(diary_answer).expanduser()
        htfs_path = Path(htfs_answer).expanduser()
        write_config(config_path, diary_dir, model_answer, htfs_path)
        return AppConfig(diary_dir=diary_dir, llm_model=model_answer, htfs_path=htfs_path)


def load_or_initialize_config(home: Path | None = None, stdin=None) -> AppConfig:
    config_path = config_file_path(home=home)
    if not config_path.exists():
        return prompt_for_config_entries(config_path, stdin=stdin)

    values = parse_config_text(config_path.read_text(encoding="utf-8"))
    diary_path = values.get("diary_path", "").strip()
    llm_model = values.get("llm_model", "").strip()
    htfs_path = values.get("htfs_path", "").strip()
    if not diary_path or not llm_model or not htfs_path:
        return prompt_for_config_entries(config_path, stdin=stdin)

    return AppConfig(
        diary_dir=Path(diary_path).expanduser(),
        llm_model=llm_model,
        htfs_path=Path(htfs_path).expanduser(),
    )


def shortlist_similar_tasks(
    candidate_text: str, tasks: Sequence[PendingTask], limit: int = 5
) -> list[PendingTask]:
    scored: list[tuple[int, PendingTask]] = []
    candidate_key = normalize_todo_text(candidate_text)
    candidate_words = set(candidate_key.split())

    for task in tasks:
        task_key = normalize_todo_text(task.text)
        task_words = set(task_key.split())
        overlap = len(candidate_words & task_words)
        substring_bonus = 3 if candidate_key and (candidate_key in task_key or task_key in candidate_key) else 0
        score = overlap + substring_bonus
        if score > 0:
            scored.append((score, task))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [task for _score, task in scored[:limit]]


def split_chunks(text: str) -> Iterable[str]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    if blocks:
        return blocks
    return [line.strip() for line in text.splitlines() if line.strip()]


def overlap_count(text: str, tokens: Sequence[str]) -> int:
    words = set(tokenize(text))
    return sum(1 for token in tokens if token in words)


def score_text(text: str, tokens: Sequence[str]) -> int:
    lowered = text.lower()
    return sum(3 if token in lowered else 0 for token in tokens) + overlap_count(text, tokens)
