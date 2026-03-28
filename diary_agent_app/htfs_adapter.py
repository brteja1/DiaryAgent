from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .models import DiarySection


class HTFSAdapter:
    """Small boundary-aware adapter between DiaryAgent sections and HTFS resources."""

    def __init__(self, boundary: Path) -> None:
        self.boundary = boundary.resolve()

    @property
    def sqlite_path(self) -> Path:
        return self.boundary / ".tagfs.db"

    @property
    def rdf_path(self) -> Path:
        return self.boundary / ".tagfs.ttl"

    def is_initialized(self) -> bool:
        return self.sqlite_path.exists()

    def ensure_initialized(self) -> None:
        if self.is_initialized():
            return
        utilities = self._utilities()
        try:
            utilities.initialize()
            utilities.add_tags(["People", "Place", "Topic", "Project", "Area"])
        finally:
            utilities.close()

    def resource_path_for_section(self, section: DiarySection) -> str:
        return f"{section.file_path.resolve()}#{section.heading}"

    def section_id_from_resource_path(self, resource_path: str) -> str | None:
        path_text = str(Path(resource_path.split("#", 1)[0]).resolve())
        file_name = Path(path_text).name
        if "#" not in resource_path:
            return None
        _, heading = resource_path.rsplit("#", 1)
        if not heading:
            return None
        return f"{file_name}#{heading}"

    def load_section_by_resource_path(self, agent, resource_path: str) -> DiarySection | None:
        section_id = self.section_id_from_resource_path(resource_path)
        if section_id is None:
            return None
        return agent.section_for_id(section_id)

    def _utilities(self):
        try:
            import sys

            sys.path.insert(0, "/linuxdev/github/HTFS")
            import TagfsUtilities  # type: ignore
        except ImportError as exc:  # pragma: no cover - environment boundary
            raise RuntimeError("HTFS is not importable from /linuxdev/github/HTFS") from exc
        return TagfsUtilities.TagfsTagHandlerUtilities(str(self.boundary))

    def add_tags(self, tags: Iterable[str]) -> list[str]:
        utilities = self._utilities()
        try:
            return utilities.add_tags(list(tags))
        finally:
            utilities.close()

    def list_tags(self) -> list[str]:
        utilities = self._utilities()
        try:
            return list(utilities.get_tags_list([]))
        finally:
            utilities.close()

    def link_tags(self, tag: str, parent_tag: str) -> bool:
        utilities = self._utilities()
        try:
            return bool(utilities.link_tags(tag, parent_tag))
        finally:
            utilities.close()

    def tag_section(self, section: DiarySection, tags: Iterable[str]) -> list[str]:
        utilities = self._utilities()
        try:
            resource_path = self.resource_path_for_section(section)
            utilities.add_resource(resource_path)
            return utilities.tag_resource(resource_path, list(tags))
        finally:
            utilities.close()

    def section_tags(self, section: DiarySection) -> list[str]:
        utilities = self._utilities()
        try:
            return list(utilities.get_resource_tags(self.resource_path_for_section(section)))
        finally:
            utilities.close()

    def query_resource_paths(self, tag_expression: str) -> list[str]:
        utilities = self._utilities()
        try:
            return list(utilities.get_resources_by_tag_expr(tag_expression))
        finally:
            utilities.close()
