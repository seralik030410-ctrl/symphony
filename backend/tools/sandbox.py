from __future__ import annotations

from pathlib import PurePosixPath

from pydantic import Field

from backend.sandbox.runtime import DockerSandboxRuntime
from backend.tools.contracts import Tool, ToolContext, ToolError, ToolInput, ToolResult
from backend.tools.workspace import WorkspaceManager


class ShellInput(ToolInput):
    command: str = Field(min_length=1, max_length=20_000)
    cwd: str = Field(default=".", max_length=500)
    timeout_seconds: float = Field(default=60, ge=1, le=120)
    network: bool = False


class ShellTool(Tool):
    name = "sandbox.shell"
    title = "Run in sandbox"
    description = (
        "Run a shell command inside the persistent Docker workspace for this chat. "
        "Use it for Python/Node tests and builds. Network is off unless explicitly requested and approved."
    )
    input_model = ShellInput
    read_only = False
    timeout_seconds = 130

    def __init__(self, runtime: DockerSandboxRuntime) -> None:
        self.runtime = runtime

    async def execute(self, context: ToolContext, arguments: ShellInput) -> ToolResult:
        result = await self.runtime.execute(
            session_id=context.session_id,
            turn_id=context.turn_id,
            command=arguments.command,
            cwd=arguments.cwd,
            timeout_seconds=arguments.timeout_seconds,
            network=arguments.network,
            on_output=context.on_output,
        )
        return ToolResult(
            {
                "command": arguments.command,
                "cwd": arguments.cwd,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "duration_ms": result.duration_ms,
                "output_truncated": result.output_truncated,
            },
            changed_files=result.changed_files,
        )


class PreviewInput(ToolInput):
    entry: str = Field(default="dist/index.html", min_length=1, max_length=500)


class PreviewTool(Tool):
    name = "sandbox.preview"
    title = "Open site preview"
    description = "Publish an HTML entry from this chat workspace through Symphony's read-only preview route."
    input_model = PreviewInput

    def __init__(self, workspaces: WorkspaceManager) -> None:
        self.workspaces = workspaces

    async def execute(self, context: ToolContext, arguments: PreviewInput) -> ToolResult:
        entry = PurePosixPath(arguments.entry.replace("\\", "/"))
        if entry.suffix.lower() not in {".html", ".htm"}:
            raise ToolError("invalid_preview", "Preview entry must be an HTML file")
        path = self.workspaces.resolve(context.session_id, arguments.entry, must_exist=True)
        if not path.is_file():
            raise ToolError("invalid_preview", "Preview entry must be a file")
        relative = self.workspaces.relative(context.session_id, path)
        return ToolResult(
            {
                "entry": relative,
                "path": relative,
                "preview_url": f"/api/sessions/{context.session_id}/preview/{relative}",
            }
        )
