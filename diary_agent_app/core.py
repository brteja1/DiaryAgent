from __future__ import annotations

import os
import re
import sys
import datetime as dt
from pathlib import Path
from typing import Iterable, Sequence

from .models import AppConfig, PendingTask

TODO_RE = re.compile(r"^(?P<indent>\s*)- \[(?P<state>[ xX])\] (?P<text>.+?)\s*$")
TODO_METADATA_SUFFIX_RE = re.compile(
    r"\s*\[(?P<field>due|priority):\s*(?P<value>[^\]]+)\]\s*$",
    re.IGNORECASE,
)
TODO_DATE_REFERENCE_RE = re.compile(
    r"\b("
    r"today|tomorrow|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun"
    r")\b",
    re.IGNORECASE,
)
WEEKDAY_NAME_TO_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
WEEKDAY_ABBREVIATION_TO_NAME = {
    "mon": "monday",
    "tue": "tuesday",
    "tues": "tuesday",
    "wed": "wednesday",
    "thu": "thursday",
    "thur": "thursday",
    "thurs": "thursday",
    "fri": "friday",
    "sat": "saturday",
    "sun": "sunday",
}
DATE_FMT = "%d_%m_%Y"
CONFIG_RELATIVE_PATH = Path(".config") / "diary_agent" / "config.txt"
DEFAULT_HTFS_PATH_ENV = "DIARY_AGENT_HTFS_PATH"


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def normalize_todo_text(text: str) -> str:
    base_text, _due, _priority = parse_todo_details(text)
    return " ".join(tokenize(base_text))


def parse_todo_details(text: str) -> tuple[str, str | None, str | None]:
    base_text = text.strip()
    due: str | None = None
    priority: str | None = None

    while True:
        match = TODO_METADATA_SUFFIX_RE.search(base_text)
        if match is None:
            break

        field = match.group("field").lower()
        value = match.group("value").strip()
        base_text = base_text[: match.start()].rstrip()

        if field == "due":
            due = value
        elif field == "priority":
            priority = value

    return base_text, due, priority


def expand_todo_date_references(text: str, base_date: dt.date) -> str:
    def replace(match: re.Match[str]) -> str:
        token = match.group(0).lower()
        if token == "today":
            target_date = base_date
        elif token == "tomorrow":
            target_date = base_date + dt.timedelta(days=1)
        else:
            weekday_name = WEEKDAY_ABBREVIATION_TO_NAME.get(token, token)
            weekday_index = WEEKDAY_NAME_TO_INDEX[weekday_name]
            days_ahead = (weekday_index - base_date.weekday()) % 7
            target_date = base_date + dt.timedelta(days=days_ahead)
        return target_date.strftime(DATE_FMT)

    return TODO_DATE_REFERENCE_RE.sub(replace, text)


def render_todo_details(due: str | None = None, priority: str | None = None) -> str:
    details: list[str] = []
    if due:
        details.append(f"[due: {due}]")
    if priority:
        details.append(f"[priority: {priority}]")
    return " " + " ".join(details) if details else ""


def render_todo_line(
    indent: str,
    state: str,
    text: str,
    due: str | None = None,
    priority: str | None = None,
) -> str:
    return f"{indent}- [{state}] {text.strip()}{render_todo_details(due, priority)}"


def config_file_path(home: Path | None = None) -> Path:
    base = home if home is not None else Path.home()
    return base / CONFIG_RELATIVE_PATH


def default_htfs_path(home: Path | None = None, repo_root: Path | None = None) -> Path:
    env_value = os.environ.get(DEFAULT_HTFS_PATH_ENV, "").strip()
    if env_value:
        return Path(env_value).expanduser()

    repo_root_path = repo_root if repo_root is not None else Path(__file__).resolve().parents[1]
    sibling_checkout = repo_root_path.parent / "HTFS"
    if sibling_checkout.exists():
        return sibling_checkout

    base = home if home is not None else Path.home()
    return base / "HTFS"


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


def write_config(
    config_path: Path,
    diary_dir: Path,
    llm_model: str | None,
    htfs_path: Path,
) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"diary_path={diary_dir}", f"htfs_path={htfs_path}"]
    if llm_model and llm_model.strip():
        lines.insert(1, f"llm_model={llm_model.strip()}")
    config_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def prompt_for_config_entries(config_path: Path, stdin=None) -> AppConfig:
    stdin = stdin if stdin is not None else sys.stdin
    if not stdin.isatty():
        raise RuntimeError(
            f"Missing or invalid config at {config_path}. Create it with 'diary_path=', 'llm_model=', and 'htfs_path=' entries."
        )

    print(f"Config file required: {config_path}")
    print("Populate the diary storage location and HTFS project path to continue.")
    print("Ollama model is optional.")
    while True:
        diary_answer = input("Diary folder path: ").strip()
        if not diary_answer:
            print("Diary folder path is required.")
            continue
        model_answer = input("LLM model name (optional): ").strip()
        htfs_answer = input("HTFS project path: ").strip()
        if not htfs_answer:
            print("HTFS project path is required.")
            continue
        diary_dir = Path(diary_answer).expanduser()
        htfs_path = Path(htfs_answer).expanduser()
        write_config(config_path, diary_dir, model_answer, htfs_path)
        return AppConfig(
            diary_dir=diary_dir,
            llm_model=model_answer or None,
            htfs_path=htfs_path,
        )


def load_or_initialize_config(home: Path | None = None, stdin=None) -> AppConfig:
    config_path = config_file_path(home=home)
    if not config_path.exists():
        return prompt_for_config_entries(config_path, stdin=stdin)

    values = parse_config_text(config_path.read_text(encoding="utf-8"))
    diary_path = values.get("diary_path", "").strip()
    llm_model = values.get("llm_model", "").strip() or None
    htfs_path = values.get("htfs_path", "").strip()
    if not diary_path or not htfs_path:
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
