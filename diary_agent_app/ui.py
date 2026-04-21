from __future__ import annotations

import asyncio
import datetime as dt
import re
import sys
from collections.abc import Callable, Sequence

from .models import DiaryEntryOption, SimilarTodoMatch
from .core import TODO_RE

try:
    from prompt_toolkit.application import Application, run_in_terminal
    from prompt_toolkit.layout import HSplit, Layout
    from prompt_toolkit.layout.containers import ConditionalContainer, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.filters import Condition
    from prompt_toolkit.widgets import Box, Frame, TextArea, CheckboxList
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
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

SHOW_SECTION_HEADING_RE = re.compile(r"^## (?P<heading>\d{2}:\d{2}(?::[1-9]\d*)?)(?:\s|$)")


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
    ).run(in_thread=_prompt_should_run_in_thread())
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


def confirm_show_latest_entry_cli(requested_title: str, latest_title: str, stdin=None) -> bool:
    stdin = stdin if stdin is not None else sys.stdin
    if not stdin.isatty():
        return False

    print(f"\nNo diary entry was found for {requested_title}.")
    print(f"The most recent entry is {latest_title}.")
    while True:
        answer = input("Show that entry instead? [y/N]: ").strip().lower()
        if answer in {"", "n", "no"}:
            return False
        if answer in {"y", "yes"}:
            return True
        print("Please answer y or n.")


if Completer is not None:
    class _CommaSeparatedTagCompleter(Completer):
        def __init__(self, words: Sequence[str]) -> None:
            self._words = list(words)

        def get_completions(self, document, complete_event):
            text_before_cursor = document.text_before_cursor
            last_comma = text_before_cursor.rfind(",")
            fragment = text_before_cursor[last_comma + 1 :] if last_comma >= 0 else text_before_cursor
            stripped_fragment = fragment.lstrip()
            start_position = -len(stripped_fragment)
            fragment_lower = stripped_fragment.lower()

            for word in self._words:
                if fragment_lower and not word.lower().startswith(fragment_lower):
                    continue
                yield Completion(word, start_position=start_position)
else:
    _CommaSeparatedTagCompleter = None


