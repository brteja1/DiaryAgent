"""Timestamp sections with exact source ranges for safe, localized edits."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .models import DiarySection

SECTION_HEADING_RE = re.compile(r"^## (?P<heading>\d{2}:\d{2}(?::[1-9]\d*)?)\s*$")


def section_heading(line: str) -> str | None:
    match = SECTION_HEADING_RE.fullmatch(line.strip())
    return match.group("heading") if match else None


def read_markdown(path: Path) -> str:
    """Preserve LF/CRLF and whitespace; missing diary files have no content."""
    if not path.exists():
        return ""
    with path.open(encoding="utf-8", newline="") as source:
        return source.read()


def write_markdown(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as target:
        target.write(text)


@dataclass(frozen=True)
class SectionSpan:
    heading: str
    start: int
    body_start: int
    end: int
    first_line: int
    last_line: int


@dataclass(frozen=True)
class DiaryDocument:
    """A source snapshot; parsing never rewrites or discards its preamble."""

    text: str
    spans: tuple[SectionSpan, ...]

    @classmethod
    def parse(cls, text: str) -> DiaryDocument:
        headings = []
        offset = 0
        lines = text.splitlines(keepends=True)
        for number, line in enumerate(lines, start=1):
            heading = section_heading(line)
            if heading is not None:
                headings.append((heading, offset, offset + len(line), number))
            offset += len(line)
        spans = []
        for index, (heading, start, body_start, first_line) in enumerate(headings):
            end, last_line = (
                (headings[index + 1][1], headings[index + 1][3] - 1)
                if index + 1 < len(headings)
                else (len(text), len(lines))
            )
            spans.append(
                SectionSpan(heading, start, body_start, end, first_line, last_line)
            )
        return cls(text, tuple(spans))

    def body(self, span: SectionSpan) -> str:
        return self.text[span.body_start : span.end]

    def sections(self, path: Path) -> list[DiarySection]:
        return [
            DiarySection(path, span.heading, self.body(span).strip())
            for span in self.spans
        ]

    def unique_section(self, heading: str) -> SectionSpan | None:
        matches = [span for span in self.spans if span.heading == heading]
        if len(matches) > 1:
            raise RuntimeError(
                f"Ambiguous section {heading}: duplicate timestamp headings; correct them explicitly."
            )
        return matches[0] if matches else None

    def section_at_line(self, number: int) -> SectionSpan | None:
        return next(
            (
                span
                for span in self.spans
                if span.first_line <= number <= span.last_line
            ),
            None,
        )

    def replace_body(self, heading: str, body: str) -> str | None:
        span = self.unique_section(heading)
        if span is None:
            return None
        header = self.text[span.start : span.body_start]
        newline = "\r\n" if header.endswith("\r\n") else "\n"
        leading = newline if header.endswith(("\n", "\r")) else newline * 2
        trailing = "" if body.endswith(("\n", "\r")) else newline
        separator = newline if span.end < len(self.text) else ""
        replacement = leading + body + trailing + separator
        return self.text[: span.body_start] + replacement + self.text[span.end :]

    def delete_section(self, heading: str) -> str | None:
        span = self.unique_section(heading)
        if span is None:
            return None
        return self.text[: span.start] + self.text[span.end :]
