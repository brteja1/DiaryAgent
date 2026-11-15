"""Recorded intent, content-first writes and metadata-only recovery.

The journal is an operation log, not a transaction manager. It never rolls back
Markdown or replays a content write. Completed/resolved records remain receipts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import datetime as dt
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Callable
from uuid import uuid4

from .core import resource_tags_for_specs
from .htfs_adapter import HTFSAdapter
from .markdown import DiaryDocument, read_markdown
from .models import DiarySection


def fingerprint(path: Path) -> str | None:
    return sha256(path.read_bytes()).hexdigest() if path.exists() else None


def text_fingerprint(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


@dataclass
class FileIntent:
    name: str
    before: str | None
    intended: str | None
    state: str = "unchanged"


@dataclass
class TagState:
    exists: bool
    tags: list[str]


@dataclass
class TagIntent:
    file: str
    heading: str
    before: TagState
    intended: TagState
    mode: str = "preserve"
    specs: list[str] = field(default_factory=list)
    checkpoint: TagState | None = None
    in_flight: list[TagState] = field(default_factory=list)


@dataclass
class Operation:
    id: str
    kind: str
    files: list[FileIntent]
    tags: list[TagIntent]
    status: str = "prepared"
    error: str | None = None
    created: str = field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat()
    )
    completed: str | None = None
    resolution: str | None = None
    schema_version: int = 1
    metadata_started: bool = False
    taxonomy_delete: list[str] = field(default_factory=list)
    taxonomy_before: dict[str, list[str]] | None = None
    taxonomy_checkpoint: dict[str, list[str]] | None = None
    taxonomy_in_flight: dict[str, list[str]] | None = None

    @property
    def committed_files(self) -> list[str]:
        return [item.name for item in self.files if item.state == "committed"]


class PersistenceError(RuntimeError):
    """Carries an inspectable operation identity and a truthful observed outcome."""

    def __init__(self, operation: Operation, detail: str):
        self.operation = operation
        files = ", ".join(operation.committed_files)
        content = f"content saved in {files}; " if files else ""
        super().__init__(
            f"{content}{operation.kind} {operation.status}: {detail}. Operation {operation.id}; "
            f"inspect with recovery show {operation.id}"
        )


class RecoveryConflict(RuntimeError):
    """Observed state no longer matches this operation's recorded targets."""


class PersistenceInterrupted(KeyboardInterrupt):
    """Interruption with an operation identity and observed store outcome."""

    def __init__(self, error: PersistenceError):
        self.operation = error.operation
        super().__init__(str(error))