def prompt_for_section_tags(
    all_tags: Sequence[str],
    top_level_tags: Sequence[str],
    all_paths: Sequence[str],
    initial_tags: Sequence[str] = [],
    suggested_tags: Sequence[str] = [],
) -> list[str]:
    unique_tags = sorted(dict.fromkeys(all_tags))
    unique_paths = sorted(dict.fromkeys(all_paths))
    all_suggestions = sorted(list(set(unique_tags + unique_paths)))
    tag_completer = _CommaSeparatedTagCompleter(all_suggestions) if _CommaSeparatedTagCompleter is not None else None

    try:
        require_prompt_toolkit()
        if not sys.stdin.isatty():
            raise RuntimeError("Not a TTY")

        # UI Components
        top_level_text = "\n".join([f"• {t}" for t in top_level_tags])
        top_level_window = Window(
            content=FormattedTextControl(top_level_text),
            height=len(top_level_tags) + 1,
        )

        # Pre-populate with initial and suggested tags
        combined_initial = sorted(list(set(list(initial_tags) + list(suggested_tags))))
        initial_text = ", ".join(combined_initial)
        tags_input = TextArea(
            text=initial_text,
            height=3,
            prompt="Tags (comma separated)> ",
            multiline=True,
            completer=tag_completer,
            complete_while_typing=True,
        )

        body = HSplit(
            [
                Frame(top_level_window, title="Top Level Tags"),
                Frame(tags_input, title="Enter Tags (Hierarchical or Direct)"),
                Window(
                    height=1,
                    content=FormattedTextControl(
                        lambda: HTML(
                            "<b>Tab:</b> Autocomplete | <b>Enter:</b> Save | <b>Esc:</b> Cancel"
                        )
                    ),
                ),
            ]
        )

        root = Box(body, padding=1)
        kb = KeyBindings()

        @kb.add("enter")
        def _(event):
            event.app.exit(result=True)

        @kb.add("escape")
        @kb.add("c-c")
        def _(event):
            event.app.exit(result=False)

        app = Application(
            layout=Layout(root, focused_element=tags_input),
            key_bindings=kb,
            full_screen=True,
            style=DIALOG_STYLE,
        )

        success = app.run(in_thread=_prompt_should_run_in_thread())
        if not success:
            return []

        # Parse and validate tags
        entered_tags = [t.strip() for t in tags_input.text.split(",") if t.strip()]
        final_tags = []
        new_tags_to_confirm = []

        existing_set = set(all_suggestions)
        for tag in entered_tags:
            if tag in existing_set:
                final_tags.append(tag)
            else:
                new_tags_to_confirm.append(tag)

        if new_tags_to_confirm:
            tags_str = ", ".join(new_tags_to_confirm)
            confirm = button_dialog(
                title="Create New Tags?",
                text=f"The following tags do not exist:\n\n{tags_str}\n\nDo you want to create them?",
                buttons=[
                    ("Yes", True),
                    ("No", False),
                ],
                style=DIALOG_STYLE,
            ).run(in_thread=_prompt_should_run_in_thread())

            if confirm:
                final_tags.extend(new_tags_to_confirm)

        return sorted(list(set(final_tags)))

    except (RuntimeError, Exception):
        # Fallback to simple input
        prompt_text = "Section tags> "
        if top_level_tags:
            print("\nTop level HTFS tags:")
            for t in top_level_tags:
                print(f"  • {t}")
        else:
            print("\nNo HTFS tags yet.")

        if suggested_tags:
            print(f"Suggestions: {', '.join(suggested_tags)}")

        print("Enter tags separated by commas (e.g., Topic/AI, People/Alice), or press Enter to skip.")
        if PromptSession is not None:
            session = PromptSession(completer=tag_completer)
            try:
                raw_value = session.prompt(
                    prompt_text,
                    complete_while_typing=True,
                    in_thread=_prompt_should_run_in_thread(),
                )
            except (EOFError, KeyboardInterrupt):
                return []
        else:
            try:
                raw_value = input(prompt_text)
            except (EOFError, KeyboardInterrupt):
                return []

        entered_tags = [part.strip() for part in raw_value.split(",") if part.strip()]
        existing_set = set(all_suggestions)
        final_tags = []
        new_tags = []
        for t in entered_tags:
            if t in existing_set:
                final_tags.append(t)
            else:
                new_tags.append(t)

        if new_tags:
            print(f"\nThe following tags are new: {', '.join(new_tags)}")
            ans = input("Create these new tags? [y/N]: ").strip().lower()
            if ans in {"y", "yes"}:
                final_tags.extend(new_tags)

        return sorted(list(set(final_tags)))


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
        editor_state = {
            "message": state,
            "rewriting": False,
            "rewrite_ready": False,
            "suggesting_tags": False,
            "suggested_tags": [],
        }
        session.default_buffer.read_only = Condition(
            lambda: editor_state["rewriting"] or editor_state["suggesting_tags"]
        )

        @bindings.add("c-d")
        def _(event) -> None:
            if editor_state["rewriting"] or editor_state["suggesting_tags"]:
                return
            event.current_buffer.validate_and_handle()

        @bindings.add("escape", "r")
        def _(event) -> None:
            if rewrite is None or editor_state["rewriting"] or editor_state["suggesting_tags"]:
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

        @bindings.add("escape", "s")
        def _(event) -> None:
            if suggest_tags is None or editor_state["rewriting"] or editor_state["suggesting_tags"]:
                return

            current_text = event.current_buffer.text
            editor_state["suggesting_tags"] = True
            editor_state["message"] = "Waiting for tag suggestions..."
            event.app.invalidate()

            async def suggest_task() -> None:
                try:
                    loop = asyncio.get_running_loop()
                    tags = await loop.run_in_executor(None, suggest_tags, current_text)
                except Exception as exc:  # pragma: no cover
                    editor_state["message"] = f"Suggestion failed: {exc}"
                    editor_state["suggesting_tags"] = False
                else:
                    editor_state["suggesting_tags"] = False
                    editor_state["suggested_tags"] = tags
                    editor_state["message"] = f"Tags suggested: {', '.join(tags)}" if tags else "No tags suggested."
                finally:
                    event.app.invalidate()

            event.app.create_background_task(suggest_task())

        prompt_text = "Diary update> " if not info_message else f"{info_message}\nDiary update> "
        final_text = session.prompt(
            prompt_text,
            default=initial_text,
            key_bindings=bindings,
            bottom_toolbar=lambda: status_toolbar(
                (
                    "Waiting..."
                    if (editor_state["rewriting"] or editor_state["suggesting_tags"])
                    else (
                        editor_state["message"]
                        + (
                            "  Alt+R rewrite"
                            if rewrite is not None and not editor_state["rewrite_ready"]
                            else ("  Alt+R rewrite again" if rewrite is not None else "")
                        )
                        + (
                            "  Alt+S suggest tags"
                            if suggest_tags is not None
                            else ""
                        )
                    )
                )
            ),
            in_thread=_prompt_should_run_in_thread(),
        )
        return final_text, editor_state["suggested_tags"]
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


