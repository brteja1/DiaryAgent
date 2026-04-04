import asyncio
import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import diary_agent
from diary_agent_app.htfs_adapter import HTFSAdapter
import diary_agent_app.ui as ui


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
    existing_path.write_text("## 09:15\n\n- first note\n", encoding="utf-8")

    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return today

    class FixedDateTime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 26, 14, 30)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(diary_agent.dt, "date", FixedDate)
    monkeypatch.setattr(diary_agent.dt, "datetime", FixedDateTime)
    try:
        path, appended = agent.append_entry("- second note")
    finally:
        monkeypatch.undo()

    assert path == existing_path
    assert appended is True
    assert existing_path.read_text(encoding="utf-8") == (
        "## 09:15\n\n"
        "- first note\n\n"
        "## 14:30\n\n"
        "- second note\n"
    )


def test_append_entry_skips_reworded_duplicate_status_lines(tmp_path):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    today = dt.date(2026, 3, 26)
    existing_path = agent.today_file(today)
    existing_path.write_text("## 09:15\n\n- Worked on login flow bug for the API service.\n", encoding="utf-8")

    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return today

    class FixedDateTime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 26, 14, 30)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(diary_agent.dt, "date", FixedDate)
    monkeypatch.setattr(diary_agent.dt, "datetime", FixedDateTime)
    try:
        path, appended = agent.append_entry("- Worked on the login flow bug for API service.")
    finally:
        monkeypatch.undo()

    assert path == existing_path
    assert appended is False
    assert existing_path.read_text(encoding="utf-8") == "## 09:15\n\n- Worked on login flow bug for the API service.\n"


def test_append_entry_skips_reworded_duplicate_lines_within_same_capture(tmp_path):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    today = dt.date(2026, 3, 26)
    existing_path = agent.today_file(today)

    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return today

    class FixedDateTime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 26, 14, 30)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(diary_agent.dt, "date", FixedDate)
    monkeypatch.setattr(diary_agent.dt, "datetime", FixedDateTime)
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
        "## 14:30\n\n"
        "- Finished API auth cleanup for the mobile client.\n"
        "- Added regression tests for token refresh.\n"
    )


def test_append_entry_preserves_nested_bullet_indentation(tmp_path):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    today = dt.date(2026, 3, 26)

    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return today

    class FixedDateTime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 26, 14, 30)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(diary_agent.dt, "date", FixedDate)
    monkeypatch.setattr(diary_agent.dt, "datetime", FixedDateTime)
    try:
        path, appended = agent.append_entry(
            "- Project work\n"
            "  - Finished auth cleanup\n"
            "  - Added regression coverage\n"
        )
    finally:
        monkeypatch.undo()

    assert appended is True
    assert path.read_text(encoding="utf-8") == (
        "## 14:30\n\n"
        "- Project work\n"
        "  - Finished auth cleanup\n"
        "  - Added regression coverage\n"
    )


def test_append_entry_verbatim_writes_final_text_without_flattening(tmp_path):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    today = dt.date(2026, 3, 26)

    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return today

    class FixedDateTime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 26, 14, 30)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(diary_agent.dt, "date", FixedDate)
    monkeypatch.setattr(diary_agent.dt, "datetime", FixedDateTime)
    try:
        path, appended = agent.append_entry_verbatim(
            "- Project work\n"
            "\n"
            "### user heading retained\n"
            "  - Finished auth cleanup\n"
        )
    finally:
        monkeypatch.undo()

    assert appended is True
    assert path.read_text(encoding="utf-8") == (
        "## 14:30\n\n"
        "- Project work\n"
        "\n"
        "### user heading retained\n"
        "  - Finished auth cleanup\n"
    )


def test_parse_day_sections_returns_timestamp_sections_with_stable_ids(tmp_path):
    file_path = tmp_path / "26_03_2026.md"
    file_path.write_text(
        "## 09:15\n\n"
        "- first note\n"
        "- [ ] first todo\n\n"
        "## 14:30\n\n"
        "- second note\n"
        "  - nested detail\n",
        encoding="utf-8",
    )
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")

    sections = agent.parse_day_sections(file_path)

    assert [(section.heading, section.body, section.section_id) for section in sections] == [
        (
            "09:15",
            "- first note\n- [ ] first todo",
            "26_03_2026.md#09:15",
        ),
        (
            "14:30",
            "- second note\n  - nested detail",
            "26_03_2026.md#14:30",
        ),
    ]


