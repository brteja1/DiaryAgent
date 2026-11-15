import datetime as dt
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import diary_agent_app.commands as commands
from diary_agent_app.service import DiaryAgent
import diary_agent_app.cli as cli
import diary_agent_app.service as service
from diary_agent_app import llm, models
import diary_agent_app.core as core
from diary_agent_app.htfs_adapter import HTFSAdapter
import diary_agent_app.ui as ui


def test_parse_config_text_ignores_comments_and_invalid_lines():
    """CFG-01–03: observable contract regression."""
    parsed = core.parse_config_text(
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
    """CFG-01–03: observable contract regression."""
    fake_home = tmp_path / "home"
    config_path = fake_home / ".config" / "diary_agent" / "config.txt"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "diary_path=~/journal\nllm_model=qwen2.5\nhtfs_path=~/HTFS\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(commands.Path, "home", lambda: fake_home)
    monkeypatch.setenv("HOME", str(fake_home))

    config = core.load_or_initialize_config()

    assert config.diary_dir == fake_home / "journal"
    assert config.llm_model == "qwen2.5"


def test_load_or_initialize_config_allows_missing_llm_model(monkeypatch, tmp_path):
    """CFG-01–03: observable contract regression."""
    fake_home = tmp_path / "home"
    config_path = fake_home / ".config" / "diary_agent" / "config.txt"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("diary_path=~/journal\n", encoding="utf-8")
    monkeypatch.setattr(commands.Path, "home", lambda: fake_home)
    monkeypatch.setattr(core.Path, "home", lambda: fake_home)
    monkeypatch.setenv("HOME", str(fake_home))

    config = core.load_or_initialize_config()

    assert config.diary_dir == fake_home / "journal"
    assert config.llm_model is None


def test_load_or_initialize_config_non_interactive_missing_required_values_raises(
    monkeypatch, tmp_path
):
    """CFG-01–03: observable contract regression."""
    fake_home = tmp_path / "home"
    config_path = fake_home / ".config" / "diary_agent" / "config.txt"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("diary_path=\nhtfs_path=\n", encoding="utf-8")
    monkeypatch.setattr(commands.Path, "home", lambda: fake_home)
    monkeypatch.setattr(commands.sys.stdin, "isatty", lambda: False)

    with pytest.raises(RuntimeError, match="Missing or invalid config"):
        core.load_or_initialize_config()


def test_bundled_htfs_path_ignores_environment_and_home(monkeypatch, tmp_path):
    """DEP-01–02: observable contract regression."""
    monkeypatch.setenv("DIARY_AGENT_HTFS_PATH", str(tmp_path / "external"))
    monkeypatch.setattr(core.Path, "home", lambda: tmp_path / "home")
    expected = Path(cli.__file__).resolve().parents[1] / "deps" / "HTFS"
    assert core.default_htfs_path() == expected
    backend = HTFSAdapter.require_backend()
    assert (
        Path(sys.modules[backend.__module__].__file__)
        .resolve()
        .is_relative_to(expected)
    )


def test_load_config_ignores_legacy_htfs_path(monkeypatch, tmp_path):
    """CFG-01–03: observable contract regression."""
    config_path = tmp_path / ".config" / "diary_agent" / "config.txt"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        f"diary_path={tmp_path / 'journal'}\nhtfs_path=/obsolete\n", encoding="utf-8"
    )
    monkeypatch.setattr(core.Path, "home", lambda: tmp_path)
    config = core.load_or_initialize_config()
    assert config.diary_dir == tmp_path / "journal"
    assert config.llm_model is None


def test_write_config_needs_only_diary_path_and_optional_model(tmp_path):
    """CFG-01–03: observable contract regression."""
    config_path = tmp_path / "config.txt"
    core.write_config(
        config_path,
        tmp_path / "journal",
        "qwen2.5",
    )

    assert config_path.read_text(encoding="utf-8") == (
        f"diary_path={tmp_path / 'journal'}\n" f"llm_model=qwen2.5\n"
    )


def test_write_config_omits_llm_model_when_not_configured(tmp_path):
    """CFG-01–03: observable contract regression."""
    config_path = tmp_path / "config.txt"
    core.write_config(
        config_path,
        tmp_path / "journal",
        None,
    )

    assert config_path.read_text(encoding="utf-8") == (
        f"diary_path={tmp_path / 'journal'}\n"
    )


def test_cli_requires_bundled_htfs_before_loading_config(monkeypatch, tmp_path, capsys):
    """CFG-01–03: observable contract regression."""
    monkeypatch.setattr(core, "default_htfs_path", lambda: tmp_path / "missing-htfs")

    def unexpected_config():
        pytest.fail("Config/capture must not start without required HTFS")

    monkeypatch.setattr(cli, "load_or_initialize_config", unexpected_config)
    assert cli.main(["capture", "--text", "New note"]) == 1
    assert "git submodule update --init --recursive" in capsys.readouterr().err
    assert not list(tmp_path.rglob("*.md"))


def test_adapter_rejects_preloaded_external_htfs(monkeypatch, tmp_path):
    """DEP-01–02: observable contract regression."""
    monkeypatch.setitem(
        sys.modules,
        "htfs",
        SimpleNamespace(__file__=str(tmp_path / "htfs/__init__.py")),
    )
    with pytest.raises(RuntimeError, match="different HTFS package is already loaded"):
        HTFSAdapter.require_backend()


