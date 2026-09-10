from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal


AgentStatus = Literal["queued", "running", "completed", "failed", "cancelled", "interrupted"]
AgentCommandType = Literal["steer", "stop"]
AgentExecutionMode = Literal["foreground", "background"]
AgentRole = Literal["worker", "orchestrator", "code", "research", "vision", "media", "review"]


@dataclass(frozen=True, slots=True)
class AgentLimits:
    max_concurrent: int
    max_depth: int
    max_children: int
    max_tasks_per_tree: int
    max_steps: int
    max_tool_calls: int
    max_input_tokens: int
    max_output_tokens: int
    deadline_seconds: int
    stall_warning_seconds: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


AGENT_PROFILES: dict[str, AgentLimits] = {
    "conservative": AgentLimits(1, 2, 4, 16, 16, 24, 500_000, 125_000, 1_800, 300),
    "balanced": AgentLimits(4, 4, 12, 64, 32, 64, 2_000_000, 500_000, 3_600, 600),
    "maximum": AgentLimits(32, 8, 32, 512, 64, 128, 8_000_000, 2_000_000, 7_200, 1_800),
}


@dataclass(slots=True)
class AgentTaskSpec:
    goal: str
    context: dict[str, Any]
    role: AgentRole = "worker"
    provider_profile_id: str | None = None
    model: str | None = None
    allowed_tools: list[str] | None = None
    output_schema: dict[str, Any] | None = None
    group: str | None = None


@dataclass(slots=True)
class AgentResult:
    task_id: str
    status: AgentStatus
    summary: str
    artifacts: list[dict[str, Any]]
    changed_files: list[str]
    evidence: list[dict[str, Any]]
    usage: dict[str, int]
    schema_valid: bool | None = None
    schema_errors: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
