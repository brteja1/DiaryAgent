from __future__ import annotations

import re
import sys
import datetime as dt
from pathlib import Path
from typing import Iterable, Sequence

from .models import AppConfig, PendingTask
from .todo_metadata import parsed_due_date

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


def format_diary_date(day: dt.date) -> str:
    return f"{day.day:02d}_{day.month:02d}_{day.year:04d}"


def validate_generated_todo_metadata(entry: str, original: str = "") -> None:
    """Reject invalid *new* model fields, retaining preexisting raw fields.

    This guard is only for proposal generation. It never validates/rejects a
    verbatim save. Original legacy/unvalidated fields remain user-controlled.
    """
    existing_due, existing_priority = set(), set()
    for line in original.splitlines():
        match = TODO_RE.match(line)
        if match:
            _, due, priority = parse_todo_details(match.group("text"))
            existing_due.add(due)
            existing_priority.add(priority)
    for line in entry.splitlines():
        match = TODO_RE.match(line)
        if not match:
            continue
        _, due, priority = parse_todo_details(match.group("text"))
        if due is not None and due not in existing_due:
            if (
                not re.fullmatch(r"[0-9]{2}-[0-9]{2}-[0-9]{4}", due)
                or parsed_due_date(due) is None
            ):
                raise RuntimeError(
                    f"LLM proposal generated invalid due metadata: {due}"
                )
        if (
            priority is not None
            and priority not in existing_priority
            and priority not in {"low", "medium", "high"}
        ):
            raise RuntimeError(
                f"LLM proposal generated invalid priority metadata: {priority}"
            )


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
        return f"{target_date.day:02d}-{target_date.month:02d}-{target_date.year:04d}"

    try:
        return TODO_DATE_REFERENCE_RE.sub(replace, text)
    except OverflowError as exc:
        raise RuntimeError(
            "Relative TODO date is outside the supported calendar range."
        ) from exc


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


def todo_with_state(line: str, state: str) -> str:
    """Change only the checkbox character, retaining source text and endings."""
    match = TODO_RE.match(line)
    if match is None:
        raise RuntimeError("The selected line is no longer a TODO.")
    start, end = match.span("state")
    return line[:start] + state + line[end:]


def config_file_path(home: Path | None = None) -> Path:
    base = home if home is not None else Path.home()
    return base / CONFIG_RELATIVE_PATH


def default_htfs_path() -> Path:
    """The mandatory backend ships at the repository's pinned submodule path."""
    return Path(__file__).resolve().parents[1] / "deps" / "HTFS"


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
) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"diary_path={diary_dir}"]
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
            f"Missing or invalid config at {config_path}. Create it with 'diary_path=' and optional 'llm_model=' entries."
        )

    print(f"Config file required: {config_path}")
    print(
        "Populate the diary storage location to continue. HTFS is bundled with the app."
    )
    print("Ollama model is optional.")
    while True:
        diary_answer = input("Diary folder path: ").strip()
        if not diary_answer:
            print("Diary folder path is required.")
            continue
        model_answer = input("LLM model name (optional): ").strip()
        diary_dir = Path(diary_answer).expanduser()
        write_config(config_path, diary_dir, model_answer)
        return AppConfig(
            diary_dir=diary_dir,
            llm_model=model_answer or None,
        )


def load_or_initialize_config(home: Path | None = None, stdin=None) -> AppConfig:
    config_path = config_file_path(home=home)
    if not config_path.exists():
        return prompt_for_config_entries(config_path, stdin=stdin)

    values = parse_config_text(config_path.read_text(encoding="utf-8"))
    diary_path = values.get("diary_path", "").strip()
    llm_model = values.get("llm_model", "").strip() or None
    # Legacy htfs_path entries are ignored; the bundled backend is authoritative.
    if not diary_path:
        return prompt_for_config_entries(config_path, stdin=stdin)

    return AppConfig(
        diary_dir=Path(diary_path).expanduser(),
        llm_model=llm_model,
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
        substring_bonus = (
            3
            if candidate_key
            and (candidate_key in task_key or task_key in candidate_key)
            else 0
        )
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
    return sum(3 if token in lowered else 0 for token in tokens) + overlap_count(
        text, tokens
    )


def todo_reference_date(
    day_text: str | None = None, file_path: Path | None = None
) -> dt.date:
    if file_path is not None:
        try:
            return dt.datetime.strptime(file_path.stem, DATE_FMT).date()
        except ValueError:
            pass
    if day_text is not None:
        normalized = parse_explicit_day_input(day_text)
        return dt.datetime.strptime(normalized, DATE_FMT).date()
    return dt.date.today()


def normalize_todo_dates(entry: str, base_date: dt.date) -> str:
    normalized_lines: list[str] = []
    for line in entry.splitlines():
        match = TODO_RE.match(line)
        if not match or match.group("state") != " ":
            normalized_lines.append(line)
            continue

        todo_text, due, priority = parse_todo_details(match.group("text").strip())
        todo_text = expand_todo_date_references(todo_text, base_date)
        if due is not None and TODO_DATE_REFERENCE_RE.fullmatch(due):
            due = expand_todo_date_references(due, base_date)
        normalized_lines.append(
            render_todo_line(
                match.group("indent"),
                match.group("state"),
                todo_text,
                due=due,
                priority=priority,
            )
        )
    return "\n".join(normalized_lines)


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
    return first_key in second_key or second_key in first_key or overlap_ratio >= 0.8


def parse_explicit_day_input(day_text: str) -> str:
    normalized = day_text.strip()

    # Try parsing as a relative date (e.g., -1, +2, 0)
    if re.fullmatch(r"[-+]?\d+", normalized):
        try:
            days_offset = int(normalized)
            target_date = dt.date.today() + dt.timedelta(days=days_offset)
            return format_diary_date(target_date)
        except (ValueError, OverflowError):
            pass

    if not re.fullmatch(r"\d{2}_\d{2}_\d{4}", normalized):
        raise RuntimeError(
            "Invalid day format. Use dd_mm_yyyy, or relative days like -1, +1, 0."
        )
    try:
        dt.datetime.strptime(normalized, DATE_FMT)
    except ValueError as exc:
        raise RuntimeError(
            "Invalid calendar date. Use a valid dd_mm_yyyy day."
        ) from exc
    return normalized


def date_for_diary_file(path: Path) -> dt.date | None:
    if re.fullmatch(r"[0-9]{2}_[0-9]{2}_[0-9]{4}", path.stem) is None:
        return None
    try:
        return dt.datetime.strptime(path.stem, DATE_FMT).date()
    except ValueError:
        return None


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
    return [tag.rsplit("/", 1)[-1] for tag in tags if tag]
