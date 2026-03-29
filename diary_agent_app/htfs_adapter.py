from __future__ import annotations

import sys
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
        client = self._client()
        try:
            client.initialize()
            client.add_tags(["People", "Place", "Topic", "Project", "Area"])
        finally:
            client.close()

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

    def _client(self):
        try:
            if "/linuxdev/github/HTFS" not in sys.path:
                sys.path.insert(0, "/linuxdev/github/HTFS")
            from htfs import HTFS  # type: ignore
        except ImportError as exc:  # pragma: no cover - environment boundary
            raise RuntimeError("HTFS is not importable from /linuxdev/github/HTFS") from exc
        return HTFS(str(self.boundary))

    def add_tags(self, tags: Iterable[str]) -> list[str]:
        client = self._client()
        try:
            return client.add_tags(list(tags))
        finally:
            client.close()

    def list_tags(self) -> list[str]:
        client = self._client()
        try:
            return list(client.get_tags_list([]))
        finally:
            client.close()

    def link_tags(self, tag: str, parent_tag: str) -> bool:
        client = self._client()
        try:
            return bool(client.link_tags(tag, parent_tag))
        finally:
            client.close()

    def tag_section(self, section: DiarySection, tags: Iterable[str]) -> list[str]:
        client = self._client()
        try:
            resource_path = self.resource_path_for_section(section)
            client.add_resource(resource_path)
            return client.tag_resource(resource_path, list(tags))
        finally:
            client.close()

    def section_tags(self, section: DiarySection) -> list[str]:
        client = self._client()
        try:
            return list(client.get_resource_tags(self.resource_path_for_section(section)))
        finally:
            client.close()

    def query_resource_paths(self, tag_expression: str) -> list[str]:
        client = self._client()
        try:
            return list(client.get_resources_by_tag_expr(tag_expression))
        finally:
            client.close()
