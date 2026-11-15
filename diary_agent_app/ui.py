from __future__ import annotations

import asyncio
import datetime as dt
import sys
from dataclasses import dataclass, field
from html import escape
from typing import TypeVar
from collections.abc import Callable, Sequence

from .models import PendingTask

try:
    from prompt_toolkit.application import (
        Application,
        run_in_terminal as run_in_terminal,
    )
    from prompt_toolkit.layout import HSplit, Layout
    from prompt_toolkit.layout.containers import ConditionalContainer, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.filters import Condition
    from prompt_toolkit.widgets import Box, Frame, TextArea, CheckboxList
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.shortcuts import (
        button_dialog,
        checkboxlist_dialog,
        message_dialog,
    )
    from prompt_toolkit.styles import Style
except ImportError:  # pragma: no cover - runtime dependency
    Application = None
    run_in_terminal = None
    HSplit = None
    Layout = None
    ConditionalContainer = None
    Window = None
    FormattedTextControl = None
    Condition = None
    Box = None
    Frame = None
    TextArea = None
    CheckboxList = None
    PromptSession = None
    Completer = None
    Completion = None
    HTML = None
    KeyBindings = None
    button_dialog = None
    checkboxlist_dialog = None
    message_dialog = None
    Style = None


DIALOG_STYLE = (
    Style.from_dict(
        {
            "dialog": "bg:#000000 #ffffff",
            "dialog.body": "bg:#000000 #ffffff",
            "dialog shadow": "bg:#000000",
            "frame.label": "bg:#000000 #ffffff bold",
            "label": "bg:#000000 #ffffff",
            "button": "bg:#202020 #ffffff",
            "button.focused": "bg:#ffffff #000000 bold",
            "button.arrow": "bg:#202020 #ffffff",
            "button.focused.arrow": "bg:#ffffff #000000 bold",
            "checkbox": "bg:#000000 #ffffff",
            "checkbox-selected": "bg:#202020 #ffffff",
        }
    )
    if Style is not None
    else None
)


def require_prompt_toolkit() -> None:
    if (
        PromptSession is None
        or Application is None
        or HSplit is None
        or Layout is None
        or ConditionalContainer is None
        or HTML is None
        or KeyBindings is None
        or Window is None
        or FormattedTextControl is None
        or Condition is None
        or Box is None
        or Frame is None
        or TextArea is None
        or CheckboxList is None
        or button_dialog is None
        or checkboxlist_dialog is None
        or Style is None
    ):
        raise RuntimeError(
            "The 'prompt_toolkit' package is required. Install it with: pip install prompt_toolkit"
        )


def _prompt_should_run_in_thread() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def status_toolbar(state: str) -> HTML:
    now = dt.datetime.now().strftime("%d %b %Y %H:%M")
    return HTML(
        f"<b> Date:</b> {now}  <b>State:</b> {escape(state)}  "
        "<style fg='ansiyellow'>Ctrl+D</style> submit"
    )


def confirm_show_latest_entry(requested_title: str, latest_title: str) -> bool:
    require_prompt_toolkit()
    result = button_dialog(
        title="No Entry For Today",
        text=(
            f"No diary entry was found for {requested_title}.\n\n"
            f"The most recent entry is {latest_title}.\n\n"
            "Do you want to show that entry instead?"
        ),
        buttons=[
            ("Show Latest", True),
            ("Cancel", False),
        ],
        style=DIALOG_STYLE,
    ).run(in_thread=_prompt_should_run_in_thread())
    return bool(result)


def confirm_show_latest_entry_cli(
    requested_title: str, latest_title: str, stdin=None
) -> bool:
    stdin = stdin if stdin is not None else sys.stdin
    if not stdin.isatty():
        return False

    print(f"\nNo diary entry was found for {requested_title}.")
    print(f"The most recent entry is {latest_title}.")
    return prompt_yes_no("Show that entry instead?")


if Completer is not None:

    class _CommaSeparatedTagCompleter(Completer):
        def __init__(self, words: Sequence[str]) -> None:
            self._words = list(words)

        def get_completions(self, document, complete_event):
            text_before_cursor = document.text_before_cursor
            last_comma = text_before_cursor.rfind(",")
            fragment = (
                text_before_cursor[last_comma + 1 :]
                if last_comma >= 0
                else text_before_cursor
            )
            stripped_fragment = fragment.lstrip()
            start_position = -len(stripped_fragment)
            fragment_lower = stripped_fragment.lower()

            for word in self._words:
                if fragment_lower and not word.lower().startswith(fragment_lower):
                    continue
                yield Completion(word, start_position=start_position)