def test_parse_day_sections_ignores_text_before_first_timestamp_heading(tmp_path):
    file_path = tmp_path / "26_03_2026.md"
    file_path.write_text(
        "orphan text\n"
        "## 09:15\n\n"
        "- first note\n",
        encoding="utf-8",
    )
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")

    sections = agent.parse_day_sections(file_path)

    assert len(sections) == 1
    assert sections[0].heading == "09:15"
    assert sections[0].body == "- first note"


def test_section_for_id_returns_matching_section(tmp_path):
    file_path = tmp_path / "26_03_2026.md"
    file_path.write_text(
        "## 09:15\n\n"
        "- first note\n\n"
        "## 14:30\n\n"
        "- second note\n",
        encoding="utf-8",
    )
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")

    section = agent.section_for_id("26_03_2026.md#14:30")

    assert section is not None
    assert section.heading == "14:30"
    assert section.body == "- second note"
    assert section.section_id == "26_03_2026.md#14:30"


def test_section_for_id_returns_none_for_missing_section(tmp_path):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")

    assert agent.section_for_id("26_03_2026.md#14:30") is None


def test_htfs_adapter_maps_section_to_resource_path_and_back(tmp_path):
    file_path = tmp_path / "26_03_2026.md"
    section = diary_agent.DiarySection(
        file_path=file_path,
        heading="14:30",
        body="- second note",
    )
    adapter = HTFSAdapter(boundary=tmp_path)

    resource_path = adapter.resource_path_for_section(section)

    assert resource_path == f"{file_path.resolve()}#14:30"
    assert adapter.section_id_from_resource_path(resource_path) == "26_03_2026.md#14:30"


def test_htfs_adapter_loads_section_from_resource_path(tmp_path):
    file_path = tmp_path / "26_03_2026.md"
    file_path.write_text(
        "## 14:30\n\n"
        "- second note\n",
        encoding="utf-8",
    )
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    adapter = HTFSAdapter(boundary=tmp_path)

    section = adapter.load_section_by_resource_path(agent, f"{file_path.resolve()}#14:30")

    assert section is not None
    assert section.section_id == "26_03_2026.md#14:30"
    assert section.body == "- second note"


def test_htfs_adapter_reports_initialization_from_boundary_files(tmp_path):
    adapter = HTFSAdapter(boundary=tmp_path)

    assert adapter.is_initialized() is False

    (tmp_path / ".tagfs.db").write_text("", encoding="utf-8")

    assert adapter.is_initialized() is True


def test_build_parser_accepts_tags_apply_command():
    parser = diary_agent.build_parser()

    args = parser.parse_args(
        [
            "tags",
            "apply",
            "26_03_2026",
            "14:30",
            "Project/DiaryAgent",
        ]
    )

    assert args.command == "tags"
    assert args.tags_command == "apply"
    assert args.day == "26_03_2026"
    assert args.time == "14:30"
    assert args.tags == ["Project/DiaryAgent"]


def test_get_htfs_adapter_initializes_in_diary_dir(tmp_path):
    adapter = diary_agent.get_htfs_adapter(tmp_path)

    assert adapter.boundary == tmp_path.resolve()
    assert (tmp_path / ".tagfs.db").exists()
    assert set(adapter.list_tags()) >= {"People","Place","Topic","Project","Area"}


def test_resource_tags_for_specs_uses_leaf_tag_names():
    assert diary_agent.resource_tags_for_specs(
        ["Project/DiaryAgent", "Topic/Retrieval", "Status"]
    ) == ["DiaryAgent", "Retrieval", "Status"]


def test_run_tags_show_prints_section_tags(monkeypatch, tmp_path, capsys):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    section = diary_agent.DiarySection(tmp_path / "26_03_2026.md", "14:30", "- second note")
    monkeypatch.setattr(diary_agent, "resolve_section", lambda *_args: section)

    class FakeAdapter:
        def section_tags(self, section):
            return ["Project/DiaryAgent", "Topic/Retrieval"]

        def get_top_level_tags(self):
            return []

        def get_all_tag_paths(self):
            return []

    monkeypatch.setattr(diary_agent, "get_htfs_adapter", lambda _diary_dir: FakeAdapter())

    exit_code = diary_agent.run_tags_show(agent, "26_03_2026", "14:30")

    assert exit_code == 0
    assert capsys.readouterr().out == (
        "[26_03_2026.md#14:30]\n"
        "Project/DiaryAgent\n"
        "Topic/Retrieval\n"
    )


