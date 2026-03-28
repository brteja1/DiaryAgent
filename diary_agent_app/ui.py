from __future__ import annotations

import asyncio
import datetime as dt
import sys
from collections.abc import Callable, Sequence

from .models import DiaryEntryOption, SimilarTodoMatch

try:
    from prompt_toolkit.application import Application
    from prompt_toolkit.layout import HSplit, Layout
    from prompt_toolkit.layout.containers import ConditionalContainer, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.filters import Condition
    from prompt_toolkit.widgets import Box, Frame, TextArea
    from prompt_toolkit import PromptSession
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.shortcuts import button_dialog, checkboxlist_dialog, message_dialog
    from prompt_toolkit.styles import Style
except ImportError:  # pragma: no cover - runtime dependency
    Application = None
    HSplit = None
    Layout = None
    ConditionalContainer = None
    Window = None
    FormattedTextControl = None
    Condition = None
    Box = None
    Frame = None
    TextArea = None
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


def prompt_for_section_tags(existing_tags: Sequence[str]) -> list[str]:
    prompt_text = "Section tags> "
    if existing_tags:
        print("\nExisting HTFS tags:")
        print(", ".join(existing_tags))
    else:
        print("\nNo existing HTFS tags yet.")
    print("Enter tags separated by commas, or press Enter to skip.")

    try:
        require_prompt_toolkit()
        session = PromptSession()
        raw_value = session.prompt(prompt_text)
    except RuntimeError:
        raw_value = input(prompt_text)

    return [part.strip() for part in raw_value.split(",") if part.strip()]


def launch_editor(
    initial_text: str = "",
    state: str = "Capturing update",
    rewrite: Callable[[str], str] | None = None,
) -> str:
    try:
        require_prompt_toolkit()
        session = PromptSession(multiline=True)
        bindings = KeyBindings()
        editor_state = {
            "message": state,
            "rewriting": False,
            "rewrite_ready": False,
        }
        session.default_buffer.read_only = Condition(lambda: editor_state["rewriting"])

        @bindings.add("c-d")
        def _(event) -> None:
            if editor_state["rewriting"]:
                return
            event.current_buffer.validate_and_handle()

        @bindings.add("escape", "r")
        def _(event) -> None:
            if rewrite is None or editor_state["rewriting"]:
                return

            current_text = event.current_buffer.text
            editor_state["rewriting"] = True
            editor_state["message"] = "Waiting for LLM rewrite..."
            event.app.invalidate()

            async def rewrite_task() -> None:
                try:
                    loop = asyncio.get_running_loop()
                    rewritten = await loop.run_in_executor(None, rewrite, current_text)
                except Exception as exc:  # pragma: no cover - interactive UI boundary
                    editor_state["message"] = f"Rewrite failed: {exc}"
                    editor_state["rewriting"] = False
                else:
                    editor_state["rewriting"] = False
                    editor_state["rewrite_ready"] = True
                    event.current_buffer.text = rewritten
                    event.current_buffer.cursor_position = len(rewritten)
                    editor_state["message"] = "Rewrite applied."
                finally:
                    event.app.invalidate()

            event.app.create_background_task(rewrite_task())

        return session.prompt(
            "Diary update> ",
            default=initial_text,
            key_bindings=bindings,
            bottom_toolbar=lambda: status_toolbar(
                (
                    "Waiting for LLM rewrite..."
                    if editor_state["rewriting"]
                    else (
                        editor_state["message"]
                        + (
                            "  Alt+R rewrite again"
                            if rewrite is not None and editor_state["rewrite_ready"]
                            else ("  Alt+R rewrite" if rewrite is not None else "")
                        )
                    )
                )
            ),
        )
    except RuntimeError:
        # CLI fallback
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
        return "\n".join(lines)


