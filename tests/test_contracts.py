"""Acceptance properties; see docs/Testing.md for catalog and contract mappings."""

import asyncio
from types import SimpleNamespace

import pytest
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.keys import Keys

from diary_agent_app import commands, core, llm, ui, viewer
from diary_agent_app.markdown import read_markdown
from diary_agent_app.service import DiaryAgent


@pytest.mark.parametrize("model", [None, "local-model"])
def test_unattended_capture_preserves_exact_input_and_duplicates(
    tmp_path, monkeypatch, model
):
    """CAP-06/10/11/13: unconsented saves use exact string equality."""
    monkeypatch.setattr(commands.sys.stdin, "isatty", lambda: False)
    agent = DiaryAgent(tmp_path, model)
    text = "  Ω note  \n- [ ] Call tomorrow [priority: unusual]  \n\n"
    for _ in range(2):
        assert commands.run_capture(agent, text, "31_12_2026") == 0
    saved = read_markdown(tmp_path / "31_12_2026.md")
    assert saved.count(text) == 2
    assert len(agent.parse_day_sections(tmp_path / "31_12_2026.md")) == 2


@pytest.mark.parametrize(
    "accept,proposal", [(False, "Changed"), (True, "Changed"), (True, "")]
)
def test_text_capture_consent_is_specific_to_displayed_proposal(
    tmp_path, monkeypatch, capsys, accept, proposal
):
    """CAP-10/12/13: accept uses displayed proposal; decline retains original."""
    monkeypatch.setattr(commands.sys.stdin, "isatty", lambda: True)
    agent = DiaryAgent(tmp_path, "local-model")
    monkeypatch.setattr(agent, "synthesize_entry", lambda text, day_text=None: proposal)
    monkeypatch.setattr(commands, "prompt_yes_no", lambda prompt: accept)
    assert commands.run_capture(agent, "Original  ", "01_01_2027") == 0
    assert "Proposed content" in capsys.readouterr().out
    path = tmp_path / "01_01_2027.md"
    expected = proposal if accept else "Original  "
    assert path.exists() == bool(expected)
    if expected:
        assert read_markdown(path).endswith(expected + "\n")


def test_failed_text_rewrite_retains_original(tmp_path, monkeypatch):
    """CAP-13: generation failure cannot mutate original content."""
    monkeypatch.setattr(commands.sys.stdin, "isatty", lambda: True)
    agent = DiaryAgent(tmp_path, "local-model")

    def fail(*args, **kwargs):
        raise RuntimeError("service unavailable")

    monkeypatch.setattr(agent, "synthesize_entry", fail)
    commands.run_capture(agent, "Original  ", "01_01_2027")
    assert read_markdown(tmp_path / "01_01_2027.md").endswith("Original  \n")


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("action", ["edit", "delete"])
def test_section_mutation_preserves_all_outside_bytes(tmp_path, newline, action):
    """VIEW-08/09, D-06: independent prefix/suffix oracle, exact UTF-8 bytes."""
    agent = DiaryAgent(tmp_path, None)
    path = tmp_path / "01_01_2027.md"
    prefix = newline.join(["Preamble Ω  ", "## 09:00", "", "first  ", "", ""])
    header = "## 10:00" + newline
    target = newline + "old" + newline * 2
    suffix = "## 11:00" + newline * 2 + "last  "
    path.write_bytes((prefix + header + target + suffix).encode())
    if action == "edit":
        body = "  New Ω\n- [ ] tomorrow  "
        agent.update_section(path, "10:00", body)
        actual = path.read_bytes()
        assert actual.startswith((prefix + header).encode())
        assert actual.endswith(suffix.encode())
        assert body.encode() in actual
    else:
        commands.get_htfs_adapter(tmp_path)
        agent.delete_section(path, "10:00")
        assert path.read_bytes() == (prefix + suffix).encode()


@pytest.mark.parametrize("action", ["edit", "delete", "tag"])
def test_duplicate_section_identity_blocks_mutations(tmp_path, action):
    """DATA-08: duplicate IDs remain viewable but cannot identify a mutation."""
    path = tmp_path / "01_01_2027.md"
    original = b"## 10:00\n\nfirst\n## 10:00\n\nsecond\n"
    path.write_bytes(original)
    agent = DiaryAgent(tmp_path, None)
    sections = agent.parse_day_sections(path)
    assert len(sections) == 2
    with pytest.raises(RuntimeError, match="Ambiguous"):
        if action == "edit":
            agent.update_section(path, "10:00", "replacement")
        elif action == "delete":
            agent.delete_section(path, "10:00")
        else:
            agent.set_section_tags(sections[0], [])
    assert path.read_bytes() == original
    assert not (tmp_path / ".tagfs.db").exists()