def show_diary_entry(
    title: str,
    body: str,
    previous_entry=None,
    next_entry=None,
    pick_entry=None,
    get_tags=None,
    toggle_todo=None,
    update_section=None,
    set_tags=None,
    get_all_tags=None,
    suggest_tags=None,
    delete_section=None,
) -> None:
    require_prompt_toolkit()

    def inject_tags(content, tags_data):
        if not tags_data:
            return content
        lines = content.splitlines()
        for i, line in enumerate(lines):
            heading_match = SHOW_SECTION_HEADING_RE.match(line.strip())
            if not heading_match:
                continue
            heading = heading_match.group("heading")
            tags = tags_data.get(heading, [])
            if tags:
                lines[i] = f"## {heading} {{{', '.join(tags)}}}"
        return "\n".join(lines)

    def get_current_section(content, line_no):
        lines = content.splitlines()
        heading_line_index = None

        # Traverse backwards to find the containing heading.
        for i in range(line_no - 1, -1, -1):
            if SHOW_SECTION_HEADING_RE.match(lines[i].strip()):
                heading_line_index = i
                break

        if heading_line_index is None:
            return None, ""

        heading_match = SHOW_SECTION_HEADING_RE.match(lines[heading_line_index].strip())
        if not heading_match:
            return None, ""
        current_heading = heading_match.group("heading")

        current_body_lines = []
        for i in range(heading_line_index + 1, len(lines)):
            if SHOW_SECTION_HEADING_RE.match(lines[i].strip()):
                break
            current_body_lines.append(lines[i])

        return current_heading, "\n".join(current_body_lines).strip()

    current_tags = get_tags(title) if get_tags else {}
    raw_content_state = {"body": body}
    display_body = inject_tags(raw_content_state["body"], current_tags)

    text_area = TextArea(
        text=display_body,
        read_only=True,
        scrollbar=True,
        focusable=True,
        wrap_lines=True,
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

    def get_help_text():
        if picker_state["open"]:
            return HTML("<b>Move:</b> Up / Down  <b>Select:</b> Enter  <b>Cancel:</b> Esc")
        return HTML(
            "<b>Browse:</b> Arrows  "
            "<b>Jump:</b> [ / ] / g  "
            "<b>Toggle TODO:</b> Space  "
            "<b>Edit:</b> e  "
            "<b>Tags:</b> t  "
            "<b>Delete:</b> d  "
            "<b>Exit:</b> q / Esc"
        )

    help_bar = Window(
        height=1,
        content=FormattedTextControl(get_help_text),
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

    def update_view(new_title, new_content):
        frame.title = new_title
        raw_content_state["body"] = new_content
        tags_data = get_tags(new_title) if get_tags else {}
        text_area.text = inject_tags(new_content, tags_data)
        text_area.buffer.cursor_position = 0

    def move_to_entry(loader) -> None:
        if loader is None:
            return
        target = loader(frame.title)
        if target is None:
            return
        next_title, next_body = target
        update_view(next_title, next_body)

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

    @bindings.add("space", filter=~picker_visible)
    def _(event) -> None:
        if toggle_todo is None:
            return
        line_no = text_area.buffer.document.cursor_position_row + 1
        new_content = toggle_todo(frame.title, line_no)
        if new_content is not None:
            cursor_pos = text_area.buffer.cursor_position
            raw_content_state["body"] = new_content
            tags_data = get_tags(frame.title) if get_tags else {}
            text_area.text = inject_tags(new_content, tags_data)
            text_area.buffer.cursor_position = cursor_pos

    @bindings.add("e", filter=~picker_visible)
    async def _(event) -> None:
        if update_section is None:
            return
        line_no = text_area.buffer.document.cursor_position_row + 1
        heading, section_body = get_current_section(raw_content_state["body"], line_no)
        if not heading:
            return

        def suggest_tags_callback(text):
            if suggest_tags:
                return suggest_tags(text)
            return []

        # Use run_in_terminal to avoid hanging the event loop
        result = await run_in_terminal(
            lambda: launch_editor(
                initial_text=section_body,
                state=f"Editing {heading}",
                suggest_tags=suggest_tags_callback,
            )
        )
        
        if result:
            new_body, _ = result
            if new_body:
                updated_content = update_section(frame.title, heading, new_body)
                if updated_content:
                    update_view(frame.title, updated_content)

    @bindings.add("t", filter=~picker_visible)
    async def _(event) -> None:
        if set_tags is None or get_all_tags is None:
            return
        line_no = text_area.buffer.document.cursor_position_row + 1
        heading, _ = get_current_section(raw_content_state["body"], line_no)
        if not heading:
            return
        
        all_tags, top_level, all_paths = get_all_tags()
        current_section_tags = (get_tags(frame.title) if get_tags else {}).get(heading, [])
        
        # Use run_in_terminal for the tagging dialog too
        new_tags = await run_in_terminal(
            lambda: prompt_for_section_tags(
                all_tags,
                top_level,
                all_paths,
                initial_tags=current_section_tags,
            )
        )
        
        if new_tags is not None and new_tags != current_section_tags:
            set_tags(frame.title, heading, new_tags)
            update_view(frame.title, raw_content_state["body"])

    @bindings.add("d", filter=~picker_visible)
    async def _(event) -> None:
        if delete_section is None:
            return
        line_no = text_area.buffer.document.cursor_position_row + 1
        heading, _ = get_current_section(raw_content_state["body"], line_no)
        if not heading:
            return

        confirmed = await run_in_terminal(
            lambda: button_dialog(
                title="Delete Section",
                text=(
                    f"Delete section {heading} from {frame.title}?\n\n"
                    "This also removes its HTFS resource and tags."
                ),
                buttons=[
                    ("Delete", True),
                    ("Cancel", False),
                ],
                style=DIALOG_STYLE,
            ).run(in_thread=_prompt_should_run_in_thread())
        )
        if not confirmed:
            return

        updated_content = delete_section(frame.title, heading)
        if updated_content is not None:
            update_view(frame.title, updated_content)

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
        new_title = selected.file_path.name
        new_body = selected.file_path.read_text(encoding="utf-8").rstrip()
        update_view(new_title, new_body)
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
