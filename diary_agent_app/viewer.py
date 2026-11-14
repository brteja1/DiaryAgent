"""Read-only day viewer and explicit navigation/mutation actions."""

from __future__ import annotations

from .models import DiaryEntryOption
from .markdown import DiaryDocument, section_heading
from .ui import (
    Application,
    run_in_terminal,
    HSplit,
    Layout,
    ConditionalContainer,
    Window,
    FormattedTextControl,
    Condition,
    Box,
    Frame,
    TextArea,
    HTML,
    KeyBindings,
    button_dialog,
    DIALOG_STYLE,
    require_prompt_toolkit,
    _prompt_should_run_in_thread,
    launch_editor,
    prompt_for_section_tags,
)


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
        for index, line in enumerate(lines):
            heading = section_heading(line)
            tags = tags_data.get(heading, [])
            if tags:
                lines[index] = f"## {heading} {{{', '.join(tags)}}}"
        return "\n".join(lines)

    def get_current_section(content, line_no):
        document = DiaryDocument.parse(content)
        span = document.section_at_line(line_no)
        if span is None:
            return None, ""
        document.unique_section(span.heading)
        return span.heading, document.body(span).strip()

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
            return HTML(
                "<b>Move:</b> Up / Down  <b>Select:</b> Enter  <b>Cancel:</b> Esc"
            )
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
    @bindings.add("escape")
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
        current_section_tags = (get_tags(frame.title) if get_tags else {}).get(
            heading, []
        )

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
            picker_state["selected"] = min(
                picker_state["selected"] + 1, len(matches) - 1
            )
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