def test_run_tags_apply_creates_and_applies_tags(monkeypatch, tmp_path, capsys):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    section = diary_agent.DiarySection(tmp_path / "26_03_2026.md", "14:30", "- second note")
    monkeypatch.setattr(diary_agent, "resolve_section", lambda *_args: section)
    recorded = {}

    class FakeAdapter:
        def add_tags(self, tags):
            recorded["added"] = list(tags)
            return []

        def tag_section(self, section, tags):
            recorded["section_id"] = section.section_id
            recorded["tagged"] = list(tags)
            return []

        def get_top_level_tags(self):
            return []

        def get_all_tag_paths(self):
            return []

    monkeypatch.setattr(diary_agent, "get_htfs_adapter", lambda _diary_dir: FakeAdapter())

    exit_code = diary_agent.run_tags_apply(
        agent,
        "26_03_2026",
        "14:30",
        ["Project/DiaryAgent", "Topic/Retrieval"],
    )

    assert exit_code == 0
    assert recorded == {
        "added": ["Project/DiaryAgent", "Topic/Retrieval"],
        "section_id": "26_03_2026.md#14:30",
        "tagged": ["DiaryAgent", "Retrieval"],
    }
    assert capsys.readouterr().out == (
        "Tagged 26_03_2026.md#14:30 with Project/DiaryAgent, Topic/Retrieval\n"
    )


def test_run_tags_suggest_uses_available_htfs_tags(monkeypatch, tmp_path, capsys):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    section = diary_agent.DiarySection(tmp_path / "26_03_2026.md", "14:30", "- second note")
    monkeypatch.setattr(diary_agent, "resolve_section", lambda *_args: section)
    monkeypatch.setattr(
        agent,
        "suggest_section_tags",
        lambda section, available_tags: ["Project/DiaryAgent"] if "Project/DiaryAgent" in available_tags else [],
    )

    class FakeAdapter:
        def list_tags(self):
            return ["Project/DiaryAgent", "Topic/Retrieval"]

        def get_top_level_tags(self):
            return []

        def get_all_tag_paths(self):
            return []

    monkeypatch.setattr(diary_agent, "get_htfs_adapter", lambda _diary_dir: FakeAdapter())

    exit_code = diary_agent.run_tags_suggest(agent, "26_03_2026", "14:30")

    assert exit_code == 0
    assert capsys.readouterr().out == "[26_03_2026.md#14:30]\nProject/DiaryAgent\n"


def test_run_tags_list_prints_all_tags(monkeypatch, tmp_path, capsys):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")

    class FakeAdapter:
        def list_tags(self):
            return ["Area", "Project", "Topic"]

    monkeypatch.setattr(diary_agent, "get_htfs_adapter", lambda _diary_dir: FakeAdapter())

    exit_code = diary_agent.run_tags_list(agent)

    assert exit_code == 0
    assert capsys.readouterr().out == "Area\nProject\nTopic\n"


def test_run_tags_tree_prints_hierarchy(monkeypatch, tmp_path, capsys):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")

    class FakeAdapter:
        def list_tags(self):
            return ["Area", "Project", "DiaryAgent", "Topic", "Retrieval"]

        def get_top_level_tags(self):
            return ["Project", "Topic"]

        def get_child_tags(self, tag_name):
            return {
                "Project": ["DiaryAgent"],
                "DiaryAgent": ["Release"],
                "Topic": ["Retrieval"],
                "Area": [],
                "Retrieval": [],
            }.get(tag_name, [])

    monkeypatch.setattr(diary_agent, "get_htfs_adapter", lambda _diary_dir: FakeAdapter())

    exit_code = diary_agent.run_tags_tree(agent)

    assert exit_code == 0
    assert capsys.readouterr().out == (
        "Project\n"
        "  DiaryAgent\n"
        "    Release\n"
        "Topic\n"
        "  Retrieval\n"
    )


def test_run_tags_tree_rejects_missing_root(monkeypatch, tmp_path, capsys):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")

    class FakeAdapter:
        def list_tags(self):
            return ["Project"]

        def get_top_level_tags(self):
            return ["Project"]

        def get_child_tags(self, tag_name):
            return []

    monkeypatch.setattr(diary_agent, "get_htfs_adapter", lambda _diary_dir: FakeAdapter())

    exit_code = diary_agent.run_tags_tree(agent, root_tag="Missing")

    assert exit_code == 1
    assert capsys.readouterr().out == "Tag not found: Missing\n"