class OperationJournal:
    def __init__(self, diary_dir: Path):
        self.directory = diary_dir / ".diary-agent" / "operations"

    def path(self, identifier: str) -> Path:
        if re.fullmatch(r"[0-9a-f]{32}", identifier) is None:
            raise RuntimeError("Invalid recovery operation ID.")
        return self.directory / f"{identifier}.json"

    def save(self, operation: Operation) -> None:
        """Replace a complete record only after flushing its temporary file."""
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.directory,
                prefix=".intent-",
                delete=False,
            ) as target:
                temporary = Path(target.name)
                json.dump(asdict(operation), target, indent=2, ensure_ascii=False)
                target.write("\n")
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.path(operation.id))
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def create(self, operation: Operation) -> None:
        if self.path(operation.id).exists():
            raise RuntimeError("Recovery operation ID already exists.")
        try:
            self.save(operation)
        except OSError as exc:
            raise RuntimeError(
                f"Cannot record recovery intent; mutation not started: {exc}"
            ) from exc

    def load(self, identifier: str) -> Operation:
        try:
            data = json.loads(self.path(identifier).read_text(encoding="utf-8"))
            if data["id"] != identifier or data["schema_version"] != 1:
                raise ValueError("operation identity/schema mismatch")
            files = [FileIntent(**item) for item in data.pop("files")]
            tags = []
            for item in data.pop("tags"):
                item["before"] = TagState(**item["before"])
                item["intended"] = TagState(**item["intended"])
                if item["checkpoint"] is not None:
                    item["checkpoint"] = TagState(**item["checkpoint"])
                item["in_flight"] = [TagState(**state) for state in item["in_flight"]]
                tags.append(TagIntent(**item))
            operation = Operation(files=files, tags=tags, **data)
            for name in [f.name for f in files] + [t.file for t in tags]:
                if Path(name).name != name or Path(name).suffix != ".md":
                    raise ValueError("invalid target filename")
            if operation.status not in {
                "prepared",
                "pending",
                "failed",
                "partial",
                "uncertain",
                "conflict",
                "complete",
                "resolved",
            }:
                raise ValueError("invalid operation status")
            if any(
                t.mode not in {"preserve", "replace", "add", "remove", "taxonomy"}
                for t in tags
            ):
                raise ValueError("invalid metadata action")
            return operation
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RuntimeError(
                f"Cannot inspect recovery operation {identifier}: {exc}"
            ) from exc

    def list(self, include_complete: bool = False) -> list[Operation]:
        if not self.directory.exists():
            return []
        operations = [
            self.load(path.stem) for path in sorted(self.directory.glob("*.json"))
        ]
        return [
            op
            for op in operations
            if include_complete or op.status not in {"complete", "resolved"}
        ]

    def resolve(self, identifier: str, reason: str) -> Operation:
        operation = self.load(identifier)
        if operation.status in {"complete", "resolved"}:
            return operation
        if not reason.strip():
            raise RuntimeError("An explicit resolution reason is required.")
        operation.status = "resolved"
        operation.resolution = reason
        operation.completed = dt.datetime.now(dt.timezone.utc).isoformat()
        self.save(operation)
        return operation


