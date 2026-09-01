"""Bounded, read-only project inspection for the workspace panel."""
from __future__ import annotations

import difflib
import hashlib
import json

from backend.tools.contracts import ToolError
from backend.tools.snapshots import SnapshotStore
from backend.tools.workspace import WorkspaceManager, walk_files


FILE_LIMIT = 256_000
DIFF_LIMIT = 500_000


def read_project_file(workspaces: WorkspaceManager, session_id: str, path: str) -> dict:
    candidate = workspaces.resolve(session_id, path, must_exist=True)
    if not candidate.is_file():
        raise ToolError("not_found", "Choose a project file")
    size = candidate.stat().st_size
    with candidate.open("rb") as stream:
        content = stream.read(FILE_LIMIT + 1)
    truncated = len(content) > FILE_LIMIT
    content = content[:FILE_LIMIT]
    try:
        text = content.decode("utf-8", errors="replace" if truncated else "strict")
        if b"\x00" in content:
            raise UnicodeError()
    except UnicodeError:
        return {"path": path, "size": size, "binary": True, "content": "", "truncated": False}
    return {"path": path, "size": size, "binary": False, "content": text, "truncated": truncated}


def project_changes(snapshots: SnapshotStore, session_id: str, snapshot_id: str | None) -> dict:
    items = snapshots.list(session_id)
    if not items:
        if snapshot_id:
            raise ToolError("not_found", "Snapshot does not belong to this chat")
        return {"snapshot": None, "files": [], "truncated": False}
    if snapshot_id:
        selected = next((item for item in items if item["id"] == snapshot_id), None)
        if not selected:
            raise ToolError("not_found", "Snapshot does not belong to this chat")
    else:
        # Whole latest turn, not just its last write/build operation.
        selected = [item for item in items if item["turn_id"] == items[0]["turn_id"]][-1]
    storage = snapshots._root(session_id)
    manifest = json.loads((storage / f"{selected['id']}.json").read_text(encoding="utf-8"))
    root = snapshots.workspaces.session_root(session_id)
    current = {}
    truncated = False
    for path in walk_files(root, excluded=snapshots.EXCLUDED):
        if len(current) >= snapshots.MAX_FILES:
            truncated = True
            break
        current[path.relative_to(root).as_posix()] = path
    files = []
    output_bytes = 0
    for relative in sorted(current.keys() | manifest["files"].keys()):
        if output_bytes >= DIFF_LIMIT or len(files) >= 200:
            truncated = True
            break
        path = current.get(relative)
        if path:
            path = snapshots.workspaces.resolve(session_id, relative, must_exist=True)
        digest = manifest["files"].get(relative)
        previous = storage / "blobs" / digest if digest else None
        if digest and (len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)):
            raise ToolError("invalid_snapshot", "Invalid snapshot hash")
        too_large = bool((path and path.stat().st_size > FILE_LIMIT) or (previous and previous.stat().st_size > FILE_LIMIT))
        if too_large:
            # Do not read arbitrarily large files just to render a UI comparison.
            files.append({"path": relative, "status": "uncompared", "diff": "", "additions": 0,
                          "deletions": 0, "binary": False, "truncated": True})
            continue
        before = previous.read_bytes() if previous else b""
        after = path.read_bytes() if path else b""
        if digest and hashlib.sha256(before).hexdigest() != digest:
            raise ToolError("invalid_snapshot", "Snapshot checksum failed")
        if path and digest and before == after:
            continue
        binary = b"\x00" in before or b"\x00" in after
        diff = ""
        additions = deletions = 0
        try:
            old, new = before.decode("utf-8"), after.decode("utf-8")
        except UnicodeError:
            binary = True
        if not binary:
            # Keep the final unterminated line visible as its own row.
            lines = list(difflib.unified_diff(old.splitlines(), new.splitlines(),
                         fromfile=f"a/{relative}" if digest else "/dev/null",
                         tofile=f"b/{relative}" if path else "/dev/null", lineterm=""))
            additions = sum(line.startswith("+") and not line.startswith("+++") for line in lines)
            deletions = sum(line.startswith("-") and not line.startswith("---") for line in lines)
            diff = "\n".join(lines)
        allowance = DIFF_LIMIT - output_bytes
        clipped = len(diff) > allowance
        diff = diff[:allowance]
        output_bytes += len(diff)
        files.append({"path": relative, "status": "added" if not digest else "deleted" if not path else "modified",
                      "diff": diff, "additions": additions, "deletions": deletions,
                      "binary": binary, "truncated": clipped})
        truncated = truncated or clipped
    return {"snapshot": selected, "files": files, "truncated": truncated}