def test_run_tags_delete_recursively_deletes_descendants_first(monkeypatch, tmp_path, capsys):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    deleted = []
    checked = []

    class FakeAdapter:
        def list_tags(self):
            return ["Project", "Project/Alpha", "Project/Alpha/Reports"]

        def get_tag_descendants(self, tag_name):
            return ["Project/Alpha/Reports", "Project/Alpha"] if tag_name == "Project" else []

        def tag_has_usage(self, tag_name):
            checked.append(tag_name)
            return False

        def delete_tag(self, tag_name):
            deleted.append(tag_name)
            return True

    monkeypatch.setattr(diary_agent, "get_htfs_adapter", lambda _diary_dir: FakeAdapter())

    exit_code = diary_agent.run_tags_delete(
        agent,
        "Project",
        descendants=True,
        only_unused=True,
        yes=True,
    )

    assert exit_code == 0
    assert checked == ["Project/Alpha/Reports", "Project/Alpha", "Project"]
    assert deleted == ["Project/Alpha/Reports", "Project/Alpha", "Project"]
    assert capsys.readouterr().out == "Deleted 3 tag(s): Project/Alpha/Reports, Project/Alpha, Project\n"


def test_run_tags_delete_blocks_when_tags_are_used(monkeypatch, tmp_path, capsys):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    deleted = []

    class FakeAdapter:
        def list_tags(self):
            return ["Project"]

        def get_tag_descendants(self, tag_name):
            return []

        def tag_has_usage(self, tag_name):
            return tag_name == "Project"

        def delete_tag(self, tag_name):
            deleted.append(tag_name)
            return True

    monkeypatch.setattr(diary_agent, "get_htfs_adapter", lambda _diary_dir: FakeAdapter())

    exit_code = diary_agent.run_tags_delete(
        agent,
        "Project",
        descendants=False,
        only_unused=True,
        yes=True,
    )

    assert exit_code == 1
    assert deleted == []
    assert capsys.readouterr().out == (
        "Cannot delete tags that are still used by diary resources: Project\n"
    )


def test_build_parser_accepts_tag_delete():
    parser = diary_agent.build_parser()

    args = parser.parse_args(["tags", "delete", "Project", "--descendants", "--unused-only", "--yes"])

    assert args.command == "tags"
    assert args.tags_command == "delete"
    assert args.tag == "Project"
    assert args.descendants is True
    assert args.unused_only is True
    assert args.yes is True


def test_build_parser_accepts_tag_list_and_tree():
    parser = diary_agent.build_parser()

    list_args = parser.parse_args(["tags", "ls"])
    tree_args = parser.parse_args(["tags", "tree", "Project"])

    assert list_args.command == "tags"
    assert list_args.tags_command == "ls"
    assert tree_args.command == "tags"
    assert tree_args.tags_command == "tree"
    assert tree_args.tag == "Project"


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


def test_run_capture_interactive_exposes_rewrite_callback_and_saves_final_edit_verbatim(monkeypatch, tmp_path, capsys):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    monkeypatch.setattr(agent, "ensure_storage", lambda: None)

    editor_calls = []

    def fake_launch_editor(initial_text="", state="Capturing update", rewrite=None, suggest_tags=None):
        rewritten = rewrite("raw update") if rewrite is not None else initial_text
        editor_calls.append((initial_text, state, rewritten))
        return "- Final edited note\n\n### keep this heading", []

    monkeypatch.setattr(diary_agent, "launch_editor", fake_launch_editor)
    monkeypatch.setattr(agent, "synthesize_entry", lambda text: "- Rewritten note")
    monkeypatch.setattr(agent, "prepare_rewrite_for_review", lambda entry: entry)
    monkeypatch.setattr(diary_agent, "prompt_for_section_tags", lambda *args, **kwargs: [])

    class FakeAdapter:
        def list_tags(self):
            return []

        def add_tags(self, tags):
            return []

        def tag_section(self, section, tags):
            return []

        def get_top_level_tags(self):
            return []

        def get_all_tag_paths(self):
            return []

    monkeypatch.setattr(diary_agent, "get_htfs_adapter", lambda _diary_dir: FakeAdapter())
    monkeypatch.setattr(
        agent,
        "append_entry_verbatim",
        lambda entry: (tmp_path / "26_03_2026.md", entry == "- Final edited note\n\n### keep this heading"),
    )
    monkeypatch.setattr(
        agent,
        "latest_section_for_file",
        lambda _path: diary_agent.DiarySection(tmp_path / "26_03_2026.md", "14:30", "- Final edited note\n\n### keep this heading"),
    )
    monkeypatch.setattr(
        agent,
        "review_entry_todos",
        lambda entry, interactive: (_ for _ in ()).throw(AssertionError("should not post-process final edit")),
    )

    exit_code = diary_agent.run_capture(agent)

    assert exit_code == 0
    assert editor_calls == [
        ("", "Capturing update", "- Rewritten note"),
    ]
    assert capsys.readouterr().out == "Updated 26_03_2026.md\n\n- Final edited note\n\n### keep this heading\n"