class DiaryPersistence:
    def __init__(self, diary_dir: Path, adapter: HTFSAdapter):
        self.root = diary_dir
        self.adapter = adapter
        self.journal = OperationJournal(diary_dir)

    def _section(self, intent: TagIntent) -> DiarySection:
        return DiarySection(self.root / intent.file, intent.heading, "")

    def _observe(self, intent: TagIntent) -> TagState:
        section = self._section(intent)
        # Each adapter call closes/flushes its session before this observation
        # is used as verified progress or a completion receipt.
        return TagState(
            self.adapter.section_resource_exists(section),
            sorted(set(self.adapter.section_tags(section))),
        )

    def _snapshot(self, file: str, heading: str) -> TagIntent:
        intent = TagIntent(file, heading, TagState(False, []), TagState(False, []))
        state = self._observe(intent)
        intent.before = state
        intent.intended = state
        intent.checkpoint = state
        return intent

    def _prepare(
        self, kind: str, changes: dict[Path, str], target: TagIntent | None = None
    ) -> Operation:
        files, tags = [], []
        for path, intended in changes.items():
            if path.parent.resolve() != self.root.resolve():
                raise RuntimeError("Content target is outside the diary directory.")
            before = read_markdown(path)
            files.append(
                FileIntent(
                    path.name, fingerprint(path), text_fingerprint(intended), "pending"
                )
            )
            headings = {span.heading for span in DiaryDocument.parse(before).spans}
            headings.update(
                span.heading for span in DiaryDocument.parse(intended).spans
            )
            tags.extend(
                self._snapshot(path.name, heading) for heading in sorted(headings)
            )
        if target is not None:
            tags = [
                t for t in tags if (t.file, t.heading) != (target.file, target.heading)
            ] + [target]
            if not files:
                path = self.root / target.file
                current = fingerprint(path)
                files = [FileIntent(target.file, current, current)]
        operation = Operation(uuid4().hex, kind, files, tags)
        self.journal.create(operation)
        return operation

    def _fail(
        self,
        operation: Operation,
        exc: BaseException,
        *,
        conflict: bool = False,
        preserve_record: bool = False,
    ) -> PersistenceError:
        operation.error = str(exc) or type(exc).__name__
        if conflict:
            operation.status = "conflict"
        elif operation.committed_files:
            operation.status = "partial"
        elif operation.metadata_started or any(
            f.state == "uncertain" for f in operation.files
        ):
            operation.status = "uncertain"
        else:
            operation.status = "failed"
        # A metadata failure may have applied part of its intended changes.
        # Capture that observation, but never authorize overwriting foreign tags.
        for intent in operation.tags:
            if (
                conflict
                or not operation.metadata_started
                or intent.mode == "preserve"
                or not intent.in_flight
                or intent.before == intent.intended
            ):
                continue
            try:
                current = self._observe(intent)
                if set(current.tags) <= set(intent.before.tags) | set(
                    intent.intended.tags
                ):
                    intent.checkpoint = current
            except Exception:
                pass  # Observation is unavailable; retain intent/in-flight evidence.
        detail = str(exc) or type(exc).__name__
        if preserve_record:
            return PersistenceError(
                operation,
                detail
                + "; completion receipt could not be inspected; original record retained",
            )
        try:
            self.journal.save(operation)
        except Exception as journal_error:
            detail += f"; progress could not be saved ({journal_error}); original intent retained"
        return PersistenceError(operation, detail)

    def _recover_or_raise(self, operation: Operation, exc: BaseException) -> Operation:
        if operation.status == "complete":
            # A save may have persisted the receipt and then lost its acknowledgement.
            # Never replace an existing completion receipt with a pending record.
            try:
                receipt = self.journal.load(operation.id)
            except RuntimeError:
                error = self._fail(operation, exc, preserve_record=True)
                if isinstance(exc, KeyboardInterrupt):
                    raise PersistenceInterrupted(error) from exc
                raise error from exc
            if receipt.status in {"complete", "resolved"}:
                if isinstance(exc, KeyboardInterrupt):
                    raise PersistenceInterrupted(
                        PersistenceError(
                            receipt, "Interrupted after verified completion"
                        )
                    ) from exc
                return receipt
        error = self._fail(operation, exc, conflict=isinstance(exc, RecoveryConflict))
        if isinstance(exc, KeyboardInterrupt):
            raise PersistenceInterrupted(error) from exc
        raise error from exc

    def content_change(
        self,
        changes: dict[Path, str],
        kind: str,
        write: Callable[[Path, str], None],
        *,
        delete: DiarySection | None = None,
    ) -> Operation:
        target = None
        if delete is not None:
            target = self._snapshot(delete.file_path.name, delete.heading)
            target.mode = "remove"
            target.intended = TagState(False, [])
        operation = self._prepare(kind, changes, target)
        try:
            for intent in operation.files:
                path = self.root / intent.name
                if fingerprint(path) != intent.before:
                    raise RecoveryConflict(
                        "Content changed before writing; inspect and reselect."
                    )
                if intent.before == intent.intended:
                    intent.state = "unchanged"
                    continue
                try:
                    write(path, changes[path])
                finally:
                    try:
                        current = fingerprint(path)
                        intent.state = (
                            "committed"
                            if current == intent.intended
                            else (
                                "not_written"
                                if current == intent.before
                                else "uncertain"
                            )
                        )
                    except OSError:
                        intent.state = "uncertain"
                if intent.state != "committed":
                    raise RuntimeError("Content write could not be verified.")
                operation.status = "pending"
                self.journal.save(operation)
            self._finish(operation, retry=False)
            return operation
        except (Exception, KeyboardInterrupt) as exc:
            return self._recover_or_raise(operation, exc)

    def tag_change(
        self, section: DiarySection, specs: list[str], *, additive: bool = False
    ) -> Operation:
        if any(not spec or any(not part for part in spec.split("/")) for spec in specs):
            raise RuntimeError(
                "Tag names and hierarchical path segments must be nonempty."
            )
        document = DiaryDocument.parse(read_markdown(section.file_path))
        if document.unique_section(section.heading) is None:
            raise RuntimeError(f"No section found for {section.section_id}.")
        intent = self._snapshot(section.file_path.name, section.heading)
        intent.mode = "add" if additive else "replace"
        intent.specs = specs
        requested = set(resource_tags_for_specs(specs))
        intended = requested | set(intent.before.tags) if additive else requested
        intent.intended = TagState(
            intent.before.exists or bool(intended), sorted(intended)
        )
        operation = self._prepare("tag_add" if additive else "tag_replace", {}, intent)
        try:
            self._finish(operation, retry=False)
            return operation
        except (Exception, KeyboardInterrupt) as exc:
            return self._recover_or_raise(operation, exc)

    def _guard_content(self, operation: Operation) -> None:
        for intent in operation.files:
            current = fingerprint(self.root / intent.name)
            if current == intent.intended and intent.before != intent.intended:
                intent.state = "committed"
            if current != intent.intended:
                if current == intent.before and intent.state != "committed":
                    raise RecoveryConflict(
                        "Content change is not confirmed; inspect it. Recovery never writes content."
                    )
                raise RecoveryConflict("Content diverged from the recorded operation.")

    def delete_taxonomy(self, names: list[str]) -> Operation:
        """Record affected associations and hierarchy before taxonomy deletion."""
        graph = self.adapter.taxonomy_state()
        tags, files = [], {}
        for resource in self.adapter.resource_paths_for_tags(names):
            file_text, separator, heading = resource.rpartition("#")
            path = Path(file_text)
            if (
                not separator
                or path.parent.resolve() != self.root.resolve()
                or path.suffix != ".md"
            ):
                raise RuntimeError(
                    "Cannot safely record a non-diary resource; inspect its metadata before deleting the taxonomy."
                )
            DiaryDocument.parse(read_markdown(path)).unique_section(heading)
            intent = self._snapshot(path.name, heading)
            intent.mode = "taxonomy"
            intent.intended = TagState(
                intent.before.exists, sorted(set(intent.before.tags) - set(names))
            )
            tags.append(intent)
            current = fingerprint(path)
            files[path.name] = FileIntent(path.name, current, current)
        operation = Operation(
            uuid4().hex,
            "delete_taxonomy",
            list(files.values()),
            tags,
            taxonomy_delete=list(names),
            taxonomy_before=graph,
            taxonomy_checkpoint=graph,
        )
        self.journal.create(operation)
        try:
            self._finish(operation, retry=False)
            return operation
        except (Exception, KeyboardInterrupt) as exc:
            return self._recover_or_raise(operation, exc)

    @staticmethod
    def _taxonomy_view(graph: dict[str, list[str]], names: list[str]) -> dict:
        """Ignore unrelated taxonomy changes, but include new incoming edges."""
        return {
            "nodes": {name: graph.get(name) for name in names},
            "incoming": sorted(
                (child, parent)
                for child, parents in graph.items()
                for parent in parents
                if parent in names
            ),
        }

    def _finish_taxonomy(self, operation: Operation) -> None:
        names = operation.taxonomy_delete
        graph = self.adapter.taxonomy_state()
        allowed = [
            operation.taxonomy_before,
            operation.taxonomy_checkpoint,
            operation.taxonomy_in_flight,
        ]
        if not any(
            self._taxonomy_view(graph, names) == self._taxonomy_view(state, names)
            for state in allowed
            if state is not None
        ):
            raise RecoveryConflict("Taxonomy diverged from the recorded operation.")
        known = {
            self.adapter.resource_path_for_section(self._section(t))
            for t in operation.tags
        }
        if set(self.adapter.resource_paths_for_tags(names)) - known:
            raise RecoveryConflict(
                "New resources use the targeted taxonomy; inspect before retrying."
            )
        for name in names:
            if name not in graph:
                continue
            intended = {
                tag: [p for p in parents if p != name]
                for tag, parents in graph.items()
                if tag != name
            }
            operation.taxonomy_in_flight = intended
            operation.metadata_started = True
            for intent in operation.tags:
                state = self._observe(intent)
                intent.in_flight = [
                    TagState(state.exists, sorted(set(state.tags) - {name}))
                ]
            self.journal.save(operation)
            if not self.adapter.delete_tag(name):
                raise RuntimeError(f"HTFS could not delete taxonomy tag {name}.")
            graph = self.adapter.taxonomy_state()
            if self._taxonomy_view(graph, names) != self._taxonomy_view(
                intended, names
            ):
                raise RuntimeError("Taxonomy deletion readback did not match intent.")
            for intent in operation.tags:
                observed = self._observe(intent)
                if observed != intent.in_flight[0]:
                    raise RuntimeError(
                        "Taxonomy association readback did not match intent."
                    )
                intent.checkpoint = observed
                intent.in_flight = []
            operation.taxonomy_checkpoint = graph
            operation.taxonomy_in_flight = None
            self.journal.save(operation)

    def _step(
        self,
        operation: Operation,
        intent: TagIntent,
        action: Callable[[], None],
        expected: TagState,
        intermediate: list[TagState] | None = None,
    ) -> None:
        intent.in_flight = [expected, *(intermediate or [])]
        self.journal.save(operation)
        action()
        observed = self._observe(intent)
        if observed != expected:
            raise RuntimeError(
                f"Metadata readback did not match intended state for {intent.heading}."
            )
        intent.checkpoint = observed
        intent.in_flight = []
        self.journal.save(operation)

    def _finish(self, operation: Operation, *, retry: bool) -> None:
        self._guard_content(operation)
        # Validate the entire target set before any metadata mutation on retry.
        for intent in operation.tags:
            document = DiaryDocument.parse(read_markdown(self.root / intent.file))
            try:
                span = (
                    document.unique_section(intent.heading)
                    if retry or intent.mode != "preserve"
                    else None
                )
            except RuntimeError as exc:
                raise RecoveryConflict(str(exc)) from exc
            if intent.mode == "remove" and span is not None:
                raise RecoveryConflict(
                    "Deleted section reappeared; refusing metadata cleanup."
                )
            if intent.mode in {"replace", "add"} and span is None:
                raise RecoveryConflict(
                    "Target section is missing; refusing metadata changes."
                )
            current = self._observe(intent)
            if current not in [
                intent.before,
                intent.intended,
                intent.checkpoint,
                *intent.in_flight,
            ]:
                raise RecoveryConflict(
                    "Tag associations diverged from the recorded operation."
                )
        if operation.taxonomy_delete:
            self._finish_taxonomy(operation)
        for intent in operation.tags:
            current = self._observe(intent)
            if intent.mode in {"add", "replace"} and intent.specs:
                # A new hierarchical path can be required even when the resource
                # already has that leaf association through another parent.
                operation.metadata_started = True
                self.journal.save(operation)
                self.adapter.add_tags(intent.specs)
                if not set(intent.specs) <= set(self.adapter.get_all_tag_paths()):
                    raise RuntimeError(
                        "HTFS did not establish the requested hierarchical tag paths."
                    )
            if current == intent.intended:
                continue
            if intent.mode == "taxonomy":
                raise RuntimeError(
                    "Taxonomy changes did not reach the intended association state."
                )
            section = self._section(intent)
            if intent.mode == "preserve":
                raise RuntimeError(
                    "Unchanged metadata no longer matches the recorded state."
                )
            operation.metadata_started = True
            self.journal.save(operation)
            if intent.mode == "remove":
                self._step(
                    operation,
                    intent,
                    lambda: self.adapter.delete_section_resource(section),
                    intent.intended,
                )
                continue
            if intent.mode == "replace" and current.tags:
                cleared = TagState(current.exists, [])
                self._step(
                    operation,
                    intent,
                    lambda: self.adapter.clear_section_tags(section),
                    cleared,
                )
            if intent.intended.tags:

                def apply():
                    rejected = self.adapter.tag_section(section, intent.intended.tags)
                    if rejected:
                        raise RuntimeError("HTFS rejected tags: " + ", ".join(rejected))

                self._step(
                    operation,
                    intent,
                    apply,
                    intent.intended,
                    [TagState(True, [] if intent.mode == "replace" else current.tags)],
                )
        self._guard_content(operation)
        operation.status = "complete"
        operation.error = None
        operation.completed = dt.datetime.now(dt.timezone.utc).isoformat()
        self.journal.save(operation)

    def retry(self, identifier: str) -> Operation:
        operation = self.journal.load(identifier)
        if operation.status in {"complete", "resolved"}:
            return operation
        try:
            self._finish(operation, retry=True)
            return operation
        except (Exception, KeyboardInterrupt) as exc:
            return self._recover_or_raise(operation, exc)
