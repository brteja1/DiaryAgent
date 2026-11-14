#!/usr/bin/env python3
"""Stable command-line entrypoint for Diary Agent."""
from diary_agent_app.cli import main
from diary_agent_app.service import DiaryAgent

__all__ = ["DiaryAgent", "main"]

if __name__ == "__main__":
    raise SystemExit(main())