def test_run_capture_interactive_rewrite_omits_existing_lines_from_rewritten_draft(monkeypatch, tmp_path):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    monkeypatch.setattr(agent, "ensure_storage", lambda: None)
    monkeypatch.setattr(agent, "read_today_context", lambda: "## 09:15\n\n- Existing note")

    editor_calls = []

    def fake_launch_editor(initial_text="", state="Capturing update", rewrite=None, suggest_tags=None):
        rewritten = rewrite("raw update") if rewrite is not None else initial_text
        editor_calls.append((initial_text, state, rewritten))
        return "- New note", []

    monkeypatch.setattr(diary_agent, "launch_editor", fake_launch_editor)
    monkeypatch.setattr(agent, "synthesize_entry", lambda text: "- Existing note\n- New note")
    monkeypatch.setattr(diary_agent, "prompt_for_section_tags", lambda *args, **kwargs: [])

    class FakeAdapter:
        def list_tags(self):
            return []

        def add_tags(self, tags):
            return []

        def tag_section(self, section, tags):
            return []

        def get_top_level_tags(self):
            return []

        def get_all_tag_paths(self):
            return []

    monkeypatch.setattr(diary_agent, "get_htfs_adapter", lambda _diary_dir: FakeAdapter())
    monkeypatch.setattr(agent, "append_entry_verbatim", lambda entry: (tmp_path / "26_03_2026.md", True))
    monkeypatch.setattr(
        agent,
        "latest_section_for_file",
        lambda _path: diary_agent.DiarySection(tmp_path / "26_03_2026.md", "14:30", "- New note"),
    )

    exit_code = diary_agent.run_capture(agent)

    assert exit_code == 0
    assert editor_calls == [
        ("", "Capturing update", "- New note"),
    ]


def test_run_capture_interactive_prompts_for_tags_and_applies_them(monkeypatch, tmp_path):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    monkeypatch.setattr(agent, "ensure_storage", lambda: None)
    
    def fake_launch_editor(initial_text="", state="Capturing update", rewrite=None, suggest_tags=None):
        suggested = suggest_tags("- Final edited note") if suggest_tags else []
        return "- Final edited note", suggested

    monkeypatch.setattr(diary_agent, "launch_editor", fake_launch_editor)
    section = diary_agent.DiarySection(tmp_path / "26_03_2026.md", "14:30", "- Final edited note")
    monkeypatch.setattr(agent, "append_entry_verbatim", lambda entry: (tmp_path / "26_03_2026.md", True))
    monkeypatch.setattr(agent, "latest_section_for_file", lambda _path: section)
    prompted = {}

    monkeypatch.setattr(agent, "suggest_tags_for_text", lambda text, all_tags: ["Topic/Retrieval"])

    def fake_prompt_for_section_tags(all_tags, top_level_tags, all_paths, suggested_tags=[]):
        prompted["all_tags"] = list(all_tags)
        prompted["top_level"] = list(top_level_tags)
        prompted["all_paths"] = list(all_paths)
        prompted["suggested"] = list(suggested_tags)
        return ["Project/DiaryAgent"]

    monkeypatch.setattr(diary_agent, "prompt_for_section_tags", fake_prompt_for_section_tags)
    recorded = {}

    class FakeAdapter:
        def list_tags(self):
            return ["Project/DiaryAgent", "Topic/Retrieval"]

        def get_top_level_tags(self):
            return ["Project", "Topic"]

        def get_all_tag_paths(self):
            return ["Project/DiaryAgent", "Topic/Retrieval"]

        def add_tags(self, tags):
            recorded["added"] = list(tags)
            return []

        def tag_section(self, applied_section, tags):
            recorded["section_id"] = applied_section.section_id
            recorded["tagged"] = list(tags)
            return []

    monkeypatch.setattr(diary_agent, "get_htfs_adapter", lambda _diary_dir: FakeAdapter())

    exit_code = diary_agent.run_capture(agent)

    assert exit_code == 0
    assert prompted == {
        "all_tags": ["Project/DiaryAgent", "Topic/Retrieval"],
        "top_level": ["Project", "Topic"],
        "all_paths": ["Project/DiaryAgent", "Topic/Retrieval"],
        "suggested": ["Topic/Retrieval"],
    }
    assert recorded == {
        "added": ["Project/DiaryAgent"],
        "section_id": "26_03_2026.md#14:30",
        "tagged": ["DiaryAgent"],
    }


