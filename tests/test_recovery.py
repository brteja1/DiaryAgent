"""PERSIST-01–05: observed store outcomes and replay safety, using real HTFS."""

import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from diary_agent_app import cli, commands, core, llm, service
from diary_agent_app.htfs_adapter import HTFSAdapter
from diary_agent_app.models import AppConfig
from diary_agent_app.persistence import OperationJournal, PersistenceError
from diary_agent_app.service import DiaryAgent


@pytest.fixture
def tagged(tmp_path):
    path = tmp_path / "14_11_2026.md"
    path.write_bytes(b"Preamble  \r\n## 09:00\r\n\r\nA note  \r\n")
    agent = DiaryAgent(tmp_path, None)
    section = agent.section_for_id(path.name + "#09:00")
    agent.set_section_tags(section, ["Old"])
    return agent, path, section, HTFSAdapter(tmp_path)


def test_failed_intent_prevents_content_and_tag_mutation(tagged, monkeypatch):
    """O-PERSIST-02: recording failure cannot start either mutation."""
    agent, path, section, adapter = tagged
    before = path.read_bytes()

    def unavailable(self, operation):
        raise OSError("journal unavailable")

    monkeypatch.setattr(OperationJournal, "save", unavailable)
    for action in [
        lambda: agent.delete_section(path, "09:00"),
        lambda: agent.set_section_tags(section, ["New"]),
        lambda: agent.append_entry_verbatim("New note", "14_11_2026"),
    ]:
        with pytest.raises(RuntimeError, match="mutation not started"):
            action()
        assert path.read_bytes() == before
        assert adapter.section_tags(section) == ["Old"]


def test_failed_delete_keeps_associations_and_records_intent(tagged, monkeypatch):
    """O-PERSIST-01/02: deletion is content-first and intent is observable before write."""
    agent, path, section, adapter = tagged
    original = path.read_bytes()

    def fail(target, content):
        records = OperationJournal(agent.diary_dir).list()
        assert len(records) == 1
        operation = records[0]
        assert operation.kind == "delete_section"
        assert operation.files[0].before != operation.files[0].intended
        intent = next(t for t in operation.tags if t.heading == "09:00")
        assert intent.before.tags == ["Old"] and intent.intended.tags == []
        assert intent.mode == "remove"
        raise OSError("disk refused deletion")

    monkeypatch.setattr(service, "write_markdown", fail)
    with pytest.raises(PersistenceError) as error:
        agent.delete_section(path, "09:00")
    assert error.value.operation.status == "failed"
    assert path.read_bytes() == original
    assert adapter.section_tags(section) == ["Old"]
    record = OperationJournal(agent.diary_dir).load(error.value.operation.id)
    assert record.files[0].state == "not_written"
    with pytest.raises(PersistenceError, match="never writes content"):
        agent.persistence().retry(record.id)
    assert path.read_bytes() == original and adapter.section_tags(section) == ["Old"]


def test_delete_metadata_retry_never_replays_content_and_keeps_receipt(
    tagged, monkeypatch
):
    """O-PERSIST-03/04/05: content stays deleted; metadata-only retry and receipt."""
    agent, path, section, adapter = tagged
    delete = HTFSAdapter.delete_section_resource

    def fail(self, target):
        raise RuntimeError("backend offline")

    monkeypatch.setattr(HTFSAdapter, "delete_section_resource", fail)
    with pytest.raises(PersistenceError) as error:
        agent.delete_section(path, "09:00")
    record = error.value.operation
    assert record.status == "partial"
    assert path.read_bytes() == b"Preamble  \r\n"
    assert adapter.section_tags(section) == ["Old"]
    monkeypatch.setattr(HTFSAdapter, "delete_section_resource", delete)
    monkeypatch.setattr(
        service, "write_markdown", lambda *a: pytest.fail("retry replayed content")
    )
    assert agent.persistence().retry(record.id).status == "complete"
    assert not adapter.section_resource_exists(section)
    # Later manual content/tag changes must survive replay of a completed ID.
    path.write_text("## 09:00\n\nManual note\n")
    adapter.tag_section(section, ["Old"])
    assert agent.persistence().retry(record.id).status == "complete"
    assert adapter.section_tags(section) == ["Old"]
    assert path.read_text() == "## 09:00\n\nManual note\n"


