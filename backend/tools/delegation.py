from __future__ import annotations

import asyncio
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.agent.contracts import AgentRole, AgentTaskSpec
from backend.agent.orchestrator import AgentOrchestrator
from backend.sandbox.policy import PolicyEngine
from backend.storage.repository import Repository
from backend.tools.contracts import Tool, ToolContext, ToolError, ToolInput, ToolResult
from backend.tools.registry import ToolRegistry
from backend.agent.learning import LearningProposalStore


class DelegatedTaskInput(BaseModel):
    goal: str = Field(min_length=1, max_length=20_000)
    context: dict[str, Any] = Field(default_factory=dict)
    role: AgentRole = "worker"
    provider_profile_id: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, max_length=200)
    allowed_tools: list[str] | None = Field(default=None, max_length=128)
    output_schema: dict[str, Any] | None = None
    group: str | None = Field(default=None, max_length=100)


class DelegateInput(ToolInput):
    task: DelegatedTaskInput | None = None
    tasks: list[DelegatedTaskInput] | None = Field(default=None, max_length=32)
    background: bool = False


class DelegateTool(Tool):
    name = "agent.delegate"
    title = "Delegate to subagents"
    description = (
        "Delegate one focused task or a parallel batch to isolated subagents. Each child receives only "
        "the supplied goal/context, has bounded tools and budget, and returns an evidence-preserving result."
    )
    input_model = DelegateInput
    # Delegation itself does not mutate the workspace; every child tool call is
    # independently policy-checked and mutating tools retain their snapshots.
    read_only = True
    timeout_seconds = 7_200

    def __init__(self, orchestrator: AgentOrchestrator) -> None:
        self.orchestrator = orchestrator

    async def execute(self, context: ToolContext, arguments: DelegateInput) -> ToolResult:
        values = arguments.tasks or ([arguments.task] if arguments.task else [])
        if not values or any(item is None for item in values):
            raise ToolError("invalid_delegation", "Provide task or tasks")
        specs = [AgentTaskSpec(**item.model_dump()) for item in values if item is not None]
        try:
            result = await self.orchestrator.delegate(
                session_id=context.session_id, root_turn_id=context.turn_id,
                parent_task_id=context.agent_task_id, specs=specs,
                background=arguments.background)
            return ToolResult(result)
        except ValueError as exc:
            raise ToolError("delegation_rejected", str(exc)) from exc


class AgentControlInput(ToolInput):
    action: Literal["list", "steer", "stop"]
    task_id: str | None = Field(default=None, max_length=64)
    message: str | None = Field(default=None, max_length=8_000)
    subtree: bool = False


class AgentControlTool(Tool):
    name = "agent.control"
    title = "Inspect or guide subagents"
    description = "List this turn's subagents, steer one active task, or explicitly stop one task or its subtree."
    input_model = AgentControlInput
    read_only = False
    internal_state_only = True

    def __init__(self, orchestrator: AgentOrchestrator) -> None:
        self.orchestrator = orchestrator

    async def execute(self, context: ToolContext, arguments: AgentControlInput) -> ToolResult:
        if arguments.action == "list":
            tasks = (self.orchestrator.store.list_descendants(context.agent_task_id)
                     if context.agent_task_id else
                     self.orchestrator.store.active_for_session(context.session_id))
            return ToolResult({"tasks": tasks})
        if not arguments.task_id:
            raise ToolError("agent_task_required", "task_id is required")
        try:
            task = self.orchestrator.store.get(arguments.task_id)
            if task["session_id"] != context.session_id:
                raise ToolError("agent_task_scope", "The task is outside this session")
            if context.agent_task_id:
                descendants = {item["id"] for item in self.orchestrator.store.list_descendants(context.agent_task_id)}
                if task["id"] not in descendants:
                    raise ToolError("agent_task_scope", "The task is outside this agent's descendants")
            result = await self.orchestrator.command(arguments.task_id, arguments.action, {
                "message": arguments.message, "subtree": arguments.subtree})
            return ToolResult(result)
        except KeyError as exc:
            raise ToolError("agent_task_not_found", "Agent task was not found") from exc
        except ValueError as exc:
            raise ToolError("agent_control_rejected", str(exc)) from exc


