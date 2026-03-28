from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Sequence


try:
    import ollama
except ImportError:  # pragma: no cover - runtime dependency
    ollama = None


OLLAMA_UNAVAILABLE_MESSAGE = (
    "Unable to reach the local Ollama service. Ensure Ollama is installed, "
    "running, and has the configured model pulled."
)


def require_ollama() -> None:
    if ollama is None:
        raise RuntimeError(
            "The 'ollama' Python package is required. Install it with: pip install ollama"
        )


def synthesize_entry(
    model: str,
    raw_update: str,
    today_context: str,
    now: dt.datetime | None = None,
) -> str:
    require_ollama()

    now = now or dt.datetime.now()
    context_excerpt = today_context[-4000:] if today_context else "(No existing notes today.)"
    messages = [
        {
            "role": "system",
            "content": (
                "You are an offline diary assistant. Transform the user's informal update "
                "into concise Markdown bullet points. Preserve factual details, fix grammar, "
                "and keep continuity with the existing note if relevant. Use '- [ ] ...' "
                "for actionable reminders or TODOs (items the user intends to do in the future), "
                "and '- ...' for regular notes (observations, reflections, completed actions, "
                "or information). Do not repeat unresolved TODOs that already exist in the diary. "
                "Do not add headings, preambles, or commentary."
            ),
        },
        {
            "role": "user",
            "content": (
                "Timestamp: " + now.strftime('%Y-%m-%d %H:%M:%S') + "\n"
                "Today's existing notes:\n" + context_excerpt + "\n\n"
                "Raw update:\n" + raw_update.strip()
            ),
        },
    ]
    try:
        response = ollama.chat(model=model, messages=messages)
    except Exception as exc:
        raise RuntimeError(OLLAMA_UNAVAILABLE_MESSAGE) from exc
    return response["message"]["content"].strip()


def answer_query(model: str, query: str, matches: Sequence[tuple[Path, str, int]]) -> str:
    require_ollama()
    if not matches:
        return "No relevant diary history found."

    excerpts = "\n\n".join(
        f"File: {path.name}\nExcerpt:\n{snippet}"
        for path, snippet, _score in matches
    )
    try:
        response = ollama.chat(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You answer questions about diary history using only the supplied excerpts. "
                        "Be concise, cite file names inline, and say when the excerpts are insufficient."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Question: {query}\n\nDiary excerpts:\n{excerpts}",
                },
            ],
        )
    except Exception as exc:
        raise RuntimeError(OLLAMA_UNAVAILABLE_MESSAGE) from exc
    return response["message"]["content"].strip()


def organize_day_entry(model: str, body: str) -> str:
    stripped = body.strip()
    if not stripped:
        return ""

    try:
        require_ollama()
        response = ollama.chat(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You reorganize a single day's diary entry into clearer Markdown sections. "
                        "Group related items by relevance or topic, not by original order alone. "
                        "Preserve every concrete item from the source. Do not invent facts, do not "
                        "drop tasks, and do not summarize multiple bullets into one. Use concise "
                        "section headings like '## Work', '## Follow-ups', or similar. Keep each "
                        "original bullet as a Markdown bullet. If an item is a TODO, keep its checkbox state."
                    ),
                },
                {
                    "role": "user",
                    "content": "Reorganize this diary entry:\n\n" + stripped,
                },
            ],
        )
        organized = response["message"]["content"].strip()
        if organized:
            return organized
    except Exception:
        pass

    return organize_day_entry_fallback(stripped)


def organize_day_entry_fallback(body: str) -> str:
    sections: list[tuple[str, list[str]]] = [
        ("Pending TODOs", []),
        ("Completed TODOs", []),
        ("Notes", []),
        ("Other", []),
    ]

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.match(r"^- \[ \] ", line):
            sections[0][1].append(line)
            continue
        if re.match(r"^- \[[xX]\] ", line):
            sections[1][1].append(line)
            continue
        if line.startswith("- "):
            sections[2][1].append(line)
            continue
        sections[3][1].append(f"- {line}")

    rendered_sections = [
        "## " + title + "\n" + "\n".join(lines)
        for title, lines in sections
        if lines
    ]
    return "\n\n".join(rendered_sections).strip()


def todos_are_semantically_similar(model: str, candidate_text: str, existing_text: str) -> bool:
    require_ollama()
    try:
        response = ollama.chat(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You compare two TODO items and decide whether they are effectively the same "
                        "unresolved task. Treat paraphrases, reordered wording, and small timing wording "
                        "differences as the same task when the intended action is still the same. "
                        "Reply with exactly YES or NO."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"TODO A: {candidate_text}\n"
                        f"TODO B: {existing_text}\n\n"
                        "Are these aggressively similar enough that re-adding TODO A would probably be redundant?"
                    ),
                },
            ],
        )
    except Exception:
        return False

    verdict = response["message"]["content"].strip().upper()
    return verdict.startswith("YES")
def classify_as_todo(model: str, text: str) -> bool | None:
    """
    Classify whether text represents an actionable TODO using LLM inference.
    Returns True if it's a TODO, False if it's a regular note, None on error.
    """
    require_ollama()
    try:
        response = ollama.chat(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You classify text as either a TODO/actionable item or a regular note. "
                        "TODOs are actionable tasks with clear intent to do something in the future. "
                        "Regular notes are observations, reflections, completed actions, or information. "
                        "Reply with exactly YES if this is a TODO, NO if it's a regular note."
                    ),
                },
                {
                    "role": "user",
                    "content": "Text to classify:\n" + text + "\n\nIs this a TODO/actionable item?",
                },
            ],
        )
    except Exception:
        return None

    verdict = response["message"]["content"].strip().upper()
    if verdict.startswith("YES"):
        return True
    elif verdict.startswith("NO"):
        return False
    return None