def show_diary_entry(
    title: str,
    body: str,
    previous_entry=None,
    next_entry=None,
    pick_entry=None,
) -> None:
    require_prompt_toolkit()

    text_area = TextArea(
        text=body,
        read_only=True,
        scrollbar=True,
        focusable=True,
        wrap_lines=False,
    )
    query_input = TextArea(
        height=1,
        multiline=False,
        wrap_lines=False,
        prompt="Jump to> ",
    )
    picker_state = {"open": False, "selected": 0}

    def picker_filter() -> bool:
        return picker_state["open"]

    picker_visible = Condition(picker_filter)
    help_bar = Window(
        height=1,
        content=FormattedTextControl(
            lambda: HTML(
                "<b>Move:</b> Up / Down  "
                "<b>Select:</b> Enter  "
                "<b>Cancel:</b> Esc"
                if picker_state["open"]
                else "<b>Browse:</b> Arrow keys / PageUp / PageDown  "
                "<b>Jump:</b> [ / ] / g  "
                "<b>Exit:</b> q, Esc, Ctrl+C"
            )
        ),
    )

    frame = Frame(text_area, title=title)
    picker_frame = Frame(query_input, title="Jump To Entry")

    def filtered_options() -> list[DiaryEntryOption]:
        if pick_entry is None:
            return []
        query = " ".join(query_input.text.lower().split())
        options = list(pick_entry())
        if not query:
            return options
        terms = query.split()
        return [
            option
            for option in options
            if all(term in option.search_text for term in terms)
        ]

    def render_results():
        matches = filtered_options()
        if not matches:
            picker_state["selected"] = 0
            return [("", "No matching entries.")]

        if picker_state["selected"] >= len(matches):
            picker_state["selected"] = len(matches) - 1

        fragments: list[tuple[str, str]] = []
        for index, option in enumerate(matches):
            style = "reverse" if index == picker_state["selected"] else ""
            fragments.append((style, option.title))
            if option.preview:
                fragments.append((style, f"  {option.preview}"))
            fragments.append(("", "\n"))
        return fragments[:-1]

    results_window = Window(
        content=FormattedTextControl(render_results),
        always_hide_cursor=True,
    )
    picker_results_frame = Frame(results_window, title="Matches")

    bindings = KeyBindings()

    @bindings.add("q")
    @bindings.add("c-c")
    def _(event) -> None:
        if picker_state["open"]:
            picker_state["open"] = False
            query_input.text = ""
            picker_state["selected"] = 0
            event.app.layout.focus(text_area)
            event.app.invalidate()
            return
        event.app.exit()

    @bindings.add("escape")
    def _(event) -> None:
        if picker_state["open"]:
            picker_state["open"] = False
            query_input.text = ""
            picker_state["selected"] = 0
            event.app.layout.focus(text_area)
            event.app.invalidate()
            return
        event.app.exit()

    def move_to_entry(loader) -> None:
        if loader is None:
            return
        target = loader(frame.title)
        if target is None:
            return
        next_title, next_body = target
        frame.title = next_title
        text_area.text = next_body
        text_area.buffer.cursor_position = 0

    @bindings.add("[")
    def _(event) -> None:
        move_to_entry(previous_entry)

    @bindings.add("]")
    def _(event) -> None:
        move_to_entry(next_entry)

    @bindings.add("g")
    def _(event) -> None:
        if pick_entry is None:
            return
        picker_state["open"] = True
        picker_state["selected"] = 0
        query_input.text = ""
        event.app.layout.focus(query_input)
        event.app.invalidate()

    query_input.buffer.on_text_changed += lambda _event: (
        picker_state.__setitem__("selected", 0)
    )

    @bindings.add("down", filter=picker_visible)
    @bindings.add("c-n", filter=picker_visible)
    def _(event) -> None:
        matches = filtered_options()
        if matches:
            picker_state["selected"] = min(picker_state["selected"] + 1, len(matches) - 1)
            event.app.invalidate()

    @bindings.add("up", filter=picker_visible)
    @bindings.add("c-p", filter=picker_visible)
    def _(event) -> None:
        if filtered_options():
            picker_state["selected"] = max(picker_state["selected"] - 1, 0)
            event.app.invalidate()

    @bindings.add("enter", filter=picker_visible)
    def _(event) -> None:
        matches = filtered_options()
        if not matches:
            return
        selected = matches[picker_state["selected"]]
        frame.title = selected.file_path.name
        text_area.text = selected.file_path.read_text(encoding="utf-8").rstrip()
        text_area.buffer.cursor_position = 0
        picker_state["open"] = False
        query_input.text = ""
        picker_state["selected"] = 0
        event.app.layout.focus(text_area)
        event.app.invalidate()

    root = Box(
        body=HSplit(
            [
                ConditionalContainer(frame, filter=~picker_visible),
                ConditionalContainer(
                    HSplit(
                        [
                            picker_frame,
                            picker_results_frame,
                        ]
                    ),
                    filter=picker_visible,
                ),
                help_bar,
            ]
        ),
        padding=1,
    )

    app = Application(
        layout=Layout(root, focused_element=text_area),
        key_bindings=bindings,
        full_screen=True,
        style=DIALOG_STYLE,
    )
    app.run()
