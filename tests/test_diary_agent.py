import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import diary_agent


def test_parse_config_text_ignores_comments_and_invalid_lines():
    parsed = diary_agent.parse_config_text(
        """
        # comment
        diary_path = /tmp/diary
        invalid line
        llm_model = llama3
        extra=value=with=equals
        """
    )

    assert parsed == {
        "diary_path": "/tmp/diary",
        "llm_model": "llama3",
        "extra": "value=with=equals",
    }


def test_load_or_initialize_config_reads_required_entries(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    config_path = fake_home / ".config" / "diary_agent" / "config.txt"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "diary_path=~/journal\nllm_model=qwen2.5\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(diary_agent.Path, "home", lambda: fake_home)
    monkeypatch.setenv("HOME", str(fake_home))

    config = diary_agent.load_or_initialize_config()

    assert config.diary_dir == fake_home / "journal"
    assert config.llm_model == "qwen2.5"


def test_load_or_initialize_config_non_interactive_missing_values_raises(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    config_path = fake_home / ".config" / "diary_agent" / "config.txt"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("diary_path=\nllm_model=\n", encoding="utf-8")
    monkeypatch.setattr(diary_agent.Path, "home", lambda: fake_home)
    monkeypatch.setattr(diary_agent.sys.stdin, "isatty", lambda: False)

    with pytest.raises(RuntimeError, match="Missing or invalid config"):
        diary_agent.load_or_initialize_config()


def test_ensure_storage_creates_configured_diary_directory(tmp_path):
    diary_dir = tmp_path / "notes"
    agent = diary_agent.DiaryAgent(diary_dir=diary_dir, model="test-model")

    agent.ensure_storage()

    assert diary_dir.exists()
    assert diary_dir.is_dir()


def test_append_entry_appends_to_existing_daily_file(tmp_path):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    today = dt.date(2026, 3, 26)
    existing_path = agent.today_file(today)
    existing_path.write_text("- first note\n", encoding="utf-8")

    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return today

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(diary_agent.dt, "date", FixedDate)
    try:
        path, appended = agent.append_entry("- second note")
    finally:
        monkeypatch.undo()

    assert path == existing_path
    assert appended is True
    assert existing_path.read_text(encoding="utf-8") == "- first note\n\n- second note\n"


def test_append_entry_skips_reworded_duplicate_status_lines(tmp_path):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    today = dt.date(2026, 3, 26)
    existing_path = agent.today_file(today)
    existing_path.write_text(
        "- Worked on login flow bug for the API service.\n",
        encoding="utf-8",
    )

    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return today

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(diary_agent.dt, "date", FixedDate)
    try:
        path, appended = agent.append_entry("- Worked on the login flow bug for API service.")
    finally:
        monkeypatch.undo()

    assert path == existing_path
    assert appended is False
    assert existing_path.read_text(encoding="utf-8") == "- Worked on login flow bug for the API service.\n"


def test_append_entry_skips_reworded_duplicate_lines_within_same_capture(tmp_path):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    today = dt.date(2026, 3, 26)
    existing_path = agent.today_file(today)

    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return today

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(diary_agent.dt, "date", FixedDate)
    try:
        path, appended = agent.append_entry(
            "- Finished API auth cleanup for the mobile client.\n"
            "- Finished the API auth cleanup for mobile client.\n"
            "- Added regression tests for token refresh.\n"
        )
    finally:
        monkeypatch.undo()

    assert path == existing_path
    assert appended is True
    assert existing_path.read_text(encoding="utf-8") == (
        "- Finished API auth cleanup for the mobile client.\n"
        "- Added regression tests for token refresh.\n"
    )


def test_run_capture_reports_duplicate_update(monkeypatch, tmp_path, capsys):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    monkeypatch.setattr(agent, "ensure_storage", lambda: None)
    monkeypatch.setattr(agent, "synthesize_entry", lambda _text: "- Existing status update")
    monkeypatch.setattr(
        agent,
        "review_entry_todos",
        lambda entry, interactive: (entry, []),
    )
    monkeypatch.setattr(agent, "append_entry", lambda _entry: (tmp_path / "26_03_2026.md", False))

    exit_code = diary_agent.run_capture(agent, raw_text="duplicate update")

    assert exit_code == 0
    assert capsys.readouterr().out == "This update has already been added.\n"


def test_read_today_context_returns_existing_daily_content(tmp_path):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    today = dt.date(2026, 3, 26)
    target = agent.today_file(today)
    target.write_text("- current context\n\n- more context\n", encoding="utf-8")

    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return today

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(diary_agent.dt, "date", FixedDate)
    try:
        context = agent.read_today_context()
    finally:
        monkeypatch.undo()

    assert context == "- current context\n\n- more context"


def test_scan_pending_tasks_reads_unchecked_todos_from_all_markdown_files(tmp_path):
    (tmp_path / "25_03_2026.md").write_text(
        "- [ ] first task\n- [x] done task\n",
        encoding="utf-8",
    )
    (tmp_path / "26_03_2026.md").write_text(
        "notes\n- [ ] second task\n",
        encoding="utf-8",
    )
    (tmp_path / "ignore.txt").write_text("- [ ] ignored\n", encoding="utf-8")
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")

    tasks = agent.scan_pending_tasks()

    assert [(task.file_path.name, task.line_number, task.text) for task in tasks] == [
        ("25_03_2026.md", 1, "first task"),
        ("26_03_2026.md", 2, "second task"),
    ]


def test_mark_tasks_complete_rewrites_selected_unchecked_tasks(tmp_path):
    file_path = tmp_path / "26_03_2026.md"
    file_path.write_text(
        "- [ ] first task\n- [ ] second task\n- [x] already done\n",
        encoding="utf-8",
    )
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    tasks = agent.scan_pending_tasks()

    updated = agent.mark_tasks_complete([tasks[1]])

    assert updated == 1
    assert file_path.read_text(encoding="utf-8") == (
        "- [ ] first task\n- [x] second task\n- [x] already done\n"
    )


def test_dedupe_entry_removes_existing_and_new_duplicate_open_todos(tmp_path):
    (tmp_path / "25_03_2026.md").write_text(
        "- [ ] Buy milk\n",
        encoding="utf-8",
    )
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")

    deduped = agent.dedupe_entry(
        "- [ ] buy milk!\n"
        "- [ ] Call mom\n"
        "- [ ] call mom\n"
        "- regular note\n"
    )

    assert deduped == "- [ ] Call mom\n- regular note"


def test_review_entry_todos_skips_similar_todos_in_non_interactive_mode(monkeypatch, tmp_path):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    existing = diary_agent.PendingTask(
        file_path=Path("25_03_2026.md"),
        line_number=3,
        text="Submit expenses",
    )
    match = diary_agent.SimilarTodoMatch(
        candidate_text="Submit expense report",
        existing_task=existing,
    )
    monkeypatch.setattr(agent, "find_similar_open_todo", lambda text: match if "expense" in text else None)
    monkeypatch.setattr(diary_agent, "confirm_similar_todo_addition_cli", lambda _match: False)

    entry, skipped = agent.review_entry_todos(
        "- [ ] Submit expense report\n- regular note",
        interactive=False,
    )

    assert entry == "- regular note"
    assert skipped == [match]


def test_search_returns_best_matching_history_chunks(tmp_path):
    (tmp_path / "25_03_2026.md").write_text(
        "- fixed login bug\n\n- planned team lunch\n",
        encoding="utf-8",
    )
    (tmp_path / "26_03_2026.md").write_text(
        "- login bug resurfaced in staging\n",
        encoding="utf-8",
    )
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")

    results = agent.search("login bug", limit=2)

    assert len(results) == 2
    assert {path.name for path, _chunk, _score in results} == {
        "25_03_2026.md",
        "26_03_2026.md",
    }
    assert all("login bug" in chunk.lower() for _path, chunk, _score in results)
    assert all(score > 0 for _path, _chunk, score in results)


def test_parse_explicit_day_input_accepts_dd_mm_yyyy():
    normalized = diary_agent.parse_explicit_day_input("05_03_2026")

    assert normalized == "05_03_2026"


def test_parse_explicit_day_input_rejects_non_dd_mm_yyyy():
    with pytest.raises(RuntimeError, match="Use dd_mm_yyyy"):
        diary_agent.parse_explicit_day_input("5 March 2026")


def test_adjacent_entry_returns_previous_and_next_diary_files(tmp_path):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    (tmp_path / "25_03_2026.md").write_text("- first\n", encoding="utf-8")
    current = tmp_path / "26_03_2026.md"
    current.write_text("- current\n", encoding="utf-8")
    (tmp_path / "27_03_2026.md").write_text("- last\n", encoding="utf-8")

    assert agent.adjacent_entry(current, -1) == ("25_03_2026.md", "- first")
    assert agent.adjacent_entry(current, 1) == ("27_03_2026.md", "- last")


def test_adjacent_entry_returns_none_when_no_neighbor_exists(tmp_path):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    only = tmp_path / "26_03_2026.md"
    only.write_text("- current\n", encoding="utf-8")

    assert agent.adjacent_entry(only, -1) is None
    assert agent.adjacent_entry(only, 1) is None


def test_run_show_day_opens_requested_file_in_ui(monkeypatch, tmp_path):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    target = tmp_path / "05_03_2026.md"
    target.write_text("- Met with product\n- [ ] Send notes\n", encoding="utf-8")
    monkeypatch.setattr(agent, "ensure_storage", lambda: None)
    monkeypatch.setattr(
        agent,
        "file_for_day_input",
        lambda day_text: target,
    )
    shown = {}
    monkeypatch.setattr(
        diary_agent,
        "show_diary_entry",
        lambda title, body, previous_entry=None, next_entry=None: shown.update(
            {
                "title": title,
                "body": body,
                "previous": previous_entry("05_03_2026.md") if previous_entry else None,
                "next": next_entry("05_03_2026.md") if next_entry else None,
            }
        ),
    )
    monkeypatch.setattr(agent, "adjacent_entry", lambda path, step: ("04_03_2026.md", "- prior") if step < 0 else ("06_03_2026.md", "- next"))

    exit_code = diary_agent.run_show_day(agent, day_text="05_03_2026")

    assert exit_code == 0
    assert shown == {
        "title": "05_03_2026.md",
        "body": "- Met with product\n- [ ] Send notes",
        "previous": ("04_03_2026.md", "- prior"),
        "next": ("06_03_2026.md", "- next"),
    }


def test_run_show_day_defaults_to_today_when_day_omitted(monkeypatch, tmp_path):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    today = dt.date(2026, 3, 28)
    target = agent.today_file(today)
    target.write_text("- Defaulted to today\n", encoding="utf-8")
    monkeypatch.setattr(agent, "ensure_storage", lambda: None)

    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return today

    monkeypatch.setattr(diary_agent.dt, "date", FixedDate)
    shown = {}
    monkeypatch.setattr(
        diary_agent,
        "show_diary_entry",
        lambda title, body, previous_entry=None, next_entry=None: shown.update({"title": title, "body": body}),
    )

    exit_code = diary_agent.run_show_day(agent)

    assert exit_code == 0
    assert shown == {
        "title": "28_03_2026.md",
        "body": "- Defaulted to today",
    }


def test_run_show_day_falls_back_to_stdout_when_ui_unavailable(monkeypatch, tmp_path, capsys):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    target = tmp_path / "05_03_2026.md"
    target.write_text("- Met with product\n- [ ] Send notes\n", encoding="utf-8")
    monkeypatch.setattr(agent, "ensure_storage", lambda: None)
    monkeypatch.setattr(
        agent,
        "file_for_day_input",
        lambda day_text: target,
    )
    monkeypatch.setattr(
        diary_agent,
        "show_diary_entry",
        lambda title, body, previous_entry=None, next_entry=None: (_ for _ in ()).throw(RuntimeError("missing prompt_toolkit")),
    )

    exit_code = diary_agent.run_show_day(agent, day_text="05_03_2026")

    assert exit_code == 0
    assert (
        capsys.readouterr().out
        == "[05_03_2026.md]\n- Met with product\n- [ ] Send notes\n"
    )


def test_run_show_day_reports_missing_file(monkeypatch, tmp_path, capsys):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    target = tmp_path / "05_03_2026.md"
    monkeypatch.setattr(agent, "ensure_storage", lambda: None)
    monkeypatch.setattr(
        agent,
        "file_for_day_input",
        lambda day_text: target,
    )

    exit_code = diary_agent.run_show_day(agent, day_text="05_03_2026")

    assert exit_code == 0
    assert capsys.readouterr().out == "No diary entry found for 05_03_2026.\n"


def test_build_parser_accepts_show_without_day():
    parser = diary_agent.build_parser()

    args = parser.parse_args(["show"])

    assert args.command == "show"
    assert args.day is None


def test_organize_day_entry_fallback_groups_items(monkeypatch):
    monkeypatch.setattr(diary_agent.llm, "ollama", None)

    organized = diary_agent.llm.organize_day_entry(
        model="test-model",
        body="- [ ] Send notes\n- Met with product\n- [x] Closed ticket\nfreeform thought",
    )

    assert organized == (
        "## Pending TODOs\n"
        "- [ ] Send notes\n\n"
        "## Completed TODOs\n"
        "- [x] Closed ticket\n\n"
        "## Notes\n"
        "- Met with product\n\n"
        "## Other\n"
        "- freeform thought"
    )


def test_organize_day_entry_prefixes_llm_output(monkeypatch):
    class FakeOllama:
        @staticmethod
        def chat(*, model, messages):
            return {
                "message": {
                    "content": "## Work\n- Met with product\n\n## Follow-ups\n- [ ] Send notes"
                }
            }

    monkeypatch.setattr(diary_agent.llm, "ollama", FakeOllama())

    organized = diary_agent.llm.organize_day_entry(
        model="test-model",
        body="- Met with product\n- [ ] Send notes",
    )

    assert organized == (
        "## Work\n"
        "- Met with product\n\n"
        "## Follow-ups\n"
        "- [ ] Send notes"
    )
