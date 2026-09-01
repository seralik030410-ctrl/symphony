from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from pydantic import Field

from backend.storage.database import utc_now
from backend.tools.contracts import Tool, ToolContext, ToolError, ToolInput, ToolResult
from backend.tools.workspace import WorkspaceManager, is_link, walk_files


class SnapshotStore:
    """Content-addressed source snapshots, outside the container's only mount.

    Dependency caches and VCS internals are intentionally not rollback targets.
    A budget violation fails closed before a mutating tool is run.
    """

    EXCLUDED = {"node_modules", ".venv", "venv", ".git", "__pycache__", ".pytest_cache", ".npm"}
    MAX_FILES = 5000
    MAX_BYTES = 50_000_000

    def __init__(self, workspaces: WorkspaceManager):
        self.workspaces = workspaces

    def _root(self, session_id: str) -> Path:
        root = self.workspaces.session_root(session_id).parent / "snapshots"
        if is_link(root):
            raise ToolError("invalid_snapshot", "Snapshot storage cannot be a link")
        root.mkdir(exist_ok=True)
        return root

    def create(self, session_id: str, turn_id: str, operation: str) -> dict:
        root = self.workspaces.session_root(session_id)
        storage = self._root(session_id)
        blobs = storage / "blobs"
        blobs.mkdir(exist_ok=True)
        manifest = {"id": uuid.uuid4().hex, "created_at": utc_now(), "turn_id": turn_id,
                    "operation": operation, "excluded_directories": sorted(self.EXCLUDED), "files": {}}
        total = 0
        for path in walk_files(root, excluded=self.EXCLUDED):
            total += path.stat().st_size
            if total > self.MAX_BYTES or len(manifest["files"]) >= self.MAX_FILES:
                raise ToolError("snapshot_limit", "Source snapshot exceeds 50 MB or 5000 files; operation was not run")
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            blob = blobs / digest
            if not blob.exists():
                blob.write_bytes(content)
            manifest["files"][path.relative_to(root).as_posix()] = digest
        manifest["bytes"] = total
        target = storage / f"{manifest['id']}.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        temporary.replace(target)
        return {key: value for key, value in manifest.items() if key != "files"} | {"file_count": len(manifest["files"])}

    def list(self, session_id: str) -> list[dict]:
        items = []
        for path in self._root(session_id).glob("*.json"):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["file_count"] = len(manifest.pop("files"))
            items.append(manifest)
        return sorted(items, key=lambda item: item["created_at"], reverse=True)

    def restore(self, session_id: str, snapshot_id: str) -> list[str]:
        if len(snapshot_id) != 32 or any(c not in "0123456789abcdef" for c in snapshot_id):
            raise ToolError("invalid_snapshot", "Invalid snapshot id")
        storage = self._root(session_id)
        path = storage / f"{snapshot_id}.json"
        if not path.is_file():
            raise ToolError("snapshot_not_found", "Snapshot does not belong to this chat")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        root = self.workspaces.session_root(session_id)
        contents = {}
        # Validate all targets and hashes before changing any file.
        for relative, digest in manifest["files"].items():
            target = self.workspaces.resolve(session_id, relative)
            if any(part in self.EXCLUDED for part in Path(relative).parts) or target.is_dir():
                raise ToolError("snapshot_conflict", f"Cannot restore {relative}")
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ToolError("invalid_snapshot", "Invalid blob hash")
            content = (storage / "blobs" / digest).read_bytes()
            if hashlib.sha256(content).hexdigest() != digest:
                raise ToolError("invalid_snapshot", "Snapshot blob failed checksum verification")
            contents[relative] = (target, content)
        current = {p.relative_to(root).as_posix(): p for p in walk_files(root, excluded=self.EXCLUDED)}
        changed = []
        for relative, (target, content) in contents.items():
            if target.exists() and target.read_bytes() == content:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.parent / f".restore-{uuid.uuid4().hex}.tmp"
            temporary.write_bytes(content)
            temporary.replace(target)
            changed.append(relative)
        # The registry saves a safety snapshot immediately before restore, including
        # newly-created files. Removing these files is therefore recoverable.
        for relative in current.keys() - contents.keys():
            current[relative].unlink()
            changed.append(relative)
        return sorted(changed)


class ListSnapshotsInput(ToolInput):
    pass


class ListSnapshotsTool(Tool):
    name = "project.snapshots"
    title = "List project snapshots"
    description = "List recoverable source snapshots belonging only to this chat, newest first."
    input_model = ListSnapshotsInput

    def __init__(self, snapshots: SnapshotStore):
        self.snapshots = snapshots

    async def execute(self, context: ToolContext, arguments: ListSnapshotsInput) -> ToolResult:
        return ToolResult({"snapshots": self.snapshots.list(context.session_id)[:50]})


class RestoreInput(ToolInput):
    snapshot_id: str = Field(pattern=r"^[0-9a-f]{32}$")


class RestoreSnapshotTool(Tool):
    name = "project.restore"
    title = "Restore project snapshot"
    description = "Restore source files to a snapshot from this chat. Requires approval; a safety snapshot is saved first. Dependency caches are excluded."
    input_model = RestoreInput
    read_only = False
    destructive = True

    def __init__(self, snapshots: SnapshotStore):
        self.snapshots = snapshots

    async def execute(self, context: ToolContext, arguments: RestoreInput) -> ToolResult:
        changed = self.snapshots.restore(context.session_id, arguments.snapshot_id)
        return ToolResult({"restored_snapshot_id": arguments.snapshot_id}, changed_files=changed)
