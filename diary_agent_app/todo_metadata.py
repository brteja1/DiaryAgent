"""Interpret metadata without changing its stored spelling."""

from __future__ import annotations

import datetime as dt
import re

PRIORITIES = frozenset({"low", "medium", "high"})


def parsed_due_date(raw: str | None) -> dt.date | None:
    if raw is None:
        return None
    formats = (
        (r"[0-9]{2}-[0-9]{2}-[0-9]{4}", "%d-%m-%Y"),
        (r"[0-9]{4}-[0-9]{2}-[0-9]{2}", "%Y-%m-%d"),
        (r"[0-9]{2}_[0-9]{2}_[0-9]{4}", "%d_%m_%Y"),
    )
    for pattern, format_string in formats:
        if re.fullmatch(pattern, raw):
            try:
                return dt.datetime.strptime(raw, format_string).date()
            except ValueError:
                return None
    return None


def field_status(raw: str | None, valid: bool) -> str:
    return "absent" if raw is None else "validated" if valid else "unvalidated"
