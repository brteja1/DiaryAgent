"""Argument parsing, startup validation and command dispatch."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from . import commands
from .core import load_or_initialize_config
from .service import DiaryAgent
from .htfs_adapter import HTFSAdapter
from .persistence import PersistenceInterrupted


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Offline diary agent powered by Ollama.",
    )
    parser.add_argument(
        "--model",
        help="Optional Ollama model override. If omitted, the app stays in no-LLM mode unless the config provides a model.",
    )

    subparsers = parser.add_subparsers(dest="command")

    capture_parser = subparsers.add_parser(
        "capture",
        help="Open the editor and append a note to a diary file. Use --day DD_MM_YYYY or relative days (e.g., -1 for yesterday) to target a different day.",
        description=(
            "Open the editor and append a note to a diary file. "
            "By default, capture writes to today's diary file."
        ),
    )
    capture_parser.add_argument(
        "--text",
        help="Text to capture without opening the editor; changed proposals require consent.",
    )
    capture_parser.add_argument(
        "--day",
        metavar="DAY",
        help="Write to a specific diary day in dd_mm_yyyy format or relative days like -1 or +1. Defaults to today.",
    )

    search_parser = subparsers.add_parser(
        "search",
        help="Search diary history and optionally filter by HTFS tag expression.",
    )
    search_parser.add_argument(
        "query",
        nargs="?",
        help="Natural-language query to search for. Omit it to list sections matching only the tag filter.",
    )
    search_parser.add_argument(
        "--tags",
        help="Optional HTFS tag expression, or a natural-language tag filter when a model is configured.",
    )

    show_parser = subparsers.add_parser(
        "show",
        help="Show the diary entry for a particular day.",
    )
    show_parser.add_argument(
        "day",
        nargs="?",
        help="Day in dd_mm_yyyy format or relative days like -1, +1, 0.",
    )

    subparsers.add_parser(
        "todos",
        help="List and manage pending todos.",
    )

    tags_parser = subparsers.add_parser(
        "tags",
        help="Show, apply, or suggest HTFS tags for a diary section.",
    )
    tags_subparsers = tags_parser.add_subparsers(dest="tags_command", required=True)

    tags_subparsers.add_parser(
        "ls",
        aliases=["list"],
        help="List all HTFS tags.",
    )

    tags_tree_parser = tags_subparsers.add_parser(
        "tree",
        help="Show HTFS tags as a hierarchy.",
    )
    tags_tree_parser.add_argument(
        "tag",
        nargs="?",
        help="Optional root tag to show a subtree.",
    )

    tags_show_parser = tags_subparsers.add_parser(
        "show",
        help="Show HTFS tags for a specific diary section.",
    )
    tags_show_parser.add_argument(
        "day", help="Day in dd_mm_yyyy format or relative days like -1, +1, 0."
    )
    tags_show_parser.add_argument(
        "time", nargs="?", help="Section time in HH:MM or HH:MM:<serial> format."
    )

    tags_apply_parser = tags_subparsers.add_parser(
        "apply",
        help="Apply HTFS tags to a specific diary section.",
    )
    tags_apply_parser.add_argument(
        "day", help="Day in dd_mm_yyyy format or relative days like -1, +1, 0."
    )
    tags_apply_parser.add_argument(
        "time", help="Section time in HH:MM or HH:MM:<serial> format."
    )
    tags_apply_parser.add_argument(
        "tags", nargs="+", help="One or more HTFS tags to apply."
    )

    tags_suggest_parser = tags_subparsers.add_parser(
        "suggest",
        help="Suggest HTFS tags for a specific diary section.",
    )
    tags_suggest_parser.add_argument(
        "day", help="Day in dd_mm_yyyy format or relative days like -1, +1, 0."
    )

    tags_suggest_parser.add_argument(
        "time", help="Section time in HH:MM or HH:MM:<serial> format."
    )

    tags_delete_parser = tags_subparsers.add_parser(
        "delete",
        help="Delete a tag from the HTFS taxonomy.",
    )
    tags_delete_parser.add_argument("tag", help="HTFS tag to delete.")
    tags_delete_parser.add_argument(
        "--descendants",
        action="store_true",
        default=None,
        help="Delete descendant tags as well.",
    )
    tags_delete_parser.add_argument(
        "--unused-only",
        action="store_true",
        default=None,
        help="Only delete tags that are unused by diary resources.",
    )
    tags_delete_parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the final confirmation prompt.",
    )
    recovery_parser = subparsers.add_parser(
        "recovery",
        help="Inspect operations and retry metadata without replaying diary writes.",
    )
    recovery_commands = recovery_parser.add_subparsers(
        dest="recovery_command", required=True
    )
    list_parser = recovery_commands.add_parser("list", help="List pending operations.")
    list_parser.add_argument(
        "--all",
        action="store_true",
        dest="include_complete",
        help="Include retained completion receipts.",
    )
    for action in ("show", "retry", "resolve"):
        action_parser = recovery_commands.add_parser(action)
        action_parser.add_argument("operation_id")
        if action == "resolve":
            action_parser.add_argument("--reason", required=True)
            action_parser.add_argument("--yes", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    command = args.command or "capture"
    try:
        HTFSAdapter.require_backend()
        config = load_or_initialize_config()
        agent = DiaryAgent(
            diary_dir=config.diary_dir,
            model=args.model or config.llm_model,
        )
        agent.ensure_storage()
        commands.get_htfs_adapter(agent.diary_dir).list_tags()
        if command == "capture":
            return commands.run_capture(
                agent,
                raw_text=getattr(args, "text", None),
                day_text=getattr(args, "day", None),
            )
        if command == "search":
            return commands.run_search(agent, query=args.query, tag_filter=args.tags)
        if command == "show":
            return commands.run_show_day(agent, day_text=args.day)
        if command == "todos":
            return commands.run_todos(agent)
        if command == "recovery":
            return commands.run_recovery(
                agent,
                args.recovery_command,
                getattr(args, "operation_id", None),
                include_complete=getattr(args, "include_complete", False),
                reason=getattr(args, "reason", ""),
                yes=getattr(args, "yes", False),
            )
        if command == "tags":
            tags_command = args.tags_command
            if tags_command in {"ls", "list"}:
                return commands.run_tags_list(agent)
            if tags_command == "tree":
                return commands.run_tags_tree(agent, args.tag)
            if tags_command == "show":
                return commands.run_tags_show(agent, args.day, args.time)
            if tags_command == "apply":
                return commands.run_tags_apply(agent, args.day, args.time, args.tags)
            if tags_command == "suggest":
                return commands.run_tags_suggest(agent, args.day, args.time)
            if tags_command == "delete":
                return commands.run_tags_delete(
                    agent,
                    args.tag,
                    descendants=args.descendants,
                    only_unused=args.unused_only,
                    yes=args.yes,
                )
        parser.error(f"Unknown command: {command}")
    except PersistenceInterrupted as exc:
        print(f"Interrupted: {exc}", file=sys.stderr)
        return 130
    except KeyboardInterrupt:
        print("\nAborted.")
        return 130
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1
    return 0