class BatchOperation(BaseModel):
    tool: str = Field(min_length=1, max_length=200)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ExecuteBatchInput(ToolInput):
    operations: list[BatchOperation] = Field(min_length=1, max_length=256)
    concurrency: int = Field(default=4, ge=1, le=32)
    stop_on_error: bool = True


class ExecuteBatchTool(Tool):
    name = "agent.execute_batch"
    title = "Execute a bounded tool batch"
    description = (
        "Run many explicit registered tool operations with bounded concurrency. Use for mechanical loops; "
        "it cannot invoke delegation or itself, and every nested operation is checked against session policy."
    )
    input_model = ExecuteBatchInput
    read_only = False
    timeout_seconds = 7_200

    def __init__(self, registry: ToolRegistry, repository: Repository, policy: PolicyEngine) -> None:
        self.registry = registry
        self.repository = repository
        self.policy = policy

    async def execute(self, context: ToolContext, arguments: ExecuteBatchInput) -> ToolResult:
        session = self.repository.get_session(context.session_id, include_history=False)
        semaphore = asyncio.Semaphore(arguments.concurrency)
        results: list[dict[str, Any] | None] = [None] * len(arguments.operations)
        changed: list[str] = []
        stop = asyncio.Event()

        async def run(index: int, operation: BatchOperation) -> None:
            if stop.is_set():
                results[index] = {"ok": False, "skipped": True}
                return
            if operation.tool in {self.name, "agent.delegate", "agent.control"}:
                results[index] = {"ok": False, "error": "Recursive batch/delegation is not allowed"}
                if arguments.stop_on_error:
                    stop.set()
                return
            async with semaphore:
                try:
                    tool = self.registry.get(operation.tool)
                    decision = self.policy.evaluate(tool, operation.arguments,
                                                    profile=session["policy_profile"],
                                                    session_id=context.session_id)
                    if decision.action != "allow":
                        raise ToolError("policy_denied", decision.reason)
                    value = await self.registry.execute(operation.tool, operation.arguments, context)
                    changed.extend(value.changed_files)
                    results[index] = {"ok": True, "output": value.output,
                                      "changed_files": value.changed_files}
                except ToolError as exc:
                    results[index] = {"ok": False, "code": exc.code, "error": str(exc)}
                    if arguments.stop_on_error:
                        stop.set()

        # Mutating calls remain sequential to avoid overlapping workspace snapshots.
        read_only = []
        mutating = []
        for index, operation in enumerate(arguments.operations):
            try:
                target = self.registry.get(operation.tool)
                (read_only if target.read_only else mutating).append((index, operation))
            except ToolError:
                mutating.append((index, operation))
        await asyncio.gather(*(run(index, operation) for index, operation in read_only))
        for index, operation in mutating:
            await run(index, operation)
        return ToolResult({"operations": results, "completed": sum(bool(item and item.get("ok")) for item in results),
                           "total": len(results)}, changed_files=sorted(set(changed)))


class LearningProposalInput(ToolInput):
    kind: Literal["memory", "skill"]
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=256_000)
    evidence: list[dict[str, Any]] = Field(default_factory=list, max_length=64)


class ProposeLearningTool(Tool):
    name = "agent.propose_learning"
    title = "Propose a memory or skill update"
    description = "Stage a learning proposal for explicit user review. It never changes active memory or skills."
    input_model = LearningProposalInput
    read_only = False

    def __init__(self, proposals: LearningProposalStore) -> None:
        self.proposals = proposals

    async def execute(self, context: ToolContext, arguments: LearningProposalInput) -> ToolResult:
        value = self.proposals.propose(session_id=context.session_id, task_id=context.agent_task_id,
                                       kind=arguments.kind, title=arguments.title,
                                       content=arguments.content, evidence=arguments.evidence)
        return ToolResult({"proposal": value, "activation": "requires explicit approval"})
