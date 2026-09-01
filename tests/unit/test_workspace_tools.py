from __future__ import annotations

import pytest
import asyncio

from backend.tools.contracts import Tool, ToolContext, ToolError, ToolInput, ToolResult
from backend.tools.registry import ToolRegistry
from backend.tools.workspace import WorkspaceManager


async def test_file_tools_create_patch_read_search_and_list(tmp_path):
    manager = WorkspaceManager(tmp_path / "workspaces")
    registry = ToolRegistry.stage_two(manager)
    context = ToolContext(session_id="a" * 32, turn_id="b" * 32)

    created = await registry.execute(
        "fs.write",
        {"path": "notes/plan.md", "content": "alpha\nbeta\n"},
        context,
    )
    patched = await registry.execute(
        "fs.apply_patch",
        {"path": "notes/plan.md", "old_text": "beta", "new_text": "gamma"},
        context,
    )
    read = await registry.execute("fs.read", {"path": "notes/plan.md"}, context)
    search = await registry.execute(
        "search.rg",
        {"query": "gamma", "path": ".", "glob": "*.md"},
        context,
    )
    listing = await registry.execute("fs.list", {"path": "."}, context)

    assert created.changed_files == ["notes/plan.md"]
    assert "-beta" in (patched.diff or "") and "+gamma" in (patched.diff or "")
    assert read.output["content"] == "alpha\ngamma\n"
    assert search.output["matches"][0]["path"] == "notes/plan.md"
    assert any(item["path"] == "notes/plan.md" for item in listing.output["entries"])


async def test_workspace_blocks_traversal_and_isolates_sessions(tmp_path):
    manager = WorkspaceManager(tmp_path / "workspaces")
    registry = ToolRegistry.stage_two(manager)
    first = ToolContext(session_id="1" * 32, turn_id="a" * 32)
    second = ToolContext(session_id="2" * 32, turn_id="b" * 32)
    await registry.execute("fs.write", {"path": "private.txt", "content": "secret"}, first)

    with pytest.raises(ToolError, match="inside the current chat workspace"):
        await registry.execute("fs.read", {"path": "../private.txt"}, second)
    with pytest.raises(ToolError) as missing:
        await registry.execute("fs.read", {"path": "private.txt"}, second)
    assert missing.value.code == "not_found"
    assert manager.tree(second.session_id) == []


class SlowInput(ToolInput):
    pass


class SlowTool(Tool):
    name = "test.slow"
    title = "Slow test tool"
    description = "Waits long enough to exercise the timeout contract."
    input_model = SlowInput

    async def execute(self, context: ToolContext, arguments: SlowInput) -> ToolResult:
        await asyncio.sleep(0.2)
        return ToolResult({"ok": True})


async def test_registry_enforces_tool_timeout():
    registry = ToolRegistry([SlowTool()], default_timeout=0.01)
    with pytest.raises(ToolError) as timed_out:
        await registry.execute(
            "test.slow",
            {},
            ToolContext(session_id="a" * 32, turn_id="b" * 32),
        )
    assert timed_out.value.code == "tool_timeout"