def test_navigation_orders_calendar_dates_and_excludes_invalid_files(tmp_path):
    """DATA-06/VIEW-03: TotalOrder le maps dates, observed through ordered paths.

    urn:csabs:operation/TotalOrder-basis-le; TotalOrder-transitive.
    Three dates include year/month boundaries. Filename
    lexical order is deliberately different; expected order is literal.
    """
    ordered = ["31_12_2025.md", "01_01_2026.md", "02_02_2026.md"]
    for name in ordered + ["notes.md", "31_02_2026.md", "1_01_2026.md"]:
        (tmp_path / name).write_text("- [ ] keep history\n")
    nested = tmp_path / "03_02_2026.md"
    nested.mkdir()
    (nested / "hidden.md").write_text("- [ ] nested task\n")
    agent = DiaryAgent(tmp_path, None)
    assert [p.name for p in agent.dated_diary_files()] == ordered
    assert [o.file_path.name for o in agent.entry_options()] == ordered[::-1]
    assert agent.latest_diary_file().name == ordered[-1]
    for index, name in enumerate(ordered):
        for step in [-1, 1]:
            result = agent.adjacent_entry(tmp_path / name, step)
            neighbor = index + step
            assert (result[0] if result else None) == (
                ordered[neighbor] if 0 <= neighbor < 3 else None
            )
    assert len(agent.scan_pending_tasks()) == 6


@pytest.mark.parametrize(
    "day",
    ["31_02_2026", "00_01_2026", "2026-01-01", "1_01_2026", "9999999999999999999"],
)
def test_invalid_day_is_rejected(day):
    """DATA-04: syntax, calendar validity and representable range are guards."""
    with pytest.raises(RuntimeError):
        core.parse_explicit_day_input(day)


def test_todo_completion_changes_only_selected_state_and_rejects_stale_batch(tmp_path):
    """TODO-03/10: exact source snapshots guard a whole completion batch."""
    first = tmp_path / "notes.md"
    second = tmp_path / "01_01_2027.md"
    raw = b"Preamble\r\n  - [ ] Call tomorrow [priority: odd]  \r\n- [ ] Other"
    first.write_bytes(raw)
    second.write_text("- [ ] Second\n")
    agent = DiaryAgent(tmp_path, None)
    tasks = agent.scan_pending_tasks()
    selected = next(task for task in tasks if task.file_path == first)
    assert agent.mark_tasks_complete([selected, selected]) == 1
    assert first.read_bytes() == raw.replace(b"[ ]", b"[x]", 1)
    assert agent.toggle_todo(first, 2) is not None
    assert first.read_bytes() == raw
    tasks = agent.scan_pending_tasks()
    second.write_text("external change\n- [ ] Second\n")
    with pytest.raises(RuntimeError, match="reselect"):
        agent.mark_tasks_complete(tasks)
    assert first.read_bytes() == raw
    assert second.read_text() == "external change\n- [ ] Second\n"