else:
    _CommaSeparatedTagCompleter = None


def _tag_input_dialog(top_level_tags, initial_tags, completer) -> str | None:
    tags_input = TextArea(
        text=", ".join(initial_tags),
        height=3,
        prompt="Tags (comma separated)> ",
        multiline=True,
        completer=completer,
        complete_while_typing=True,
    )
    roots = Window(
        content=FormattedTextControl("\n".join(f"• {tag}" for tag in top_level_tags)),
        height=len(top_level_tags) + 1,
    )
    help_text = Window(
        height=1,
        content=FormattedTextControl(
            HTML(
                "<b>Tab:</b> Complete | <b>Enter:</b> Accept (empty clears) | <b>Esc:</b> Cancel"
            )
        ),
    )
    body = HSplit(
        [
            Frame(roots, title="Top Level Tags"),
            Frame(tags_input, title="Enter Tags (Hierarchical or Direct)"),
            help_text,
        ]
    )
    bindings = KeyBindings()

    @bindings.add("enter")
    def accept(event):
        event.app.exit(result=True)

    @bindings.add("escape")
    @bindings.add("c-c")
    def cancel(event):
        event.app.exit(result=False)

    app = Application(
        layout=Layout(Box(body, padding=1), focused_element=tags_input),
        key_bindings=bindings,
        full_screen=True,
        style=DIALOG_STYLE,
    )
    accepted = app.run(in_thread=_prompt_should_run_in_thread())
    return tags_input.text if accepted else None


def _tag_input_cli(
    top_level_tags, initial_tags, suggested_tags, completer
) -> str | None:
    if not sys.stdin.isatty():
        return None
    print("\nTop level HTFS tags: " + (", ".join(top_level_tags) or "(none)"))
    if initial_tags:
        print("Current tags: " + ", ".join(initial_tags))
    if suggested_tags:
        print("Suggestions: " + ", ".join(suggested_tags))
    print("Enter comma-separated tags; empty accepts no tags, Ctrl+C cancels.")
    try:
        if PromptSession is not None:
            return PromptSession(completer=completer).prompt(
                "Section tags> ",
                complete_while_typing=True,
                in_thread=_prompt_should_run_in_thread(),
            )
        return input("Section tags> ")
    except (EOFError, KeyboardInterrupt):
        return None


def prompt_for_section_tags(
    all_tags: Sequence[str],
    top_level_tags: Sequence[str],
    all_paths: Sequence[str],
    initial_tags: Sequence[str] = (),
    suggested_tags: Sequence[str] = (),
) -> list[str] | None:
    """None cancels; an accepted empty list explicitly clears associations."""
    available = sorted(set(all_tags) | set(all_paths))
    completer = (
        _CommaSeparatedTagCompleter(available) if _CommaSeparatedTagCompleter else None
    )
    try:
        require_prompt_toolkit()
        use_dialog = sys.stdin.isatty()
    except RuntimeError:
        use_dialog = False
    if use_dialog:
        initial = sorted(set(initial_tags) | set(suggested_tags))
        raw = _tag_input_dialog(top_level_tags, initial, completer)
    else:
        raw = _tag_input_cli(top_level_tags, initial_tags, suggested_tags, completer)
    if raw is None:
        return None

    selected = sorted({tag.strip() for tag in raw.split(",") if tag.strip()})
    new_tags = [tag for tag in selected if tag not in available]
    if new_tags:
        message = "Create new tags: " + ", ".join(new_tags) + "?"
        if use_dialog:
            confirmed = button_dialog(
                title="Create New Tags?",
                text=message,
                buttons=[("Yes", True), ("No", False)],
                style=DIALOG_STYLE,
            ).run(in_thread=_prompt_should_run_in_thread())
        else:
            confirmed = prompt_yes_no(message)
        if not confirmed:
            return None
    return selected


@dataclass
class EditorState:
    """One active operation owns the editor lock until its finally block."""

    message: str
    busy: bool = False
    rewrite_ready: bool = False
    suggested_tags: list[str] = field(default_factory=list)
    original_draft: str | None = None


ActionResult = TypeVar("ActionResult")


def _start_editor_action(
    event,
    state: EditorState,
    work: Callable[[str], ActionResult] | None,
    apply: Callable[[ActionResult], None],
    waiting: str,
    failure: str,
) -> None:
    """Run model work off the UI loop and always release the buffer lock."""
    if work is None or state.busy or state.original_draft is not None:
        return
    text = event.current_buffer.text
    state.busy = True
    state.message = waiting
    event.app.invalidate()

    async def run():
        try:
            result = await asyncio.get_running_loop().run_in_executor(None, work, text)
            # prompt_toolkit rejects programmatic text changes while read-only.
            state.busy = False
            apply(result)
        except Exception as exc:
            state.message = f"{failure}: {exc}"
        finally:
            state.busy = False
            event.app.invalidate()

    event.app.create_background_task(run())


