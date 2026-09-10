from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any

from backend.agent.contracts import AGENT_PROFILES, AgentLimits, AgentTaskSpec
from backend.agent.executor import AgentExecutor
from backend.agent.heartbeat import AgentHeartbeatService
from backend.agent.task_store import AgentTaskStore
from backend.storage.repository import NotFoundError, Repository
from backend.tools.registry import ToolRegistry


class AgentOrchestrator:
    def __init__(self, store: AgentTaskStore, repository: Repository,
                 executor: AgentExecutor, tools: ToolRegistry,
                 heartbeats: AgentHeartbeatService | None = None) -> None:
        self.store = store
        self.repository = repository
        self.executor = executor
        self.tools = tools
        self.heartbeats = heartbeats
        self._running: dict[str, asyncio.Task] = {}
        self._semaphore: asyncio.Semaphore | None = None
        self._semaphore_size = 0
        self._monitor_task: asyncio.Task[None] | None = None
        self.executor.slot_provider = lambda: self._get_semaphore(self.limits().max_concurrent)

    def limits(self) -> AgentLimits:
        settings = self.store.settings()
        base = AGENT_PROFILES.get(settings["profile"], AGENT_PROFILES["balanced"])
        allowed = set(base.to_dict())
        overrides = {key: int(value) for key, value in settings["overrides"].items()
                     if key in allowed and isinstance(value, (int, float)) and int(value) > 0}
        values = base.to_dict()
        values.update(overrides)
        absolute = AGENT_PROFILES["maximum"]
        for key, cap in absolute.to_dict().items():
            values[key] = min(values[key], cap)
        return AgentLimits(**values)

    async def delegate(self, *, session_id: str, root_turn_id: str,
                       parent_task_id: str | None, specs: list[AgentTaskSpec],
                       background: bool = False) -> dict[str, Any]:
        settings = self.store.settings()
        if not settings["enabled"]:
            raise ValueError("Agent orchestration is disabled")
        limits = self.limits()
        if not specs or len(specs) > limits.max_children:
            raise ValueError(f"A delegation must contain 1-{limits.max_children} tasks")
        parent = self.store.get(parent_task_id) if parent_task_id else None
        depth = (parent["depth"] + 1) if parent else 1
        if depth > limits.max_depth:
            raise ValueError("Agent delegation depth limit reached")
        if self.store.count_tree(root_turn_id) + len(specs) > limits.max_tasks_per_tree:
            raise ValueError("Agent task-tree budget reached")
        session = self.repository.get_session(session_id, include_history=False)
        parent_allowlist = set(parent["allowed_tools"]) if parent else set(self.tools.tools)
        prepared: list[tuple[AgentTaskSpec, list[str], str | None, str]] = []
        for spec in specs:
            requested = set(spec.allowed_tools) if spec.allowed_tools is not None else parent_allowlist
            allowed = sorted(requested & parent_allowlist & set(self.tools.tools))
            provider_profile_id, model = self._resolve_route(spec, session)
            prepared.append((spec, allowed, provider_profile_id, model))
        created = []
        for ordinal, (spec, allowed, provider_profile_id, model) in enumerate(prepared):
            created.append(self.store.create(
                session_id=session_id, root_turn_id=root_turn_id, parent_task_id=parent_task_id,
                ordinal=ordinal, depth=depth, spec=spec,
                provider_profile_id=provider_profile_id,
                model=model, permission_profile=session["policy_profile"],
                allowed_tools=allowed, limits=limits,
                execution_mode="background" if background else "foreground"))
            if background and self.heartbeats:
                self.heartbeats.ensure_watch(created[-1]["id"])
        async def run_one(item: dict[str, Any]):
            return await asyncio.wait_for(self.executor.run(item["id"]), timeout=item["deadline_seconds"])

        tasks = [asyncio.create_task(run_one(item), name=f"agent:{item['id']}") for item in created]
        for item, task in zip(created, tasks, strict=True):
            self._running[item["id"]] = task
            task.add_done_callback(lambda done, task_id=item["id"]: self._task_done(task_id, done))
        if background:
            return {"tasks": [], "task_ids": [item["id"] for item in created],
                    "background": True, "receipt_state": "running"}
        try:
            results = await asyncio.gather(*tasks)
        except (asyncio.CancelledError, TimeoutError):
            for item in created:
                await self.cancel(item["id"])
            raise
        return {"tasks": [result.to_dict() for result in results],
                "task_ids": [item["id"] for item in created]}

    def _resolve_route(self, spec: AgentTaskSpec, session: dict[str, Any]) -> tuple[str | None, str]:
        route = self.store.settings().get("role_routes", {}).get(spec.role, {})
        profile_id = spec.provider_profile_id or route.get("provider_profile_id") or session.get("provider_profile_id")
        model = spec.model or route.get("model") or session["model"]
        registry = getattr(self.executor.gateway, "registry", None)
        if profile_id and registry is not None:
            try:
                profile = registry.get(profile_id, include_health=True)
            except NotFoundError as exc:
                raise ValueError(f"Provider route for role {spec.role} was not found") from exc
            if not profile["enabled"]:
                raise ValueError(f"Provider route for role {spec.role} is disabled")
        return profile_id, model

    async def command(self, task_id: str, command_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.store.get(task_id)
        if command_type == "steer":
            message = str(payload.get("message") or "").strip()
            if not message or len(message) > 8_000:
                raise ValueError("Steering message must contain 1-8000 characters")
            return self.store.queue_command(task_id, "steer", {"message": message})
        if command_type == "stop":
            subtree = bool(payload.get("subtree", False))
            command = self.store.queue_command(task_id, "stop", {"subtree": subtree})
            # Stop is applied synchronously by the orchestrator. Record it before
            # terminalization rejects any commands still left in the mailbox.
            self.store.apply_command(command["id"])
            ids = await self.cancel(task_id, subtree=subtree)
            return self.store.get_command(command["id"]) | {"affected_task_ids": ids}
        raise ValueError("Unsupported agent command")

    async def cancel(self, task_id: str, *, subtree: bool = True) -> list[str]:
        self.store.get(task_id)
        ids = self.store.request_cancel(task_id, subtree=subtree)
        for item in ids:
            current = self.store.get(item)
            task = self._running.get(item)
            if task and not task.done():
                task.cancel()
            # An asyncio task cancelled before its coroutine starts never enters
            # AgentExecutor's cancellation handler. Persist that terminal state
            # here so queued work and background receipts cannot remain orphaned.
            if current["status"] == "queued":
                self.store.finish(item, status="cancelled", result={
                    "task_id": item,
                    "status": "cancelled",
                    "summary": "Cancelled before execution",
                    "artifacts": [],
                    "changed_files": [],
                    "evidence": [],
                    "usage": {"steps": 0, "tool_calls": 0,
                              "input_tokens": 0, "output_tokens": 0},
                    "schema_valid": None,
                    "schema_errors": None,
                })
        return ids

    async def cancel_root(self, root_turn_id: str) -> None:
        tree = self.store.list_tree(root_turn_id)
        roots = [item for item in tree if item["parent_task_id"] is None]
        for item in roots:
            await self.cancel(item["id"])

    async def cancel_session(self, session_id: str) -> list[str]:
        active = self.store.active_for_session(session_id)
        active_ids = {item["id"] for item in active}
        roots = [item for item in active if item["parent_task_id"] not in active_ids]
        affected: list[str] = []
        for item in roots:
            affected.extend(await self.cancel(item["id"], subtree=True))
        return list(dict.fromkeys(affected))

    async def shutdown(self) -> None:
        if self._monitor_task:
            self._monitor_task.cancel()
            await asyncio.gather(self._monitor_task, return_exceptions=True)
            self._monitor_task = None
        tasks = list(self._running.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def start_monitor(self) -> None:
        if not self._monitor_task or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self._monitor(), name="agent-activity-monitor")

    async def _monitor(self) -> None:
        while True:
            await asyncio.sleep(15)
            try:
                threshold = self.limits().stall_warning_seconds
                now = datetime.now(timezone.utc)
                for task in self.store.running():
                    raw = task.get("last_activity_at") or task.get("started_at")
                    if not raw:
                        continue
                    with suppress(ValueError):
                        last = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                        age = (now - last.astimezone(timezone.utc)).total_seconds()
                        if age >= threshold:
                            self.store.mark_stalled(task["id"])
                        elif task.get("stalled_at"):
                            self.store.clear_stalled(task["id"])
            except asyncio.CancelledError:
                raise
            except Exception:
                # A transient database/configuration error must not permanently
                # disable activity supervision for every subsequent task.
                continue

    def _task_done(self, task_id: str, task: asyncio.Task) -> None:
        self._running.pop(task_id, None)
        with suppress(asyncio.CancelledError, Exception):
            task.exception()

    def _get_semaphore(self, size: int) -> asyncio.Semaphore:
        if self._semaphore is None or self._semaphore_size != size:
            self._semaphore = asyncio.Semaphore(size)
            self._semaphore_size = size
        return self._semaphore
