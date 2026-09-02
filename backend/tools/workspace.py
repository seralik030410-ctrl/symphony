from __future__ import annotations

import os
import shutil
from pathlib import Path

from backend.tools.contracts import ToolError


def is_link(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def walk_files(root: Path, *, excluded: set[str] | None = None):
    """Never follow links/reparse points created by untrusted project commands."""
    excluded = excluded or set()
    for current, directories, files in os.walk(root, followlinks=False):
        directories[:] = sorted(name for name in directories if name not in excluded and not is_link(Path(current) / name))
        for name in sorted(files):
            path = Path(current) / name
            if not is_link(path) and path.is_file():
                yield path


class WorkspaceManager:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def session_root(self, session_id: str) -> Path:
        if not session_id or any(character not in "0123456789abcdef" for character in session_id.lower()):
            raise ToolError("invalid_session", "Session id is invalid")
        session_path = self.root / session_id
        if is_link(session_path) or is_link(session_path / "worktree"):
            raise ToolError("workspace_escape", "Workspace directories cannot be links")
        root = (session_path / "worktree").resolve()
        if self.root not in root.parents:
            raise ToolError("workspace_escape", "Session workspace escaped the configured root")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def resolve(self, session_id: str, relative_path: str, *, must_exist: bool = False) -> Path:
        raw = relative_path.strip() or "."
        if "\x00" in raw:
            raise ToolError("invalid_path", "Path contains a null byte")
        if ":" in raw:
            raise ToolError("invalid_path", "Drive-qualified paths and Windows ADS are not allowed")
        relative = Path(raw.replace("\\", "/"))
        if relative.is_absolute() or any(part == ".." for part in relative.parts):
            raise ToolError("path_traversal", "Path must stay inside the current chat workspace")
        root = self.session_root(session_id)
        current = root
        for part in relative.parts:
            current = current / part
            if is_link(current):
                raise ToolError("symlink_escape", "Workspace paths cannot contain links")
        candidate = (root / relative).resolve(strict=False)
        if candidate != root and root not in candidate.parents:
            raise ToolError("workspace_escape", "Resolved path leaves the current chat workspace")
        if must_exist and not candidate.exists():
            raise ToolError("not_found", f"Path does not exist: {relative_path}")
        if candidate.exists() and candidate.is_symlink():
            resolved = candidate.resolve()
            if resolved != root and root not in resolved.parents:
                raise ToolError("symlink_escape", "Symlink target leaves the current chat workspace")
        return candidate

    def relative(self, session_id: str, path: Path) -> str:
        return path.resolve().relative_to(self.session_root(session_id)).as_posix()

    def tree(self, session_id: str, *, max_entries: int = 500) -> list[dict[str, object]]:
        root = self.session_root(session_id)
        entries: list[dict[str, object]] = []
        for current_root, directories, files in os.walk(root, followlinks=False):
            directories[:] = sorted(
                name for name in directories if not is_link(Path(current_root) / name)
            )
            for name in [*directories, *sorted(files)]:
                path = Path(current_root) / name
                if is_link(path):
                    continue
                entries.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "type": "directory" if path.is_dir() else "file",
                        "size": path.stat().st_size if path.is_file() else None,
                    }
                )
                if len(entries) >= max_entries:
                    return entries
        return entries

    def purge_session(self, session_id: str) -> None:
        """Remove the complete on-disk session directory without following links."""
        if not session_id or any(character not in "0123456789abcdef" for character in session_id.lower()):
            raise ToolError("invalid_session", "Session id is invalid")
        session_path = self.root / session_id
        if not session_path.exists():
            return
        if is_link(session_path):
            raise ToolError("workspace_escape", "Session directory cannot be a link")
        resolved = session_path.resolve()
        if resolved.parent != self.root:
            raise ToolError("workspace_escape", "Session directory escaped the configured root")
        shutil.rmtree(resolved)