def test_launch_editor_uses_thread_mode_when_called_from_async_context(monkeypatch):
    captured = {}

    class FakeBuffer:
        read_only = None

    class FakeSession:
        def __init__(self, *args, **kwargs):
            self.default_buffer = FakeBuffer()

        def prompt(self, *args, **kwargs):
            captured["in_thread"] = kwargs.get("in_thread")
            return "edited text"

    class FakeKeyBindings:
        def add(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

    monkeypatch.setattr(ui, "require_prompt_toolkit", lambda: None)
    monkeypatch.setattr(ui, "PromptSession", FakeSession)
    monkeypatch.setattr(ui, "KeyBindings", FakeKeyBindings)
    monkeypatch.setattr(ui, "Condition", lambda predicate: predicate)

    async def call_launch_editor():
        return ui.launch_editor(initial_text="draft")

    result = asyncio.run(call_launch_editor())

    assert captured["in_thread"] is True
    assert result == ("edited text", [])


def test_synthesize_entry_strips_headings_and_preserves_nested_bullets(monkeypatch):
    class FakeOllama:
        @staticmethod
        def chat(*, model, messages):
            return {
                "message": {
                    "content": "## Work\n- Project work\n  - Finished auth cleanup\n  - Added tests"
                }
            }

    monkeypatch.setattr(diary_agent.llm, "ollama", FakeOllama())

    synthesized = diary_agent.llm.synthesize_entry(
        model="test-model",
        raw_update="worked on project",
        today_context="",
    )

    assert synthesized == (
        "- Project work\n"
        "  - Finished auth cleanup\n"
        "  - Added tests"
    )


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


def test_entry_options_are_sorted_newest_first_with_preview_and_search_text(tmp_path):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    (tmp_path / "25_03_2026.md").write_text("\n- earlier entry\n", encoding="utf-8")
    (tmp_path / "27_03_2026.md").write_text("- latest entry\nsecond line\n", encoding="utf-8")

    options = agent.entry_options()

    assert [option.file_path.name for option in options] == [
        "27_03_2026.md",
        "25_03_2026.md",
    ]
    assert options[0].title == "27 Mar 2026"
    assert options[0].preview == "- latest entry"
    assert "27_03_2026" in options[0].search_text
    assert "27 mar 2026" in options[0].search_text


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
        lambda title, body, previous_entry=None, next_entry=None, pick_entry=None, get_tags=None, toggle_todo=None, **kwargs: shown.update(
            {
                "title": title,
                "body": body,
                "previous": previous_entry("05_03_2026.md") if previous_entry else None,
                "next": next_entry("05_03_2026.md") if next_entry else None,
                "picked": pick_entry() if pick_entry else None,
            }
        ),
    )
    monkeypatch.setattr(agent, "adjacent_entry", lambda path, step: ("04_03_2026.md", "- prior") if step < 0 else ("06_03_2026.md", "- next"))
    monkeypatch.setattr(
        agent,
        "entry_options",
        lambda: [diary_agent.DiaryEntryOption(target, "05 Mar 2026", "- Met with product", "05_03_2026")],
    )

    exit_code = diary_agent.run_show_day(agent, day_text="05_03_2026")

    assert exit_code == 0
    assert shown == {
        "title": "05_03_2026.md",
        "body": "- Met with product\n- [ ] Send notes",
        "previous": ("04_03_2026.md", "- prior"),
        "next": ("06_03_2026.md", "- next"),
        "picked": [diary_agent.DiaryEntryOption(target, "05 Mar 2026", "- Met with product", "05_03_2026")],
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
        lambda title, body, previous_entry=None, next_entry=None, pick_entry=None, get_tags=None, toggle_todo=None, **kwargs: shown.update({"title": title, "body": body}),
    )

    exit_code = diary_agent.run_show_day(agent)

    assert exit_code == 0
    assert shown == {
        "title": "28_03_2026.md",
        "body": "- Defaulted to today",
    }


