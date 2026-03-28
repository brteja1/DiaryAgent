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
                "Treat today's existing notes as background context only. Rewrite only the new raw "
                "update and do not restate, summarize, or copy earlier entries from today's file. "
                "Do not add headings, preambles, or commentary. If one point needs sub-points, "
                "keep them as indented nested bullets under that point instead of introducing sections."
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
    return strip_generated_headings(response["message"]["content"])


def strip_generated_headings(text: str) -> str:
    filtered_lines: list[str] = []
    for raw_line in text.strip().splitlines():
        if re.match(r"^\s*#{1,6}\s+", raw_line):
            continue
        filtered_lines.append(raw_line.rstrip())
    return "\n".join(filtered_lines).strip()


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


def suggest_section_tags(model: str, section_body: str, available_tags: Sequence[str]) -> list[str]:
    require_ollama()
    if not available_tags:
        return []

    try:
        response = ollama.chat(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You suggest relevant tags for a diary section using only the provided tag list. "
                        "Return a comma-separated list of exact tag names from the provided list. "
                        "Do not invent tags, do not explain your answer, and return an empty string if none apply."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Available tags:\n"
                        + "\n".join(available_tags)
                        + "\n\nDiary section:\n"
                        + section_body.strip()
                    ),
                },
            ],
        )
    except Exception as exc:
        raise RuntimeError(OLLAMA_UNAVAILABLE_MESSAGE) from exc

    suggested = [part.strip() for part in response["message"]["content"].split(",") if part.strip()]
    available = {tag: tag for tag in available_tags}
    return [available[tag] for tag in suggested if tag in available]