def test_cli_htfs_initialization_failure_prevents_capture(
    monkeypatch, tmp_path, capsys
):
    """DEP-01–02: observable contract regression."""
    diary_dir = tmp_path / "journal"
    monkeypatch.setattr(
        cli,
        "load_or_initialize_config",
        lambda: core.AppConfig(diary_dir=diary_dir, llm_model=None),
    )

    def unavailable(_boundary):
        raise RuntimeError("HTFS store unavailable")

    monkeypatch.setattr(commands, "get_htfs_adapter", unavailable)
    assert cli.main(["capture", "--text", "New note"]) == 1
    assert "HTFS store unavailable" in capsys.readouterr().err
    assert not list(diary_dir.glob("*.md"))


def test_bundled_htfs_resource_tagging_survives_reopening(tmp_path):
    """DEP-01–02: observable contract regression."""
    section = models.DiarySection(tmp_path / "14_11_2026.md", "14:30", "A note")
    adapter = commands.get_htfs_adapter(tmp_path)
    adapter.add_tags(["Project/DiaryAgent"])
    assert adapter.tag_section(section, ["DiaryAgent"]) == []
    reopened = commands.get_htfs_adapter(tmp_path)
    assert reopened.section_tags(section) == ["DiaryAgent"]
    assert reopened.resource_path_for_section(section) in reopened.query_resource_paths(
        "DiaryAgent"
    )
    assert reopened.sqlite_path.is_file()
    assert reopened.rdf_path.is_file()


def test_search_does_not_hide_htfs_read_failures(monkeypatch, tmp_path):
    """SEARCH-01–06: observable contract regression."""
    (tmp_path / "14_11_2026.md").write_text("## 14:30\n\nA note\n", encoding="utf-8")

    class BrokenAdapter:
        def __init__(self, _boundary):
            pass

        def section_tags(self, _section):
            raise RuntimeError("HTFS read failed")

    monkeypatch.setattr(service, "HTFSAdapter", BrokenAdapter)
    with pytest.raises(RuntimeError, match="HTFS read failed"):
        DiaryAgent(tmp_path, model=None).search("note")


def test_show_does_not_mask_runtime_errors_as_ui_fallback(monkeypatch, tmp_path):
    """VIEW-01/02/07: observable contract regression."""
    (tmp_path / "14_11_2026.md").write_text("## 14:30\n\nA note\n", encoding="utf-8")
    monkeypatch.setattr(ui, "require_prompt_toolkit", lambda: None)

    def broken_viewer(*_args, **_kwargs):
        raise RuntimeError("HTFS read failed")

    monkeypatch.setattr(commands, "show_diary_entry", broken_viewer)
    with pytest.raises(RuntimeError, match="HTFS read failed"):
        commands.run_show_day(DiaryAgent(tmp_path, model=None), "14_11_2026")


def test_append_entry_appends_to_existing_daily_file(tmp_path):
    """DATA-01–02, CAP-06: observable contract regression."""
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")
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
    monkeypatch.setattr(commands.dt, "date", FixedDate)
    monkeypatch.setattr(commands.dt, "datetime", FixedDateTime)
    try:
        path, appended = agent.append_entry("- second note")
    finally:
        monkeypatch.undo()

    assert path == existing_path
    assert appended is True
    assert existing_path.read_text(encoding="utf-8") == (
        "## 09:15\n\n" "- first note\n\n" "## 14:30\n\n" "- second note\n"
    )


def test_append_entry_verbatim_uses_serial_suffix_for_same_minute(tmp_path):
    """DATA-01–02, CAP-06: observable contract regression."""
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")
    today = dt.date(2026, 3, 26)
    existing_path = agent.today_file(today)
    existing_path.write_text("## 14:30\n\n- first note\n", encoding="utf-8")

    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return today

    class FixedDateTime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 26, 14, 30)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(commands.dt, "date", FixedDate)
    monkeypatch.setattr(commands.dt, "datetime", FixedDateTime)
    try:
        first_path, first_appended = agent.append_entry_verbatim("- second note")
        second_path, second_appended = agent.append_entry_verbatim("- third note")
    finally:
        monkeypatch.undo()

    assert first_appended is True
    assert second_appended is True
    assert first_path == existing_path
    assert second_path == existing_path
    assert existing_path.read_text(encoding="utf-8") == (
        "## 14:30\n\n"
        "- first note\n\n"
        "## 14:30:2\n\n"
        "- second note\n\n"
        "## 14:30:3\n\n"
        "- third note\n"
    )


