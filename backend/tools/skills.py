from __future__ import annotations

import shlex
from typing import Literal

from pydantic import Field

from backend.sandbox.runtime import DockerSandboxRuntime
from backend.skills.store import SkillStore
from backend.tools.contracts import Tool, ToolContext, ToolInput, ToolResult


class ReadSkillResourceInput(ToolInput):
    skill_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    path: str = Field(min_length=1, max_length=1_024)


class ReadSkillResourceTool(Tool):
    name = "skill.read_resource"
    title = "Read skill resource"
    description = "Read one text reference, template, asset description, or script from a skill activated for this turn."
    input_model = ReadSkillResourceInput

    def __init__(self, skills: SkillStore):
        self.skills = skills

    async def execute(self, context: ToolContext, arguments: ReadSkillResourceInput) -> ToolResult:
        return ToolResult(self.skills.read_resource(arguments.skill_id, arguments.path,
                                                     selected_ids=context.selected_skill_ids))


class RunSkillScriptInput(ToolInput):
    skill_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    path: str = Field(min_length=1, max_length=1_024)
    args: list[str] = Field(default_factory=list, max_length=32)
    cwd: str = Field(default=".", max_length=1_024)
    timeout_seconds: float = Field(default=30, ge=1, le=120)


class RunSkillScriptTool(Tool):
    name = "skill.run_script"
    title = "Run skill script"
    description = "Run an activated skill's .py, .js, or .sh script offline in Docker. The skill is mounted read-only; only this chat workspace can change. Always requires user approval."
    input_model = RunSkillScriptInput
    read_only = False
    timeout_seconds = 125

    def __init__(self, skills: SkillStore, sandbox: DockerSandboxRuntime):
        self.skills = skills
        self.sandbox = sandbox

    async def execute(self, context: ToolContext, arguments: RunSkillScriptInput) -> ToolResult:
        if any(len(item) > 256 or "\x00" in item for item in arguments.args):
            from backend.tools.contracts import ToolError
            raise ToolError("invalid_arguments", "Script arguments must be at most 256 characters each")
        skill, root, relative = self.skills.script_path(arguments.skill_id, arguments.path,
                                                         selected_ids=context.selected_skill_ids)
        extension = relative.rsplit(".", 1)[-1].lower()
        runner = {"py": "python", "js": "node", "sh": "/bin/sh"}[extension]
        command = shlex.join([runner, f"/skill/{relative}", *arguments.args])
        result = await self.sandbox.execute(
            session_id=context.session_id, turn_id=context.turn_id, command=command,
            cwd=arguments.cwd, timeout_seconds=arguments.timeout_seconds, network=False,
            on_output=context.on_output, readonly_mounts=[(root, "/skill")],
        )
        return ToolResult({"skill_id": skill["id"], "skill": skill["name"], "path": relative,
                           "command": command, "exit_code": result.exit_code, "stdout": result.stdout,
                           "stderr": result.stderr, "output_truncated": result.output_truncated},
                          changed_files=result.changed_files)