def test_run_show_day_wires_htfs_callbacks(monkeypatch, tmp_path):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    target = tmp_path / "05_03_2026.md"
    target.write_text("## 14:30\n- Note\n", encoding="utf-8")
    monkeypatch.setattr(agent, "ensure_storage", lambda: None)
    monkeypatch.setattr(agent, "get_section_tags", lambda _path: {"14:30": ["Project/DiaryAgent"]})
    monkeypatch.setattr(agent, "suggest_tags_for_text", lambda text, all_tags: ["Topic/Retrieval"])

    adapter_calls = {}

    class FakeAdapter:
        def list_tags(self):
            adapter_calls["list_tags"] = True
            return ["Project/DiaryAgent", "Topic/Retrieval"]

        def get_top_level_tags(self):
            adapter_calls["top_level"] = True
            return ["Project", "Topic"]

        def get_all_tag_paths(self):
            adapter_calls["all_paths"] = True
            return ["Project/DiaryAgent", "Topic/Retrieval"]

    monkeypatch.setattr(diary_agent, "get_htfs_adapter", lambda _diary_dir: FakeAdapter())

    shown = {}

    def fake_show_diary_entry(
        title,
        body,
        previous_entry=None,
        next_entry=None,
        pick_entry=None,
        get_tags=None,
        toggle_todo=None,
        update_section=None,
        set_tags=None,
        get_all_tags=None,
        suggest_tags=None,
    ):
        shown["title"] = title
        shown["body"] = body
        shown["all_tags"] = get_all_tags()
        shown["suggested"] = suggest_tags("note")

    monkeypatch.setattr(diary_agent, "show_diary_entry", fake_show_diary_entry)

    exit_code = diary_agent.run_show_day(agent, day_text="05_03_2026")

    assert exit_code == 0
    assert shown == {
        "title": "05_03_2026.md",
        "body": "## 14:30\n- Note",
        "all_tags": (["Project/DiaryAgent", "Topic/Retrieval"], ["Project", "Topic"], ["Project/DiaryAgent", "Topic/Retrieval"]),
        "suggested": ["Topic/Retrieval"],
    }
    assert adapter_calls == {"list_tags": True, "top_level": True, "all_paths": True}


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
        lambda title, body, previous_entry=None, next_entry=None, pick_entry=None, get_tags=None, toggle_todo=None, **kwargs: (_ for _ in ()).throw(RuntimeError("missing prompt_toolkit")),
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

def test_run_tags_show_prints_all_sections_tags_when_time_is_none(monkeypatch, tmp_path, capsys):
    agent = diary_agent.DiaryAgent(diary_dir=tmp_path, model="test-model")
    day_file = tmp_path / "26_03_2026.md"
    day_file.write_text("## 10:00\n- first note\n## 14:30\n- second note", encoding="utf-8")
    
    class FakeAdapter:
        def section_tags(self, section):
            if section.heading == "10:00":
                return ["Topic/Personal"]
            if section.heading == "14:30":
                return ["Project/DiaryAgent"]
            return []

        def get_top_level_tags(self):
            return []

        def get_all_tag_paths(self):
            return []

    monkeypatch.setattr(diary_agent, "get_htfs_adapter", lambda _diary_dir: FakeAdapter())

    exit_code = diary_agent.run_tags_show(agent, "26_03_2026", None)

    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "[26_03_2026.md#10:00]" in captured
    assert "  Topic/Personal" in captured
    assert "[26_03_2026.md#14:30]" in captured
    assert "  Project/DiaryAgent" in captured

def test_build_parser_accepts_tags_show_without_time():
    parser = diary_agent.build_parser()
    args = parser.parse_args(["tags", "show", "26_03_2026"])
    assert args.command == "tags"
    assert args.tags_command == "show"
    assert args.day == "26_03_2026"
    assert args.time is None
