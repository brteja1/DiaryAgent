from __future__ import annotations

import datetime as dt
import sys

from .models import SimilarTodoMatch

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.shortcuts import button_dialog, checkboxlist_dialog, message_dialog
    from prompt_toolkit.styles import Style
except ImportError:  # pragma: no cover - runtime dependency
    PromptSession = None
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
        or HTML is None
        or KeyBindings is None
        or button_dialog is None
        or checkboxlist_dialog is None
        or Style is None
    ):
        raise RuntimeError(
            "The 'prompt_toolkit' package is required. Install it with: pip install prompt_toolkit"
        )


def status_toolbar(state: str) -> HTML:
    now = dt.datetime.now().strftime("%d %b %Y %H:%M")
    return HTML(
        f"<b> Date:</b> {now}  <b>State:</b> {state}  "
        "<style fg='ansiyellow'>Ctrl+D</style> submit"
    )


def confirm_similar_todo_addition(match: SimilarTodoMatch) -> bool:
    require_prompt_toolkit()
    result = button_dialog(
        title="Similar TODO Found",
        text=(
            "A similar unresolved TODO already exists.\n\n"
            f"New TODO:\n{match.candidate_text}\n\n"
            f"Existing TODO:\n{match.existing_task.text}\n"
            f"Source: {match.existing_task.file_path.name}:{match.existing_task.line_number}\n\n"
            "Do you want to add the new TODO anyway?"
        ),
        buttons=[
            ("Add Anyway", True),
            ("Skip", False),
        ],
        style=DIALOG_STYLE,
    ).run()
    return bool(result)


def confirm_similar_todo_addition_cli(match: SimilarTodoMatch, stdin=None) -> bool:
    stdin = stdin if stdin is not None else sys.stdin
    if not stdin.isatty():
        return False

    print("\nSimilar TODO found:")
    print(f"New TODO: {match.candidate_text}")
    print(f"Existing TODO: {match.existing_task.text}")
    print(f"Source: {match.existing_task.file_path.name}:{match.existing_task.line_number}")
    while True:
        answer = input("Add the new TODO anyway? [y/N]: ").strip().lower()
        if answer in {"", "n", "no"}:
            return False
        if answer in {"y", "yes"}:
            return True
        print("Please answer y or n.")


def launch_editor(initial_text: str = "") -> str:
    require_prompt_toolkit()
    session = PromptSession(multiline=True)
    bindings = KeyBindings()

    @bindings.add("c-d")
    def _(event) -> None:
        event.current_buffer.validate_and_handle()

    return session.prompt(
        "Diary update> ",
        default=initial_text,
        key_bindings=bindings,
        bottom_toolbar=lambda: status_toolbar("Capturing update"),
    )