@pytest.mark.parametrize("divergence", ["content", "tags", "duplicate"])
def test_retry_rejects_divergence_without_metadata_mutation(
    tagged, monkeypatch, divergence
):
    """O-PERSIST-04: check state/identity before retry, never guess a target."""
    agent, path, section, adapter = tagged
    apply = HTFSAdapter.tag_section
    monkeypatch.setattr(
        HTFSAdapter,
        "tag_section",
        lambda *a: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    with pytest.raises(PersistenceError) as error:
        agent.set_section_tags(section, ["New"])
    identifier = error.value.operation.id
    monkeypatch.setattr(HTFSAdapter, "tag_section", apply)
    if divergence == "content":
        path.write_text("External content change")
    elif divergence == "duplicate":
        path.write_text("## 09:00\n\nOne\n## 09:00\n\nTwo\n")
    else:
        adapter.add_tags(["External"])
        adapter.tag_section(section, ["External"])
    current = path.read_bytes(), adapter.section_tags(section)
    with pytest.raises(PersistenceError) as conflict:
        agent.persistence().retry(identifier)
    assert conflict.value.operation.status == "conflict"
    assert (path.read_bytes(), adapter.section_tags(section)) == current


def test_partial_tag_replacement_retries_with_prior_and_intended_state(
    tagged, monkeypatch
):
    """O-TAG-07/O-PERSIST-05: partial state is recorded; no rollback is assumed."""
    agent, path, section, adapter = tagged
    before = path.read_bytes()
    apply = HTFSAdapter.tag_section
    monkeypatch.setattr(HTFSAdapter, "tag_section", lambda *a: ["New"])
    with pytest.raises(PersistenceError, match="rejected") as failure:
        agent.set_section_tags(section, ["New"])
    operation = OperationJournal(agent.diary_dir).load(failure.value.operation.id)
    assert operation.status == "uncertain"
    assert operation.tags[0].before.tags == ["Old"]
    assert operation.tags[0].intended.tags == ["New"]
    assert adapter.section_tags(section) == []
    monkeypatch.setattr(HTFSAdapter, "tag_section", apply)
    assert agent.persistence().retry(operation.id).status == "complete"
    assert adapter.section_tags(section) == ["New"]
    assert path.read_bytes() == before


@pytest.mark.parametrize("stage", ["partial-write", "readback", "receipt"])
def test_uncertain_and_post_write_failures_are_not_success(tagged, monkeypatch, stage):
    """O-PERSIST-03/05: distinguish uncertain bytes from confirmed partial save."""
    agent, path, section, adapter = tagged
    if stage == "partial-write":

        def write(target, content):
            target.write_text("incomplete bytes")
            raise OSError("write interrupted")

        monkeypatch.setattr(service, "write_markdown", write)
    elif stage == "readback":
        observe = HTFSAdapter.section_tags

        def read(self, target):
            if path.read_text().endswith("New body\n"):
                raise RuntimeError("cannot verify metadata after content commit")
            return observe(self, target)

        monkeypatch.setattr(HTFSAdapter, "section_tags", read)
    else:
        save = OperationJournal.save

        def persist(self, operation):
            if operation.status == "complete":
                raise OSError("receipt write unavailable")
            return save(self, operation)

        monkeypatch.setattr(OperationJournal, "save", persist)
    with pytest.raises(PersistenceError) as error:
        agent.update_section(path, "09:00", "New body")
    operation = OperationJournal(agent.diary_dir).load(error.value.operation.id)
    assert operation.status == ("uncertain" if stage == "partial-write" else "partial")
    assert operation.files[0].state == (
        "uncertain" if stage == "partial-write" else "committed"
    )
    assert operation.error


@pytest.mark.parametrize("raises", [False, True])
def test_capture_tag_failure_reports_saved_note_and_recoverable_operation(
    tmp_path, monkeypatch, capsys, raises
):
    """O-PERSIST-03/O-QUAL-03: rejected lists and exceptions cannot report success."""
    monkeypatch.setattr(
        cli, "load_or_initialize_config", lambda: AppConfig(tmp_path, None)
    )
    monkeypatch.setattr(commands, "launch_editor", lambda **kw: ("Saved note", []))
    monkeypatch.setattr(commands, "prompt_for_section_tags", lambda *a, **kw: ["New"])
    apply = HTFSAdapter.tag_section

    def unavailable(*a):
        if raises:
            raise RuntimeError("offline")
        return ["New"]

    monkeypatch.setattr(HTFSAdapter, "tag_section", unavailable)
    assert cli.main(["capture", "--day", "14_11_2026"]) == 1
    output = capsys.readouterr()
    assert "Updated 14_11_2026.md" in output.out
    assert "Note saved; tagging pending" in output.err
    assert "Saved note" in (tmp_path / "14_11_2026.md").read_text()
    pending = OperationJournal(tmp_path).list()
    assert len(pending) == 1 and pending[0].id in output.err
    monkeypatch.setattr(HTFSAdapter, "tag_section", apply)
    assert cli.main(["recovery", "retry", pending[0].id]) == 0
    assert (tmp_path / "14_11_2026.md").read_text().count("Saved note") == 1


def test_taxonomy_retry_checks_associations_and_receipt(tagged, monkeypatch):
    """O-PERSIST-02/04/05, TAG-06: deletion progress and no replay after recreation."""
    agent, path, section, adapter = tagged
    agent.set_section_tags(section, ["Alpha/Beta"])
    delete = HTFSAdapter.delete_tag

    def fail_parent(self, name):
        if name == "Alpha":
            raise RuntimeError("parent deletion unavailable")
        return delete(self, name)

    monkeypatch.setattr(HTFSAdapter, "delete_tag", fail_parent)
    with pytest.raises(PersistenceError) as failure:
        agent.delete_taxonomy_tags(["Beta", "Alpha"])
    record = OperationJournal(agent.diary_dir).load(failure.value.operation.id)
    assert "Beta" not in adapter.list_tags() and "Alpha" in adapter.list_tags()
    assert record.tags[0].before.tags == ["Beta"]
    monkeypatch.setattr(HTFSAdapter, "delete_tag", delete)
    assert agent.persistence().retry(record.id).status == "complete"
    adapter.add_tags(["Alpha/Beta"])
    adapter.tag_section(section, ["Beta"])
    assert agent.persistence().retry(record.id).status == "complete"
    assert adapter.section_tags(section) == ["Beta"]


def test_no_toolkit_can_capture_list_and_show_in_fresh_interpreter(tmp_path):
    """O-CAP-08/O-VIEW-02: exercise actual missing-package import and fallbacks."""
    code = """import importlib.abc,sys
from pathlib import Path
class Missing(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, path, target=None):
  if fullname == 'prompt_toolkit' or fullname.startswith('prompt_toolkit.'):
   raise ModuleNotFoundError('optional terminal package absent')
sys.meta_path.insert(0,Missing())
from diary_agent_app import cli
from diary_agent_app.models import AppConfig
cli.load_or_initialize_config=lambda:AppConfig(Path(sys.argv[1]),None)
assert cli.main(['capture','--day','14_11_2026'])==0
assert cli.main(['todos'])==0
assert cli.main(['show','14_11_2026'])==0
"""
    process = subprocess.run(
        [sys.executable, "-B", "-c", code, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        input="Raw note  \n- [ ] Tomorrow  \n\n",
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert process.returncode == 0, process.stderr
    assert "Raw note" in process.stdout and "Tomorrow" in process.stdout
    assert (
        (tmp_path / "14_11_2026.md")
        .read_text()
        .endswith("Raw note  \n- [ ] Tomorrow  \n")
    )


def test_generated_metadata_is_validated_but_verbatim_legacy_text_is_preserved(
    tmp_path, monkeypatch
):
    """O-TODO-08/O-CAP-13: validation is a proposal guard, never hidden save processing."""
    monkeypatch.setattr(commands.sys.stdin, "isatty", lambda: True)
    invalid = "- [ ] Model task [due: 31-02-2026] [priority: urgent]"
    monkeypatch.setattr(
        llm,
        "ollama",
        SimpleNamespace(chat=lambda **kw: {"message": {"content": invalid}}),
    )
    agent = DiaryAgent(tmp_path, "test-model")
    assert commands.run_capture(agent, "Original note", "14_11_2026") == 0
    path = tmp_path / "14_11_2026.md"
    assert "Model task" not in path.read_text() and "Original note" in path.read_text()
    agent.append_entry_verbatim(invalid, "14_11_2026")
    task = agent.scan_pending_tasks()[0]
    assert task.due == "31-02-2026" and task.priority == "urgent"
    assert task.due_status == task.priority_status == "unvalidated"
    assert "unvalidated" in task.display_text
    assert invalid in path.read_text()


@pytest.mark.parametrize("raw", ["16-11-2026", "2026-11-16", "16_11_2026"])
def test_legacy_due_status_retains_original_spelling(tmp_path, raw):
    """O-TODO-08: recognized dates have equal interpretation and distinct raw spelling."""
    agent = DiaryAgent(tmp_path, None)
    agent.append_entry_verbatim(
        f"- [ ] Task [due: {raw}] [priority: high]", "14_11_2026"
    )
    task = agent.scan_pending_tasks()[0]
    assert task.due == raw and task.due_status == task.priority_status == "validated"


def test_completed_history_cannot_remove_new_open_task(tmp_path):
    """O-TODO-04: compare open-task keys, not state-erased checkbox lines."""
    path = tmp_path / "14_11_2026.md"
    path.write_text("## 09:00\n\n- [x] Buy milk\n")
    agent = DiaryAgent(tmp_path, "test-model")
    assert (
        agent.prepare_rewrite_for_review("- [ ] Buy milk", "14_11_2026")
        == "- [ ] Buy milk"
    )


def test_relative_year_one_produces_navigable_filename(tmp_path):
    """O-DATA-01/04: supported dates remain within the canonical filename carrier."""
    import datetime as dt

    target = str((dt.date(1, 1, 1) - dt.date.today()).days)
    assert core.parse_explicit_day_input(target) == "01_01_0001"
    agent = DiaryAgent(tmp_path, None)
    path, _ = agent.append_entry_verbatim("Year one", target)
    assert path.name == "01_01_0001.md" and agent.dated_diary_files() == [path]


def test_completed_write_with_lost_acknowledgement_retries_metadata_only(
    tagged, monkeypatch
):
    """O-PERSIST-03/04: observe committed bytes even when the write call raises."""
    agent, path, section, adapter = tagged
    write = service.write_markdown

    def lost_acknowledgement(target, text):
        write(target, text)
        raise OSError("acknowledgement lost")

    monkeypatch.setattr(service, "write_markdown", lost_acknowledgement)
    with pytest.raises(PersistenceError) as error:
        agent.delete_section(path, "09:00")
    assert error.value.operation.status == "partial"
    assert adapter.section_tags(section) == ["Old"]
    before_retry = path.read_bytes()
    monkeypatch.setattr(
        service, "write_markdown", lambda *a: pytest.fail("content replayed")
    )
    assert agent.persistence().retry(error.value.operation.id).status == "complete"
    assert path.read_bytes() == before_retry and not adapter.section_resource_exists(
        section
    )


def test_resolution_and_invalid_records_never_replay_metadata(tagged, monkeypatch):
    """O-PERSIST-04/05: explicit resolution is a retained receipt; bad IDs/records fail safely."""
    agent, path, section, adapter = tagged
    apply = HTFSAdapter.tag_section
    monkeypatch.setattr(HTFSAdapter, "tag_section", lambda *a: ["New"])
    with pytest.raises(PersistenceError) as error:
        agent.set_section_tags(section, ["New"])
    journal = OperationJournal(agent.diary_dir)
    identifier = error.value.operation.id
    with pytest.raises(RuntimeError, match="reason"):
        journal.resolve(identifier, " ")
    journal.resolve(identifier, "User chose to keep the current associations")
    monkeypatch.setattr(HTFSAdapter, "tag_section", apply)
    assert agent.persistence().retry(identifier).status == "resolved"
    assert adapter.section_tags(section) == []
    assert journal.load(identifier).tags[0].before.tags == ["Old"]
    with pytest.raises(RuntimeError, match="Invalid recovery"):
        journal.load("../outside")
    data = json.loads(journal.path(identifier).read_text())
    data["files"][0]["name"] = "../outside.md"
    journal.path(identifier).write_text(json.dumps(data))
    with pytest.raises(RuntimeError, match="invalid target filename"):
        agent.persistence().retry(identifier)
    assert adapter.section_tags(section) == []


def test_metadata_close_failure_retains_intent_until_verified(tagged, monkeypatch):
    """O-PERSIST-05: a backend close exception cannot produce a completion receipt."""
    agent, path, section, adapter = tagged
    factory = HTFSAdapter._client

    def client_with_close_failure(self):
        client = factory(self)
        close = client.close

        def fail_after_close():
            changed = "New" in client.get_resource_tags(
                self.resource_path_for_section(section)
            )
            close()
            if changed:
                raise RuntimeError("flush/close acknowledgement unavailable")

        client.close = fail_after_close
        return client

    monkeypatch.setattr(HTFSAdapter, "_client", client_with_close_failure)
    with pytest.raises(PersistenceError) as error:
        agent.set_section_tags(section, ["New"])
    journal = OperationJournal(agent.diary_dir)
    assert journal.load(error.value.operation.id).status == "uncertain"
    monkeypatch.setattr(HTFSAdapter, "_client", factory)
    assert agent.persistence().retry(error.value.operation.id).status == "complete"
    assert adapter.section_tags(section) == ["New"]


def test_viewer_refreshes_committed_deletion_when_metadata_fails(tagged, monkeypatch):
    """VIEW-06/PERSIST-03: retain a usable viewer and display the partial operation."""
    import asyncio
    from diary_agent_app import viewer

    agent, path, section, adapter = tagged
    monkeypatch.setattr(
        HTFSAdapter,
        "delete_section_resource",
        lambda *a: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    notices = []

    async def in_terminal(callback):
        return callback()

    monkeypatch.setattr(viewer, "run_in_terminal", in_terminal)
    monkeypatch.setattr(
        viewer, "button_dialog", lambda **kw: SimpleNamespace(run=lambda **args: True)
    )

    def notice(**kwargs):
        notices.append(kwargs["text"])
        return SimpleNamespace(run=lambda **args: None)

    monkeypatch.setattr(viewer, "message_dialog", notice)

    def run(app, **kwargs):
        buffer = app.layout.current_buffer
        buffer.cursor_position = buffer.text.index("## 09:00")
        handler = app.key_bindings.get_bindings_for_keys(("d",))[-1].handler
        asyncio.run(handler(SimpleNamespace(app=app)))
        assert "## 09:00" not in buffer.text
        assert buffer.text == path.read_text()

    monkeypatch.setattr(viewer.Application, "run", run)
    viewer.show_diary_entry(
        path.name,
        path.read_text(),
        delete_section=lambda title, heading: agent.delete_section(path, heading),
        reload_entry=lambda title: path.read_text(),
    )
    assert len(notices) == 1 and "partial" in notices[0] and "Operation" in notices[0]


@pytest.mark.parametrize(
    "input_line", ["- [ ] Call tomorrow", "- [ ] Call [due: tomorrow]"]
)
def test_out_of_range_proposal_dates_fail_without_mutating_notes(tmp_path, input_line):
    """TODO-02/08: date overflow is explicit; a proposal never writes notes."""
    agent = DiaryAgent(tmp_path, "model")
    with pytest.raises(RuntimeError, match="outside the supported calendar"):
        agent.prepare_rewrite_for_review(input_line, "31_12_9999")
    assert not list(tmp_path.glob("*.md"))


def test_conflicting_known_tag_subset_is_not_adopted_on_repeated_retries(
    tagged, monkeypatch
):
    """O-PERSIST-04: reporting conflict must not turn divergence into a new checkpoint."""
    agent, path, section, adapter = tagged
    apply = HTFSAdapter.tag_section
    monkeypatch.setattr(HTFSAdapter, "tag_section", lambda *a: ["New", "Other"])
    with pytest.raises(PersistenceError) as error:
        agent.set_section_tags(section, ["New", "Other"])
    monkeypatch.setattr(HTFSAdapter, "tag_section", apply)
    adapter.tag_section(section, ["New"])
    for _ in range(2):
        with pytest.raises(PersistenceError) as conflict:
            agent.persistence().retry(error.value.operation.id)
        assert conflict.value.operation.status == "conflict"
        assert adapter.section_tags(section) == ["New"]


def test_persisted_receipt_survives_lost_save_acknowledgement(tagged, monkeypatch):
    """O-PERSIST-04/05: never downgrade an existing completion receipt."""
    agent, path, section, adapter = tagged
    save = OperationJournal.save

    def lost_acknowledgement(self, operation):
        save(self, operation)
        if operation.status == "complete":
            raise OSError("receipt acknowledgement lost")

    monkeypatch.setattr(OperationJournal, "save", lost_acknowledgement)
    assert agent.set_section_tags(section, ["New"]) == ["New"]
    identifier = agent.last_operation_id
    assert OperationJournal(agent.diary_dir).load(identifier).status == "complete"
    adapter.clear_section_tags(section)
    adapter.tag_section(section, ["Old"])
    assert agent.persistence().retry(identifier).status == "complete"
    assert adapter.section_tags(section) == ["Old"]


def test_partial_todo_batch_retains_all_intent_without_replaying_files(
    tmp_path, monkeypatch
):
    """O-PERSIST-02/03/04: no multi-file atomicity claim; retry never completes a second file."""
    first = tmp_path / "14_11_2026.md"
    second = tmp_path / "15_11_2026.md"
    first.write_text("- [ ] First\n")
    second.write_text("- [ ] Second\n")
    agent = DiaryAgent(tmp_path, None)
    tasks = agent.scan_pending_tasks()
    write = service.write_markdown

    def fail_second(path, text):
        if path == second:
            raise OSError("second file unavailable")
        return write(path, text)

    monkeypatch.setattr(service, "write_markdown", fail_second)
    with pytest.raises(PersistenceError) as error:
        agent.mark_tasks_complete(tasks)
    operation = OperationJournal(tmp_path).load(error.value.operation.id)
    assert operation.status == "partial"
    assert [f.state for f in operation.files] == ["committed", "not_written"]
    assert (
        first.read_text() == "- [x] First\n" and second.read_text() == "- [ ] Second\n"
    )
    monkeypatch.setattr(
        service, "write_markdown", lambda *a: pytest.fail("content replayed")
    )
    with pytest.raises(PersistenceError, match="never writes content"):
        agent.persistence().retry(operation.id)
    assert (
        first.read_text() == "- [x] First\n" and second.read_text() == "- [ ] Second\n"
    )


def test_unreadable_completion_acknowledgement_does_not_destroy_receipt(
    tagged, monkeypatch
):
    """O-PERSIST-05: preserve an uninspectable possible receipt rather than downgrading it."""
    agent, path, section, adapter = tagged
    save = OperationJournal.save
    load = OperationJournal.load

    def lost_acknowledgement(self, operation):
        save(self, operation)
        if operation.status == "complete":
            raise OSError("receipt acknowledgement lost")

    monkeypatch.setattr(OperationJournal, "save", lost_acknowledgement)
    monkeypatch.setattr(
        OperationJournal,
        "load",
        lambda *a: (_ for _ in ()).throw(RuntimeError("inspection unavailable")),
    )
    with pytest.raises(PersistenceError) as failure:
        agent.set_section_tags(section, ["New"])
    identifier = failure.value.operation.id
    monkeypatch.setattr(OperationJournal, "load", load)
    assert OperationJournal(agent.diary_dir).load(identifier).status == "complete"
    adapter.clear_section_tags(section)
    adapter.tag_section(section, ["Old"])
    assert agent.persistence().retry(identifier).status == "complete"
    assert adapter.section_tags(section) == ["Old"]


@pytest.mark.parametrize("stage", ["content", "tags", "receipt"])
def test_mutation_interruption_retains_truthful_outcome_and_exit_status(
    tmp_path, monkeypatch, capsys, stage
):
    """CLI-02/PERSIST-02/03: Ctrl+C during I/O cannot hide a committed/unknown write."""
    monkeypatch.setattr(
        cli, "load_or_initialize_config", lambda: AppConfig(tmp_path, None)
    )
    if stage == "content":

        def interrupted(path, text):
            path.write_text("partial bytes")
            raise KeyboardInterrupt

        monkeypatch.setattr(service, "write_markdown", interrupted)
    elif stage == "tags":
        monkeypatch.setattr(commands, "launch_editor", lambda **kw: ("Saved note", []))
        monkeypatch.setattr(
            commands, "prompt_for_section_tags", lambda *a, **kw: ["New"]
        )

        def interrupted(*args):
            raise KeyboardInterrupt

        monkeypatch.setattr(HTFSAdapter, "tag_section", interrupted)
    else:
        save = OperationJournal.save

        def interrupted(self, operation):
            save(self, operation)
            if operation.status == "complete":
                raise KeyboardInterrupt

        monkeypatch.setattr(OperationJournal, "save", interrupted)
    arguments = ["capture", "--day", "14_11_2026"]
    if stage != "tags":
        arguments += ["--text", "Saved note"]
    assert cli.main(arguments) == 130
    output = capsys.readouterr()
    operations = OperationJournal(tmp_path).list(include_complete=True)
    operation = next(
        op
        for op in operations
        if op.kind == ("tag_add" if stage == "tags" else "capture")
    )
    assert operation.id in output.err
    assert operation.status == ("complete" if stage == "receipt" else "uncertain")
    if stage == "content":
        assert (tmp_path / "14_11_2026.md").read_text() == "partial bytes"
    else:
        assert "Saved note" in (tmp_path / "14_11_2026.md").read_text()


def test_adding_another_parent_path_does_not_skip_hierarchy_creation(tagged):
    """TAG-04/05/PERSIST-05: equal leaf sets do not imply equal hierarchy intent."""
    agent, path, section, adapter = tagged
    agent.set_section_tags(section, ["First/Leaf"])
    agent.set_section_tags(section, ["Second/Leaf"], additive=True)
    assert adapter.section_tags(section) == ["Leaf"]
    assert {"First/Leaf", "Second/Leaf"} <= set(adapter.get_all_tag_paths())
    identifier = agent.last_operation_id
    assert OperationJournal(agent.diary_dir).load(identifier).status == "complete"


def test_leaf_projection_retains_backend_tag_spelling(tagged):
    """TAG-04: the projected atomic leaf is the name actually created by HTFS."""
    agent, path, section, adapter = tagged
    agent.set_section_tags(section, ["Parent/Leaf name "])
    assert adapter.section_tags(section) == ["Leaf name "]
    assert "Parent/Leaf name " in adapter.get_all_tag_paths()