def launch_editor(
    initial_text: str = "",
    state: str = "Capturing update",
    info_message: str | None = None,
    rewrite: Callable[[str], str] | None = None,
    suggest_tags: Callable[[str], list[str]] | None = None,
) -> tuple[str, list[str]]:
    try:
        require_prompt_toolkit()
        session = PromptSession(multiline=True)
        bindings = KeyBindings()
        editor_state = EditorState(state)
        session.default_buffer.read_only = Condition(
            lambda: editor_state.busy or editor_state.original_draft is not None
        )

        @bindings.add("c-d")
        def submit(event) -> None:
            if not editor_state.busy and editor_state.original_draft is None:
                event.current_buffer.validate_and_handle()

        @bindings.add("escape", "r")
        def request_rewrite(event) -> None:
            def apply(text: str):
                original = event.current_buffer.text
                event.current_buffer.text = text
                event.current_buffer.cursor_position = len(text)
                editor_state.original_draft = original
                editor_state.message = (
                    "Review complete proposal: Alt+Y accept | Alt+N reject"
                )

            _start_editor_action(
                event,
                editor_state,
                rewrite,
                apply,
                "Waiting for LLM rewrite...",
                "Rewrite failed",
            )

        @bindings.add("escape", "y")
        def accept_rewrite(event) -> None:
            if editor_state.original_draft is not None:
                editor_state.original_draft = None
                editor_state.rewrite_ready = True
                editor_state.message = "Rewrite accepted."

        @bindings.add("escape", "n")
        def reject_rewrite(event) -> None:
            if editor_state.original_draft is not None:
                original = editor_state.original_draft
                editor_state.original_draft = None
                event.current_buffer.text = original
                editor_state.message = "Rewrite rejected; draft retained."

        @bindings.add("escape", "s")
        def request_tags(event) -> None:
            def apply(tags: list[str]):
                editor_state.suggested_tags = tags
                editor_state.message = (
                    f"Tags suggested: {', '.join(tags)}"
                    if tags
                    else "No tags suggested."
                )

            _start_editor_action(
                event,
                editor_state,
                suggest_tags,
                apply,
                "Waiting for tag suggestions...",
                "Suggestion failed",
            )

        def toolbar():
            if editor_state.busy or editor_state.original_draft is not None:
                return status_toolbar(editor_state.message)
            hints = []
            if rewrite is not None:
                hints.append(
                    "Alt+R rewrite again"
                    if editor_state.rewrite_ready
                    else "Alt+R rewrite"
                )
            if suggest_tags is not None:
                hints.append("Alt+S suggest tags")
            return status_toolbar("  ".join([editor_state.message, *hints]))

        prompt_text = (
            "Diary update> " if not info_message else f"{info_message}\nDiary update> "
        )
        final_text = session.prompt(
            prompt_text,
            default=initial_text,
            key_bindings=bindings,
            bottom_toolbar=toolbar,
            in_thread=_prompt_should_run_in_thread(),
        )
        return final_text, editor_state.suggested_tags
    except RuntimeError:
        # CLI fallback
        if info_message:
            print(info_message)
        print("Enter your diary update (Ctrl-D or empty line to finish):")
        lines = []
        while True:
            try:
                line = input()
                if line == "":
                    break
                lines.append(line)
            except EOFError:
                break
        return "\n".join(lines), []


def prompt_yes_no(prompt: str, default: bool = False) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        try:
            answer = input(f"{prompt} {suffix}: ").strip().lower()
        except EOFError:
            return default

        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Please answer y or n.")


def select_pending_tasks(tasks: Sequence[PendingTask]) -> list[PendingTask]:
    require_prompt_toolkit()
    selected = checkboxlist_dialog(
        title="Pending TODOs",
        text="Select pending tasks to mark complete.",
        values=[
            (task.key, f"{task.file_path.name}:{task.line_number}  {task.display_text}")
            for task in tasks
        ],
        ok_text="Complete",
        cancel_text="Skip",
        style=DIALOG_STYLE,
    ).run(in_thread=_prompt_should_run_in_thread())
    return [task for task in tasks if selected and task.key in selected]


def show_completed_task_count(count: int) -> None:
    message_dialog(
        title="Tasks Updated",
        text=f"Marked {count} task(s) complete.",
        style=DIALOG_STYLE,
    ).run(in_thread=_prompt_should_run_in_thread())
