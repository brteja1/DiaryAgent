from __future__ import annotations

import importlib
from contextlib import contextmanager
import sys
from pathlib import Path
from typing import Iterable

from . import core
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
        with self._session() as client:
            client.initialize()
            client.add_tags(["People", "Place", "Topic", "Project", "Area"])

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

    def load_section_by_resource_path(
        self, agent, resource_path: str
    ) -> DiarySection | None:
        section_id = self.section_id_from_resource_path(resource_path)
        if section_id is None:
            return None
        return agent.section_for_id(section_id)

    @staticmethod
    def require_backend():
        """Load only the bundled backend, without touching the diary boundary."""
        backend_path = core.default_htfs_path().resolve()
        package_path = backend_path / "htfs"
        if not (package_path / "__init__.py").is_file():
            raise RuntimeError(
                f"Required HTFS submodule is missing at {backend_path}. "
                "Run 'git submodule update --init --recursive' from the Diary Agent repository."
            )

        def require_bundled(module):
            source = getattr(module, "__file__", None)
            if source is None or not Path(source).resolve().is_relative_to(
                package_path
            ):
                raise RuntimeError(
                    "A different HTFS package is already loaded. Restart using the Diary Agent "
                    f"environment with the bundled backend at {backend_path}."
                )

        existing = sys.modules.get("htfs")
        if existing is not None:
            require_bundled(existing)
        backend_path_text = str(backend_path)
        if not sys.path or sys.path[0] != backend_path_text:
            sys.path.insert(0, backend_path_text)
        try:
            package = importlib.import_module("htfs")
            module = importlib.import_module("htfs.core")
        except ImportError as exc:  # pragma: no cover - environment boundary
            raise RuntimeError(
                f"Required bundled HTFS cannot be imported: {exc}. "
                "Initialize submodules, then run 'python -m pip install -r requirements.txt'."
            ) from exc
        require_bundled(package)
        require_bundled(module)
        return module.HTFS

    def _client(self):
        return self.require_backend()(str(self.boundary))

    @contextmanager
    def _session(self):
        """Every backend operation flushes/closes its client, including on errors."""
        client = self._client()
        try:
            yield client
        finally:
            client.close()

    def add_tags(self, tags: Iterable[str]) -> list[str]:
        with self._session() as client:
            return client.add_tags(list(tags))

    def list_tags(self) -> list[str]:
        with self._session() as client:
            return list(client.get_tags_list([]))

    def get_top_level_tags(self) -> list[str]:
        with self._session() as client:
            all_tags = list(client.get_tags_list([]))
            top_level = []
            for tag in all_tags:
                if not client.th.get_parent_tags(tag):
                    top_level.append(tag)
            return sorted(top_level)

    def get_child_tags(self, tag_name: str) -> list[str]:
        with self._session() as client:
            return sorted(list(client.th.get_child_tags(tag_name)))

    def get_tag_descendants(self, tag_name: str) -> list[str]:
        with self._session() as client:
            seen: set[str] = set()
            descendants: list[str] = []

            def walk(current_tag: str) -> None:
                for child_tag in client.th.get_child_tags(current_tag):
                    if child_tag in seen:
                        continue
                    seen.add(child_tag)
                    walk(child_tag)
                    descendants.append(child_tag)

            walk(tag_name)
            return descendants

    def tag_has_usage(self, tag_name: str) -> bool:
        with self._session() as client:
            return bool(client.get_resources_by_tag([tag_name]))

    def delete_tag(self, tag_name: str) -> bool:
        with self._session() as client:
            return bool(client.del_tag(tag_name))

    def taxonomy_state(self) -> dict[str, list[str]]:
        with self._session() as client:
            return {
                tag: sorted(client.th.get_parent_tags(tag))
                for tag in client.get_tags_list([])
            }

    def resource_paths_for_tags(self, tags: Iterable[str]) -> list[str]:
        with self._session() as client:
            existing = set(client.get_tags_list([]))
            return sorted(
                {
                    path
                    for tag in tags
                    if tag in existing
                    for path in client.get_resources_by_tag([tag])
                }
            )

    def get_all_tag_paths(self) -> list[str]:
        """Get all possible hierarchical tag paths."""
        with self._session() as client:
            all_tags = list(client.get_tags_list([]))
            paths = []

            def build_paths(current_tag, current_path):
                full_path = "/".join(current_path + [current_tag])
                paths.append(full_path)
                children = client.th.get_child_tags(current_tag)
                for child in children:
                    build_paths(child, current_path + [current_tag])

            top_level = [tag for tag in all_tags if not client.th.get_parent_tags(tag)]
            for tag in top_level:
                build_paths(tag, [])
            return sorted(paths)

    def tag_section(self, section: DiarySection, tags: Iterable[str]) -> list[str]:
        with self._session() as client:
            resource_path = self.resource_path_for_section(section)
            client.add_resource(resource_path)
            return client.tag_resource(resource_path, list(tags))

    def section_tags(self, section: DiarySection) -> list[str]:
        with self._session() as client:
            return list(
                client.get_resource_tags(self.resource_path_for_section(section))
            )

    def section_resource_exists(self, section: DiarySection) -> bool:
        with self._session() as client:
            return bool(
                client.is_resource_tracked(self.resource_path_for_section(section))
            )

    def clear_section_tags(self, section: DiarySection) -> None:
        with self._session() as client:
            resource_path = self.resource_path_for_section(section)
            current_tags = client.get_resource_tags(resource_path)
            if current_tags:
                client.untag_resource(resource_path, list(current_tags))

    def delete_section_resource(self, section: DiarySection) -> None:
        with self._session() as client:
            resource_path = self.resource_path_for_section(section)
            current_tags = client.get_resource_tags(resource_path)
            if current_tags:
                client.untag_resource(resource_path, list(current_tags))

            client.del_resource(resource_path)

    def query_resource_paths(self, tag_expression: str) -> list[str]:
        with self._session() as client:
            return list(client.get_resources_by_tag_expr(tag_expression))