def test_unattended_todos_lists_without_prompting_or_mutating(
    tmp_path, monkeypatch, capsys
):
    """TODO-09: redirected input is a read-only observation."""
    path = tmp_path / "notes.md"
    path.write_text("- [ ] Call tomorrow\n")
    monkeypatch.setattr(commands.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr("builtins.input", lambda *a: pytest.fail("unattended prompt"))
    assert commands.run_todos(DiaryAgent(tmp_path, None)) == 0
    assert "Call tomorrow" in capsys.readouterr().out
    assert path.read_text() == "- [ ] Call tomorrow\n"


@pytest.mark.parametrize("selection", ["1,9", "0", "-1", "1,no", "1,"])
def test_invalid_todo_selection_rejects_entire_batch(tmp_path, monkeypatch, selection):
    """TODO-03: invalid or out-of-range selections never partially apply."""
    path = tmp_path / "notes.md"
    path.write_text("- [ ] Call\n")
    monkeypatch.setattr(commands.sys.stdin, "isatty", lambda: True)

    def no_toolkit():
        raise RuntimeError("not installed")

    monkeypatch.setattr(ui, "require_prompt_toolkit", no_toolkit)
    monkeypatch.setattr("builtins.input", lambda *a: selection)
    assert commands.run_todos(DiaryAgent(tmp_path, None)) == 1
    assert path.read_text() == "- [ ] Call\n"


def test_only_proposed_open_todos_expand_dates(tmp_path):
    """TODO-02/08, CAP-13: display cleanup before consent, DD-MM-YYYY."""
    agent = DiaryAgent(tmp_path, "local-model")
    source = "- [ ] Call tomorrow [due: Friday]\n- [x] Finished today\n- note tomorrow"
    proposal = agent.prepare_rewrite_for_review(source, "26_03_2026")
    assert (
        proposal
        == "- [ ] Call 27-03-2026 [due: 27-03-2026]\n- [x] Finished today\n- note tomorrow"
    )
    assert not list(tmp_path.glob("*.md"))


def press(bindings, event, *keys):
    """Drive real prompt_toolkit bindings without a live terminal."""
    bindings.get_bindings_for_keys(keys)[-1].handler(event)


@pytest.mark.parametrize("decision", ["y", "n", "error"])
def test_editor_reviews_rewrite_before_draft_replacement(monkeypatch, decision):
    """CAP-04/06: single-operation lifecycle; failure/rejection retain draft."""

    class Session:
        def __init__(self, **kwargs):
            self.default_buffer = Buffer()

        def prompt(self, *args, **kwargs):
            buffer = self.default_buffer
            buffer.text = "Original  "
            pending = []
            submitted = []
            app = SimpleNamespace(
                invalidate=lambda: None, create_background_task=pending.append
            )
            event = SimpleNamespace(app=app, current_buffer=buffer)
            bindings = kwargs["key_bindings"]
            buffer.validate_and_handle = lambda: submitted.append(buffer.text)
            press(bindings, event, Keys.Escape, "r")
            assert buffer.read_only()
            press(bindings, event, Keys.ControlD)
            press(bindings, event, Keys.Escape, "r")
            assert len(pending) == 1 and not submitted

            async def finish():
                loop = asyncio.get_running_loop()

                def executor(_executor, work, text):
                    future = loop.create_future()

                    def resolve():
                        try:
                            future.set_result(work(text))
                        except Exception as exc:
                            future.set_exception(exc)

                    loop.call_soon(resolve)
                    return future

                monkeypatch.setattr(loop, "run_in_executor", executor)
                await pending.pop()

            asyncio.run(finish())
            if decision != "error":
                assert buffer.text == "Complete proposal" and buffer.read_only()
                press(bindings, event, Keys.ControlD)
                assert not submitted
                press(bindings, event, Keys.Escape, decision)
            assert not buffer.read_only()
            press(bindings, event, Keys.ControlD)
            assert submitted == [
                "Complete proposal" if decision == "y" else "Original  "
            ]
            return buffer.text

    monkeypatch.setattr(ui, "PromptSession", Session)

    def rewrite(text):
        assert text == "Original  "
        if decision == "error":
            raise RuntimeError("offline")
        return "Complete proposal"

    final, tags = ui.launch_editor(rewrite=rewrite)
    assert final == ("Complete proposal" if decision == "y" else "Original  ")
    assert tags == []


@pytest.mark.parametrize(
    "selection,expected", [(None, ["Old"]), ([], []), (["New"], ["New"])]
)
def test_viewer_tag_cancel_clear_replace_are_distinct(
    tmp_path, monkeypatch, selection, expected
):
    """TAG-07: OptionType none/some/case maps None versus present lists.

    urn:csabs:axiom/option-case-none and option-case-some. Observation is the
    actual persisted HTFS association set, not callback invocation counts.
    """
    path = tmp_path / "01_01_2027.md"
    path.write_text("## 10:00\n\nA note\n")
    agent = DiaryAgent(tmp_path, None)
    section = agent.section_for_id(path.name + "#10:00")
    commands.get_htfs_adapter(tmp_path)
    agent.set_section_tags(section, ["Old"])

    async def in_terminal(callback):
        return callback()

    monkeypatch.setattr(viewer, "run_in_terminal", in_terminal)
    monkeypatch.setattr(viewer, "prompt_for_section_tags", lambda *a, **k: selection)

    def run(app, **kwargs):
        event = SimpleNamespace(app=app)
        binding = app.key_bindings.get_bindings_for_keys(("t",))[-1]
        asyncio.run(binding.handler(event))

    monkeypatch.setattr(viewer.Application, "run", run)
    viewer.show_diary_entry(
        path.name,
        path.read_text(),
        get_tags=lambda title: agent.get_section_tags(tmp_path / title),
        get_all_tags=lambda: (["Old", "New"], [], []),
        set_tags=lambda title, heading, tags: agent.set_section_tags(section, tags),
    )
    assert agent.get_section_tags(path)["10:00"] == expected


@pytest.mark.parametrize("model", [None, "local-model"])
def test_editor_capture_saves_final_buffer_without_postprocessing(
    tmp_path, monkeypatch, model
):
    """CAP-02/06/07: callbacks require a model; final draft stays verbatim."""
    agent = DiaryAgent(tmp_path, model)
    final = "  Ω draft  \n- [ ] Call tomorrow  \n\n"

    def editor(**kwargs):
        assert (kwargs["rewrite"] is not None) == bool(model)
        assert (kwargs["suggest_tags"] is not None) == bool(model)
        return final, []

    monkeypatch.setattr(commands, "launch_editor", editor)
    monkeypatch.setattr(commands, "prompt_for_section_tags", lambda *a, **k: None)
    assert commands.run_capture(agent, day_text="01_01_2027") == 0
    assert read_markdown(tmp_path / "01_01_2027.md").endswith(final)


@pytest.mark.parametrize(
    "raw,confirmed,expected",
    [
        (None, False, None),
        ("", False, []),
        ("Existing", False, ["Existing"]),
        ("New", False, None),
        ("New", True, ["New"]),
    ],
)
def test_tag_prompt_requires_explicit_creation_consent(
    monkeypatch, raw, confirmed, expected
):
    """TAG-03/07: cancel, accepted-empty, existing and confirmed-new results."""
    monkeypatch.setattr(ui.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(ui, "_tag_input_dialog", lambda *a: raw)
    monkeypatch.setattr(
        ui, "button_dialog", lambda **k: SimpleNamespace(run=lambda **kw: confirmed)
    )
    assert ui.prompt_for_section_tags(["Existing"], [], ["Existing"]) == expected


def test_viewer_is_read_only_and_boundary_navigation_is_noop(tmp_path, monkeypatch):
    """VIEW-02/03: drive actual bindings and inspect the presented document."""
    from prompt_toolkit.buffer import EditReadOnlyBuffer

    early = tmp_path / "31_12_2026.md"
    late = tmp_path / "01_01_2027.md"
    early.write_text("Earlier")
    late.write_text("Later")
    agent = DiaryAgent(tmp_path, None)

    def run(app, **kwargs):
        event = SimpleNamespace(app=app)
        buffer = app.layout.current_buffer
        with pytest.raises(EditReadOnlyBuffer):
            buffer.insert_text("accidental typing")
        for key, expected in [
            ("[", "Earlier"),
            ("]", "Later"),
            ("]", "Later"),
            ("[", "Earlier"),
        ]:
            press(app.key_bindings, event, key)
            assert buffer.text == expected

    monkeypatch.setattr(viewer.Application, "run", run)
    viewer.show_diary_entry(
        early.name,
        early.read_text(),
        previous_entry=lambda title: agent.adjacent_entry(tmp_path / title, -1),
        next_entry=lambda title: agent.adjacent_entry(tmp_path / title, 1),
    )


def test_backfilled_rewrite_uses_target_day_context(tmp_path, monkeypatch):
    """CAP-03, DATA-05: model receives target history rather than another day."""
    (tmp_path / "26_03_2026.md").write_text("Target history")
    (tmp_path / "27_03_2026.md").write_text("Unrelated history")
    prompts = []

    def chat(**kwargs):
        prompts.extend(message["content"] for message in kwargs["messages"])
        return {"message": {"content": "- New note"}}

    monkeypatch.setattr(llm, "ollama", SimpleNamespace(chat=chat))
    assert (
        DiaryAgent(tmp_path, "local-model").synthesize_entry("Raw note", "26_03_2026")
        == "- New note"
    )
    combined = "\n".join(prompts)
    assert "Target history" in combined and "Raw note" in combined
    assert "Unrelated history" not in combined