def test_parse_day_sections_returns_timestamp_sections_with_stable_ids(tmp_path):
    """DATA-03/07: observable contract regression."""
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
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")

    sections = agent.parse_day_sections(file_path)

    assert [
        (section.heading, section.body, section.section_id) for section in sections
    ] == [
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


def test_parse_day_sections_supports_serialized_timestamp_headings(tmp_path):
    """DATA-03/07: observable contract regression."""
    file_path = tmp_path / "26_03_2026.md"
    file_path.write_text(
        "## 14:30\n\n" "- first note\n\n" "## 14:30:2\n\n" "- second note\n",
        encoding="utf-8",
    )
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")

    sections = agent.parse_day_sections(file_path)

    assert [(section.heading, section.section_id) for section in sections] == [
        ("14:30", "26_03_2026.md#14:30"),
        ("14:30:2", "26_03_2026.md#14:30:2"),
    ]


def test_parse_day_sections_ignores_text_before_first_timestamp_heading(tmp_path):
    """DATA-03/07: observable contract regression."""
    file_path = tmp_path / "26_03_2026.md"
    file_path.write_text(
        "orphan text\n" "## 09:15\n\n" "- first note\n",
        encoding="utf-8",
    )
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")

    sections = agent.parse_day_sections(file_path)

    assert len(sections) == 1
    assert sections[0].heading == "09:15"
    assert sections[0].body == "- first note"


def test_section_for_id_returns_matching_section(tmp_path):
    """DATA-08: observable contract regression."""
    file_path = tmp_path / "26_03_2026.md"
    file_path.write_text(
        "## 09:15\n\n" "- first note\n\n" "## 14:30\n\n" "- second note\n",
        encoding="utf-8",
    )
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")

    section = agent.section_for_id("26_03_2026.md#14:30")

    assert section is not None
    assert section.heading == "14:30"
    assert section.body == "- second note"
    assert section.section_id == "26_03_2026.md#14:30"


def test_section_for_id_returns_none_for_missing_section(tmp_path):
    """DATA-08: observable contract regression."""
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")

    assert agent.section_for_id("26_03_2026.md#14:30") is None


def test_delete_section_removes_markdown_section_and_htfs_resource(tmp_path):
    """VIEW-05/08/09, PERSIST-01: actual content/resource deletion."""
    path = tmp_path / "26_03_2026.md"
    path.write_text("## 09:15\n\n- first note\n\n## 14:30\n\n- second note\n")
    agent = DiaryAgent(tmp_path, None)
    selected = agent.section_for_id(path.name + "#09:15")
    agent.set_section_tags(selected, ["Old"])
    assert agent.delete_section(path, "09:15") == "## 14:30\n\n- second note"
    assert path.read_text() == "## 14:30\n\n- second note\n"
    adapter = HTFSAdapter(tmp_path)
    assert not adapter.section_resource_exists(selected)
    assert "Old" in adapter.list_tags()


def test_delete_section_returns_none_when_heading_is_missing(monkeypatch, tmp_path):
    """VIEW-05/08/09 (missing target; no mutation starts): observable contract regression."""
    file_path = tmp_path / "26_03_2026.md"
    original = "## 09:15\n\n- first note\n"
    file_path.write_text(original, encoding="utf-8")
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")
    constructed = {"count": 0}

    class FakeAdapter:
        def __init__(self, *_args, **_kwargs):
            constructed["count"] += 1

    monkeypatch.setattr(service, "HTFSAdapter", FakeAdapter)

    updated = agent.delete_section(file_path, "14:30")

    assert updated is None
    assert constructed["count"] == 0
    assert file_path.read_text(encoding="utf-8") == original


def test_htfs_adapter_maps_section_to_resource_path_and_back(tmp_path):
    """TAG-01–02: observable contract regression."""
    file_path = tmp_path / "26_03_2026.md"
    section = models.DiarySection(
        file_path=file_path,
        heading="14:30",
        body="- second note",
    )
    adapter = HTFSAdapter(boundary=tmp_path)

    resource_path = adapter.resource_path_for_section(section)

    assert resource_path == f"{file_path.resolve()}#14:30"
    assert adapter.section_id_from_resource_path(resource_path) == "26_03_2026.md#14:30"


def test_htfs_adapter_loads_section_from_resource_path(tmp_path):
    """TAG-01–02: observable contract regression."""
    file_path = tmp_path / "26_03_2026.md"
    file_path.write_text(
        "## 14:30\n\n" "- second note\n",
        encoding="utf-8",
    )
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")
    adapter = HTFSAdapter(boundary=tmp_path)

    section = adapter.load_section_by_resource_path(
        agent, f"{file_path.resolve()}#14:30"
    )

    assert section is not None
    assert section.section_id == "26_03_2026.md#14:30"
    assert section.body == "- second note"


def test_build_parser_accepts_tags_apply_command():
    """CLI-01: observable contract regression."""
    parser = cli.build_parser()

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


def test_run_tags_show_prints_section_tags(monkeypatch, tmp_path, capsys):
    """TAG-02–06: observable contract regression."""
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")
    section = models.DiarySection(tmp_path / "26_03_2026.md", "14:30", "- second note")
    monkeypatch.setattr(commands, "resolve_section", lambda *_args: section)

    class FakeAdapter:
        def section_tags(self, section):
            return ["Project/DiaryAgent", "Topic/Retrieval"]

        def get_top_level_tags(self):
            return []

        def get_all_tag_paths(self):
            return []

    monkeypatch.setattr(commands, "get_htfs_adapter", lambda *_args: FakeAdapter())

    exit_code = commands.run_tags_show(agent, "26_03_2026", "14:30")

    assert exit_code == 0
    assert capsys.readouterr().out == (
        "[26_03_2026.md#14:30]\n" "Project/DiaryAgent\n" "Topic/Retrieval\n"
    )


def test_run_tags_apply_creates_and_applies_tags(tmp_path, capsys):
    """TAG-04/05: hierarchical creation and additive section associations."""
    path = tmp_path / "26_03_2026.md"
    path.write_text("## 14:30\n\nA note\n")
    agent = DiaryAgent(tmp_path, None)
    section = agent.section_for_id(path.name + "#14:30")
    agent.set_section_tags(section, ["Existing"])
    assert (
        commands.run_tags_apply(
            agent, "26_03_2026", "14:30", ["Project/DiaryAgent", "Topic/Retrieval"]
        )
        == 0
    )
    adapter = HTFSAdapter(tmp_path)
    assert set(adapter.section_tags(section)) == {"Existing", "DiaryAgent", "Retrieval"}
    assert {"Project/DiaryAgent", "Topic/Retrieval"} <= set(adapter.get_all_tag_paths())
    assert section.section_id in capsys.readouterr().out


def test_run_tags_suggest_uses_available_htfs_tags(monkeypatch, tmp_path, capsys):
    """TAG-02–06: observable contract regression."""
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")
    section = models.DiarySection(tmp_path / "26_03_2026.md", "14:30", "- second note")
    monkeypatch.setattr(commands, "resolve_section", lambda *_args: section)
    monkeypatch.setattr(
        agent,
        "suggest_section_tags",
        lambda section, available_tags: (
            ["Project/DiaryAgent"] if "Project/DiaryAgent" in available_tags else []
        ),
    )

    class FakeAdapter:
        def list_tags(self):
            return ["Project/DiaryAgent", "Topic/Retrieval"]

        def get_top_level_tags(self):
            return []

        def get_all_tag_paths(self):
            return []

    monkeypatch.setattr(commands, "get_htfs_adapter", lambda *_args: FakeAdapter())

    exit_code = commands.run_tags_suggest(agent, "26_03_2026", "14:30")

    assert exit_code == 0
    assert capsys.readouterr().out == "[26_03_2026.md#14:30]\nProject/DiaryAgent\n"


def test_run_tags_list_prints_all_tags(monkeypatch, tmp_path, capsys):
    """TAG-02–06: observable contract regression."""
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")

    class FakeAdapter:
        def list_tags(self):
            return ["Area", "Project", "Topic"]

    monkeypatch.setattr(commands, "get_htfs_adapter", lambda *_args: FakeAdapter())

    exit_code = commands.run_tags_list(agent)

    assert exit_code == 0
    assert capsys.readouterr().out == "Area\nProject\nTopic\n"


def test_run_tags_tree_prints_hierarchy(monkeypatch, tmp_path, capsys):
    """TAG-02–06: observable contract regression."""
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")

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

    monkeypatch.setattr(commands, "get_htfs_adapter", lambda *_args: FakeAdapter())

    exit_code = commands.run_tags_tree(agent)

    assert exit_code == 0
    assert capsys.readouterr().out == (
        "Project\n" "  DiaryAgent\n" "    Release\n" "Topic\n" "  Retrieval\n"
    )


def test_run_tags_tree_rejects_missing_root(monkeypatch, tmp_path, capsys):
    """TAG-02–06: observable contract regression."""
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")

    class FakeAdapter:
        def list_tags(self):
            return ["Project"]

        def get_top_level_tags(self):
            return ["Project"]

        def get_child_tags(self, tag_name):
            return []

    monkeypatch.setattr(commands, "get_htfs_adapter", lambda *_args: FakeAdapter())

    exit_code = commands.run_tags_tree(agent, root_tag="Missing")

    assert exit_code == 1
    assert capsys.readouterr().out == "Tag not found: Missing\n"


def test_run_tags_delete_recursively_deletes_descendants_first(monkeypatch, tmp_path):
    """TAG-06: destructive backend effects run child before parent."""
    adapter = commands.get_htfs_adapter(tmp_path)
    adapter.add_tags(["Alpha/Beta/Gamma"])
    deleted = []
    delete = HTFSAdapter.delete_tag

    def observe(self, name):
        deleted.append(name)
        return delete(self, name)

    monkeypatch.setattr(HTFSAdapter, "delete_tag", observe)
    assert (
        commands.run_tags_delete(
            DiaryAgent(tmp_path, None),
            "Alpha",
            descendants=True,
            only_unused=False,
            yes=True,
        )
        == 0
    )
    assert deleted == ["Gamma", "Beta", "Alpha"]
    assert not {"Alpha", "Beta", "Gamma"} & set(adapter.list_tags())


def test_run_tags_delete_blocks_when_tags_are_used(monkeypatch, tmp_path, capsys):
    """TAG-02–06: observable contract regression."""
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")
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

    monkeypatch.setattr(commands, "get_htfs_adapter", lambda *_args: FakeAdapter())

    exit_code = commands.run_tags_delete(
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
    """CLI-01: observable contract regression."""
    parser = cli.build_parser()

    args = parser.parse_args(
        ["tags", "delete", "Project", "--descendants", "--unused-only", "--yes"]
    )

    assert args.command == "tags"
    assert args.tags_command == "delete"
    assert args.tag == "Project"
    assert args.descendants is True
    assert args.unused_only is True
    assert args.yes is True


def test_build_parser_accepts_tag_list_and_tree():
    """CLI-01: observable contract regression."""
    parser = cli.build_parser()

    list_args = parser.parse_args(["tags", "ls"])
    tree_args = parser.parse_args(["tags", "tree", "Project"])
    search_args = parser.parse_args(["search", "--tags", "Project&Topic", "login bug"])
    tag_only_args = parser.parse_args(["search", "--tags", "Project/DiaryAgent"])

    assert list_args.command == "tags"
    assert list_args.tags_command == "ls"
    assert tree_args.command == "tags"
    assert tree_args.tags_command == "tree"
    assert tree_args.tag == "Project"
    assert search_args.command == "search"
    assert search_args.query == "login bug"
    assert search_args.tags == "Project&Topic"
    assert tag_only_args.command == "search"
    assert tag_only_args.query is None
    assert tag_only_args.tags == "Project/DiaryAgent"


def test_run_capture_interactive_prompts_for_tags_and_applies_them(
    monkeypatch, tmp_path
):
    """CAP-07, TAG-03: actual saved capture followed by explicit tagging."""
    agent = DiaryAgent(tmp_path, "model")
    adapter = commands.get_htfs_adapter(tmp_path)
    adapter.add_tags(["Project/DiaryAgent", "Topic/Retrieval"])
    monkeypatch.setattr(
        agent, "suggest_tags_for_text", lambda text, all_tags: ["Topic/Retrieval"]
    )

    def editor(**kwargs):
        suggestions = kwargs["suggest_tags"]("Final note")
        return "Final note", suggestions

    def prompt(all_tags, top_level_tags, all_paths, suggested_tags=()):
        assert "Project" in top_level_tags
        assert "Project/DiaryAgent" in all_paths
        assert suggested_tags == ["Topic/Retrieval"]
        return ["Project/DiaryAgent"]

    monkeypatch.setattr(commands, "launch_editor", editor)
    monkeypatch.setattr(commands, "prompt_for_section_tags", prompt)
    assert commands.run_capture(agent, day_text="26_03_2026") == 0
    section = agent.parse_day_sections(tmp_path / "26_03_2026.md")[0]
    assert section.body == "Final note"
    assert adapter.section_tags(section) == ["DiaryAgent"]


def test_run_show_day_hides_llm_tag_suggestions_when_model_missing(
    monkeypatch, tmp_path
):
    """VIEW-01/02/07: observable contract regression."""
    agent = DiaryAgent(diary_dir=tmp_path, model=None)
    target = tmp_path / "05_03_2026.md"
    target.write_text("## 14:30\n\n- note\n", encoding="utf-8")

    recorded = {}

    def fake_show_diary_entry(*args, **kwargs):
        recorded["suggest_tags"] = kwargs.get("suggest_tags")
        recorded["set_tags"] = kwargs.get("set_tags")
        return None

    monkeypatch.setattr(commands, "show_diary_entry", fake_show_diary_entry)
    monkeypatch.setattr(commands, "get_htfs_adapter", lambda *_args: None)

    exit_code = commands.run_show_day(agent, day_text="05_03_2026")

    assert exit_code == 0
    assert recorded["suggest_tags"] is None


def test_comma_separated_tag_completer_completes_after_commas():
    """TAG-03: observable contract regression."""
    if (
        not hasattr(ui, "_CommaSeparatedTagCompleter")
        or ui._CommaSeparatedTagCompleter is None
    ):
        pytest.skip("prompt_toolkit not available")

    completer = ui._CommaSeparatedTagCompleter(
        ["Project/DiaryAgent", "Topic/Personal", "Topic/Work"]
    )

    class FakeDocument:
        def __init__(self, text_before_cursor):
            self.text_before_cursor = text_before_cursor

    first = list(completer.get_completions(FakeDocument("To"), None))
    second = list(
        completer.get_completions(FakeDocument("Project/DiaryAgent, To"), None)
    )
    exact = list(completer.get_completions(FakeDocument("Project/DiaryAgent, "), None))

    assert [c.text for c in first] == ["Topic/Personal", "Topic/Work"]
    assert [c.text for c in second] == ["Topic/Personal", "Topic/Work"]
    assert [c.text for c in exact] == [
        "Project/DiaryAgent",
        "Topic/Personal",
        "Topic/Work",
    ]
    assert all(c.start_position == -2 for c in second)


def test_synthesize_entry_strips_headings_and_preserves_nested_bullets(monkeypatch):
    """CAP-03: observable contract regression."""

    class FakeOllama:
        @staticmethod
        def chat(*, model, messages):
            return {
                "message": {
                    "content": "## Work\n- Project work\n  - Finished auth cleanup\n  - Added tests"
                }
            }

    monkeypatch.setattr(llm, "ollama", FakeOllama())

    synthesized = llm.synthesize_entry(
        model="test-model",
        raw_update="worked on project",
        today_context="",
    )

    assert synthesized == (
        "- Project work\n" "  - Finished auth cleanup\n" "  - Added tests"
    )


def test_scan_pending_tasks_reads_unchecked_todos_from_all_markdown_files(tmp_path):
    """TODO-01, DATA-06: observable contract regression."""
    (tmp_path / "25_03_2026.md").write_text(
        "- [ ] first task [due: 2026-04-01] [priority: high]\n- [x] done task\n",
        encoding="utf-8",
    )
    (tmp_path / "26_03_2026.md").write_text(
        "notes\n- [ ] second task\n",
        encoding="utf-8",
    )
    (tmp_path / "ignore.txt").write_text("- [ ] ignored\n", encoding="utf-8")
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")

    tasks = agent.scan_pending_tasks()

    assert [
        (task.file_path.name, task.line_number, task.text, task.due, task.priority)
        for task in tasks
    ] == [
        ("25_03_2026.md", 1, "first task", "2026-04-01", "high"),
        ("26_03_2026.md", 2, "second task", None, None),
    ]


def test_todo_proposal_ignores_optional_todo_metadata(tmp_path):
    """TODO-04–05, CAP-11/13 (proposal only; saving requires consent): observable contract regression."""
    (tmp_path / "25_03_2026.md").write_text(
        "- [ ] Buy milk [due: tomorrow]\n",
        encoding="utf-8",
    )
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")

    deduped = agent.dedupe_entry(
        "- [ ] buy milk! [priority: high]\n"
        "- [ ] Call mom [due: Friday]\n"
        "- regular note\n"
    )

    assert deduped == "- [ ] Call mom [due: Friday]\n- regular note"


def test_todo_proposal_removes_existing_and_new_duplicate_open_todos(tmp_path):
    """TODO-04–05, CAP-11/13 (proposal only; saving requires consent): observable contract regression."""
    (tmp_path / "25_03_2026.md").write_text(
        "- [ ] Buy milk\n",
        encoding="utf-8",
    )
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")

    deduped = agent.dedupe_entry(
        "- [ ] buy milk!\n" "- [ ] Call mom\n" "- [ ] call mom\n" "- regular note\n"
    )

    assert deduped == "- [ ] Call mom\n- regular note"


def test_todo_proposal_can_omit_a_declined_similar_task(monkeypatch, tmp_path):
    """TODO-04–05, CAP-11/13 (proposal only; saving requires consent): observable contract regression."""
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")
    existing = models.PendingTask(
        file_path=Path("25_03_2026.md"),
        line_number=3,
        text="Submit expenses",
    )
    match = models.SimilarTodoMatch(
        candidate_text="Submit expense report",
        existing_task=existing,
    )
    monkeypatch.setattr(
        agent,
        "find_similar_open_todo",
        lambda text: match if "expense" in text else None,
    )

    entry, skipped = agent.review_entry_todos(
        "- [ ] Submit expense report\n- regular note",
        confirm=lambda _match: False,
    )

    assert entry == "- regular note"
    assert skipped == [match]


def test_search_returns_best_matching_history_chunks(tmp_path):
    """SEARCH-01–06: observable contract regression."""
    (tmp_path / "25_03_2026.md").write_text(
        "- fixed login bug\n\n- planned team lunch\n",
        encoding="utf-8",
    )
    (tmp_path / "26_03_2026.md").write_text(
        "- login bug resurfaced in staging\n",
        encoding="utf-8",
    )
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")

    results = agent.search("login bug", limit=2)

    assert len(results) == 2
    assert {result.file_path.name for result in results} == {
        "25_03_2026.md",
        "26_03_2026.md",
    }
    assert all("login bug" in result.snippet.lower() for result in results)
    assert all(result.score > 0 for result in results)


def test_search_attaches_section_tags_to_matching_excerpts(monkeypatch, tmp_path):
    """SEARCH-01–06: observable contract regression."""
    (tmp_path / "25_03_2026.md").write_text(
        "## 14:30\n\n- fixed login bug\n",
        encoding="utf-8",
    )

    class FakeAdapter:
        def __init__(self, *args, **kwargs):
            pass

        def section_tags(self, section):
            return ["Project/DiaryAgent"] if section.heading == "14:30" else []

    monkeypatch.setattr(service, "HTFSAdapter", FakeAdapter)
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")

    results = agent.search("login bug", limit=1)

    assert len(results) == 1
    assert results[0].section_tags == ("Project/DiaryAgent",)


def test_search_matches_sections_via_tags(monkeypatch, tmp_path):
    """SEARCH-01–06: observable contract regression."""
    (tmp_path / "25_03_2026.md").write_text(
        "## 14:30\n\n- unrelated notes\n",
        encoding="utf-8",
    )

    class FakeAdapter:
        def __init__(self, *args, **kwargs):
            pass

        def section_tags(self, section):
            return ["Project/DiaryAgent"] if section.heading == "14:30" else []

    monkeypatch.setattr(service, "HTFSAdapter", FakeAdapter)
    agent = DiaryAgent(diary_dir=tmp_path, model=None)

    results = agent.search("DiaryAgent", limit=5)

    assert len(results) == 1
    assert results[0].file_path.name == "25_03_2026.md"
    assert results[0].section_tags == ("Project/DiaryAgent",)
    assert "unrelated notes" in results[0].snippet
    assert results[0].score > 0


def test_run_search_falls_back_to_basic_text_search_when_llm_is_unavailable(
    monkeypatch, tmp_path, capsys
):
    """SEARCH-01–06: observable contract regression."""
    (tmp_path / "25_03_2026.md").write_text(
        "## 14:30\n\n- fixed login bug\n",
        encoding="utf-8",
    )

    class FakeAdapter:
        def __init__(self, *args, **kwargs):
            pass

        def section_tags(self, section):
            return ["Project/DiaryAgent"]

    monkeypatch.setattr(service, "HTFSAdapter", FakeAdapter)
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")

    def fake_answer_query(_query, _matches):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(agent, "answer_query", fake_answer_query)

    exit_code = commands.run_search(agent, "login bug")
    captured = capsys.readouterr()

    assert exit_code == 0
    assert (
        "Warning: LLM search is unavailable; showing basic text search results instead."
        in captured.err
    )
    assert "Basic text search results:" in captured.out
    assert "[25_03_2026.md#14:30] [tags: Project/DiaryAgent]" in captured.out
    assert "fixed login bug" in captured.out


def test_run_search_supports_raw_tag_expressions_without_llm(
    monkeypatch, tmp_path, capsys
):
    """SEARCH-01–06: observable contract regression."""
    (tmp_path / "25_03_2026.md").write_text(
        "## 14:30\n\n- fixed login bug\n", encoding="utf-8"
    )
    agent = DiaryAgent(diary_dir=tmp_path, model=None)

    class FakeAdapter:
        def __init__(self, *args, **kwargs):
            self.expressions = []

        def get_all_tag_paths(self):
            return ["Project/DiaryAgent", "Topic/Retrieval"]

        def query_resource_paths(self, expression):
            self.expressions.append(expression)
            return [f"{tmp_path / '25_03_2026.md'}#14:30"]

        def load_section_by_resource_path(self, agent_obj, resource_path):
            return models.DiarySection(
                tmp_path / "25_03_2026.md", "14:30", "- fixed login bug"
            )

        def section_tags(self, section):
            return ["Project/DiaryAgent"]

    fake_adapter = FakeAdapter()
    monkeypatch.setattr(commands, "get_htfs_adapter", lambda *_args: fake_adapter)

    exit_code = commands.run_search(agent, tag_filter="Project/DiaryAgent")
    captured = capsys.readouterr()

    assert exit_code == 0
    assert fake_adapter.expressions == ["Project/DiaryAgent"]
    assert "Tag search results:" in captured.out
    assert "[25_03_2026.md#14:30] [tags: Project/DiaryAgent]" in captured.out
    assert "fixed login bug" in captured.out


def test_run_search_translates_natural_language_tag_filters_when_llm_enabled(
    monkeypatch, tmp_path, capsys
):
    """SEARCH-01–06: observable contract regression."""
    (tmp_path / "25_03_2026.md").write_text(
        "## 14:30\n\n- fixed login bug\n", encoding="utf-8"
    )
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")

    class FakeAdapter:
        def __init__(self, *args, **kwargs):
            self.expressions = []

        def get_all_tag_paths(self):
            return ["Project/DiaryAgent", "Topic/Retrieval"]

        def query_resource_paths(self, expression):
            self.expressions.append(expression)
            return [f"{tmp_path / '25_03_2026.md'}#14:30"]

        def load_section_by_resource_path(self, agent_obj, resource_path):
            return models.DiarySection(
                tmp_path / "25_03_2026.md", "14:30", "- fixed login bug"
            )

        def section_tags(self, section):
            return ["Project/DiaryAgent"]

    fake_adapter = FakeAdapter()
    monkeypatch.setattr(commands, "get_htfs_adapter", lambda *_args: fake_adapter)
    monkeypatch.setattr(
        agent,
        "tag_expression_from_natural_language",
        lambda request, available_tags: (
            "(Project/DiaryAgent|Topic/Retrieval)" if "login" in request else ""
        ),
    )

    exit_code = commands.run_search(agent, tag_filter="login work")
    captured = capsys.readouterr()

    assert exit_code == 0
    assert fake_adapter.expressions == ["(Project/DiaryAgent|Topic/Retrieval)"]
    assert "Tag search results:" in captured.out
    assert "[25_03_2026.md#14:30] [tags: Project/DiaryAgent]" in captured.out


def test_answer_query_includes_section_tags_in_prompt(monkeypatch):
    """SEARCH-01–06: observable contract regression."""
    captured = {}

    class FakeOllama:
        @staticmethod
        def chat(*, model, messages):
            captured["model"] = model
            captured["messages"] = messages
            return {"message": {"content": "Answer"}}

    monkeypatch.setattr(llm, "ollama", FakeOllama())

    answer = llm.answer_query(
        model="test-model",
        query="What happened with login bugs?",
        matches=[
            models.SearchResult(
                file_path=Path("25_03_2026.md"),
                snippet="- fixed login bug",
                score=3,
                section_tags=("Project/DiaryAgent", "Topic/Retrieval"),
            )
        ],
    )

    assert answer == "Answer"
    user_message = captured["messages"][1]["content"]
    assert "Tags: Project/DiaryAgent, Topic/Retrieval" in user_message
    assert captured["model"] == "test-model"


def test_parse_explicit_day_input_accepts_dd_mm_yyyy():
    """DATA-04: observable contract regression."""
    normalized = commands.parse_explicit_day_input("05_03_2026")

    assert normalized == "05_03_2026"


def test_parse_explicit_day_input_accepts_relative_days():
    """DATA-04: observable contract regression."""
    import datetime as dt

    today = dt.date.today()
    yesterday = (today - dt.timedelta(days=1)).strftime("%d_%m_%Y")
    tomorrow = (today + dt.timedelta(days=1)).strftime("%d_%m_%Y")
    today_str = today.strftime("%d_%m_%Y")

    assert commands.parse_explicit_day_input("0") == today_str
    assert commands.parse_explicit_day_input("-1") == yesterday
    assert commands.parse_explicit_day_input("+1") == tomorrow
    assert commands.parse_explicit_day_input("1") == tomorrow


def test_parse_explicit_day_input_rejects_non_dd_mm_yyyy():
    """DATA-04: observable contract regression."""
    with pytest.raises(
        RuntimeError, match=r"Use dd_mm_yyyy, or relative days like -1, \+1, 0"
    ):
        commands.parse_explicit_day_input("5 March 2026")


def test_entry_options_are_sorted_newest_first_with_preview_and_search_text(tmp_path):
    """SEARCH-01–06: observable contract regression."""
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")
    (tmp_path / "25_03_2026.md").write_text("\n- earlier entry\n", encoding="utf-8")
    (tmp_path / "27_03_2026.md").write_text(
        "- latest entry\nsecond line\n", encoding="utf-8"
    )

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
    """VIEW-01/02/07: observable contract regression."""
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")
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
        commands,
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
    monkeypatch.setattr(
        agent,
        "adjacent_entry",
        lambda path, step: (
            ("04_03_2026.md", "- prior") if step < 0 else ("06_03_2026.md", "- next")
        ),
    )
    monkeypatch.setattr(
        agent,
        "entry_options",
        lambda: [
            models.DiaryEntryOption(
                target, "05 Mar 2026", "- Met with product", "05_03_2026"
            )
        ],
    )

    exit_code = commands.run_show_day(agent, day_text="05_03_2026")

    assert exit_code == 0
    assert shown == {
        "title": "05_03_2026.md",
        "body": "- Met with product\n- [ ] Send notes",
        "previous": ("04_03_2026.md", "- prior"),
        "next": ("06_03_2026.md", "- next"),
        "picked": [
            models.DiaryEntryOption(
                target, "05 Mar 2026", "- Met with product", "05_03_2026"
            )
        ],
    }


def test_run_show_day_defaults_to_today_when_day_omitted(monkeypatch, tmp_path):
    """VIEW-01/02/07: observable contract regression."""
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")
    today = dt.date(2026, 3, 28)
    target = agent.today_file(today)
    target.write_text("- Defaulted to today\n", encoding="utf-8")
    monkeypatch.setattr(agent, "ensure_storage", lambda: None)

    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return today

    monkeypatch.setattr(commands.dt, "date", FixedDate)
    shown = {}
    monkeypatch.setattr(
        commands,
        "show_diary_entry",
        lambda title, body, previous_entry=None, next_entry=None, pick_entry=None, get_tags=None, toggle_todo=None, **kwargs: shown.update(
            {"title": title, "body": body}
        ),
    )

    exit_code = commands.run_show_day(agent)

    assert exit_code == 0
    assert shown == {
        "title": "28_03_2026.md",
        "body": "- Defaulted to today",
    }


def test_run_show_day_asks_to_show_latest_entry_when_today_missing(
    monkeypatch, tmp_path
):
    """VIEW-01/02/07: observable contract regression."""
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")
    today = dt.date(2026, 4, 5)
    older = tmp_path / "31_03_2026.md"
    latest = tmp_path / "01_04_2026.md"
    older.write_text("- Older entry\n", encoding="utf-8")
    latest.write_text("- Most recent entry\n", encoding="utf-8")
    monkeypatch.setattr(agent, "ensure_storage", lambda: None)

    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return today

    monkeypatch.setattr(commands.dt, "date", FixedDate)
    asked = {}
    monkeypatch.setattr(
        commands,
        "confirm_show_latest_entry",
        lambda requested_title, latest_title: asked.update(
            {"requested": requested_title, "latest": latest_title}
        )
        or True,
    )
    shown = {}
    monkeypatch.setattr(
        commands,
        "show_diary_entry",
        lambda title, body, previous_entry=None, next_entry=None, pick_entry=None, get_tags=None, toggle_todo=None, **kwargs: shown.update(
            {"title": title, "body": body}
        ),
    )

    exit_code = commands.run_show_day(agent)

    assert exit_code == 0
    assert asked == {
        "requested": "05_04_2026",
        "latest": "01_04_2026",
    }
    assert shown == {
        "title": "01_04_2026.md",
        "body": "- Most recent entry",
    }


def test_run_show_day_falls_back_to_stdout_when_ui_unavailable(
    monkeypatch, tmp_path, capsys
):
    """VIEW-01/02/07: observable contract regression."""
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")
    target = tmp_path / "05_03_2026.md"
    target.write_text("- Met with product\n- [ ] Send notes\n", encoding="utf-8")
    monkeypatch.setattr(agent, "ensure_storage", lambda: None)
    monkeypatch.setattr(
        agent,
        "file_for_day_input",
        lambda day_text: target,
    )
    monkeypatch.setattr(
        ui,
        "require_prompt_toolkit",
        lambda: (_ for _ in ()).throw(RuntimeError("missing prompt_toolkit")),
    )

    exit_code = commands.run_show_day(agent, day_text="05_03_2026")

    assert exit_code == 0
    assert (
        capsys.readouterr().out
        == "[05_03_2026.md]\n- Met with product\n- [ ] Send notes\n"
    )


def test_run_show_day_reports_missing_file(monkeypatch, tmp_path, capsys):
    """VIEW-01/02/07: observable contract regression."""
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")
    target = tmp_path / "05_03_2026.md"
    monkeypatch.setattr(agent, "ensure_storage", lambda: None)
    monkeypatch.setattr(
        agent,
        "file_for_day_input",
        lambda day_text: target,
    )

    exit_code = commands.run_show_day(agent, day_text="05_03_2026")

    assert exit_code == 0
    assert capsys.readouterr().out == "No diary entry found for 05_03_2026.\n"


def test_build_parser_accepts_show_without_day():
    """CLI-01: observable contract regression."""
    parser = cli.build_parser()

    args = parser.parse_args(["show"])

    assert args.command == "show"
    assert args.day is None


def test_build_parser_accepts_capture_day():
    """CLI-01: observable contract regression."""
    parser = cli.build_parser()

    args = parser.parse_args(["capture", "--day", "25_03_2026", "--text", "backfill"])

    assert args.command == "capture"
    assert args.day == "25_03_2026"
    assert args.text == "backfill"


def test_run_tags_show_prints_all_sections_tags_when_time_is_none(
    monkeypatch, tmp_path, capsys
):
    """TAG-02–06: observable contract regression."""
    agent = DiaryAgent(diary_dir=tmp_path, model="test-model")
    day_file = tmp_path / "26_03_2026.md"
    day_file.write_text(
        "## 10:00\n- first note\n## 14:30\n- second note", encoding="utf-8"
    )

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

    monkeypatch.setattr(commands, "get_htfs_adapter", lambda *_args: FakeAdapter())

    exit_code = commands.run_tags_show(agent, "26_03_2026", None)

    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "[26_03_2026.md#10:00]" in captured
    assert "  Topic/Personal" in captured
    assert "[26_03_2026.md#14:30]" in captured
    assert "  Project/DiaryAgent" in captured


def test_build_parser_accepts_tags_show_without_time():
    """CLI-01: observable contract regression."""
    parser = cli.build_parser()
    args = parser.parse_args(["tags", "show", "26_03_2026"])
    assert args.command == "tags"
    assert args.tags_command == "show"
    assert args.day == "26_03_2026"
    assert args.time is None
