from __future__ import annotations

import asyncio
from typing import Any

from pydantic import ValidationError

from backend.tools.contracts import Tool, ToolContext, ToolError, ToolResult
from backend.tools.files import ApplyPatchTool, ListFilesTool, ReadFileTool, SearchTool, WriteFileTool
from backend.tools.sandbox import PreviewTool, ShellTool
from backend.tools.workspace import WorkspaceManager
from backend.sandbox.runtime import DockerSandboxRuntime
from backend.tools.snapshots import SnapshotStore, ListSnapshotsTool, RestoreSnapshotTool
from backend.skills.store import SkillStore
from backend.tools.skills import ReadSkillResourceTool, RunSkillScriptTool


class ToolRegistry:
    def __init__(self, tools: list[Tool], *, default_timeout: float = 10.0, snapshots: SnapshotStore | None = None) -> None:
        self.tools = {tool.name: tool for tool in tools}
        self.default_timeout = default_timeout
        self.snapshots = snapshots

    @classmethod
    def stage_two(cls, workspaces: WorkspaceManager, *, default_timeout: float = 10.0) -> "ToolRegistry":
        return cls(
            [
                ListFilesTool(workspaces),
                ReadFileTool(workspaces),
                WriteFileTool(workspaces),
                ApplyPatchTool(workspaces),
                SearchTool(workspaces),
            ],
            default_timeout=default_timeout,
            snapshots=SnapshotStore(workspaces),
        )

    @classmethod
    def stage_three(
        cls,
        workspaces: WorkspaceManager,
        sandbox: DockerSandboxRuntime,
        *,
        default_timeout: float = 10.0,
    ) -> "ToolRegistry":
        registry = cls.stage_two(workspaces, default_timeout=default_timeout)
        return cls(
            [*registry.tools.values(), ShellTool(sandbox), PreviewTool(workspaces),
             ListSnapshotsTool(registry.snapshots), RestoreSnapshotTool(registry.snapshots)],
            default_timeout=default_timeout,
            snapshots=registry.snapshots,
        )

    @classmethod
    def stage_four(
        cls, workspaces: WorkspaceManager, sandbox: DockerSandboxRuntime, skills: SkillStore,
        *, default_timeout: float = 10.0,
    ) -> "ToolRegistry":
        registry = cls.stage_three(workspaces, sandbox, default_timeout=default_timeout)
        return cls([*registry.tools.values(), ReadSkillResourceTool(skills), RunSkillScriptTool(skills, sandbox)],
                   default_timeout=default_timeout, snapshots=registry.snapshots)

    def definitions(self) -> list[dict[str, Any]]:
        return [tool.definition() for tool in self.tools.values()]

    def model_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": definition["name"],
                    "description": definition["description"],
                    "parameters": definition["input_schema"],
                },
            }
            for definition in self.definitions()
        ]

    def get(self, name: str) -> Tool:
        try:
            return self.tools[name]
        except KeyError as exc:
            raise ToolError("unknown_tool", f"Unknown tool: {name}") from exc

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        tool = self.get(name)
        try:
            validated = tool.input_model.model_validate(arguments)
        except ValidationError as exc:
            raise ToolError("invalid_arguments", str(exc)) from exc
        timeout = tool.timeout_seconds or self.default_timeout
        snapshot = None
        if not tool.read_only and self.snapshots:
            snapshot = self.snapshots.create(context.session_id, context.turn_id, name)
            if context.on_snapshot:
                await context.on_snapshot(snapshot)
        try:
            result = await asyncio.wait_for(tool.execute(context, validated), timeout=timeout)
            if snapshot:
                result.output["snapshot_id"] = snapshot["id"]
            return result
        except ToolError as exc:
            if snapshot:
                exc.details["snapshot_id"] = snapshot["id"]
            raise
        except TimeoutError as exc:
            raise ToolError("tool_timeout", f"Tool {name} exceeded its {timeout:g}s timeout") from exc
