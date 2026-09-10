from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from backend.agent.contracts import AGENT_PROFILES


router = APIRouter(prefix="/api/agents", tags=["agents"])


def _runtime(request: Request):
    return request.app.state.runtime


class AgentRoleRoute(BaseModel):
    provider_profile_id: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=200)

    @field_validator("provider_profile_id", "model")
    @classmethod
    def nonempty_value(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Role route values cannot be empty")
        return value


class AgentSettingsUpdate(BaseModel):
    enabled: bool = True
    profile: Literal["conservative", "balanced", "maximum", "custom"] = "balanced"
    overrides: dict[str, int] = Field(default_factory=dict)
    lazy_tools_enabled: bool = True
    role_routes: dict[Literal["worker", "orchestrator", "code", "research", "vision", "media", "review"], AgentRoleRoute] = Field(default_factory=dict)


class LearningDecision(BaseModel):
    approved: bool


class AgentCommandInput(BaseModel):
    type: Literal["steer", "stop"]
    message: str | None = Field(default=None, max_length=8_000)
    subtree: bool = False


@router.get("/settings")
async def get_settings(request: Request) -> dict[str, Any]:
    runtime = _runtime(request)
    value = runtime.agent_tasks.settings()
    value["effective_limits"] = runtime.agents.limits().to_dict()
    value["profiles"] = {name: limits.to_dict() for name, limits in AGENT_PROFILES.items()}
    return value


@router.put("/settings")
async def update_settings(payload: AgentSettingsUpdate, request: Request) -> dict[str, Any]:
    runtime = _runtime(request)
    if payload.profile == "custom" and not payload.overrides:
        raise HTTPException(status_code=422, detail="Custom profile needs at least one override")
    routes = {role: route.model_dump() for role, route in payload.role_routes.items()}
    for role, route in routes.items():
        try:
            provider = runtime.providers.get(route["provider_profile_id"], include_health=True)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Provider route for {role} was not found") from exc
        if not provider["enabled"]:
            raise HTTPException(status_code=422, detail=f"Provider route for {role} is disabled")
    runtime.agent_tasks.save_settings(enabled=payload.enabled, profile=payload.profile,
                                      overrides=payload.overrides,
                                      lazy_tools_enabled=payload.lazy_tools_enabled,
                                      role_routes=routes)
    return await get_settings(request)


@router.get("/turns/{turn_id}/tree")
async def task_tree(turn_id: str, request: Request) -> list[dict[str, Any]]:
    runtime = _runtime(request)
    try:
        runtime.repository.get_turn(turn_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Turn not found") from exc
    return runtime.agent_tasks.list_tree(turn_id)


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, request: Request) -> dict[str, Any]:
    try:
        return _runtime(request).agent_tasks.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agent task not found") from exc


@router.get("/tasks/{task_id}/events")
async def get_task_events(task_id: str, request: Request,
                          after: int = Query(default=0, ge=0)) -> list[dict[str, Any]]:
    try:
        _runtime(request).agent_tasks.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agent task not found") from exc
    return _runtime(request).agent_tasks.events(task_id, after)


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, request: Request) -> dict[str, Any]:
    try:
        result = await _runtime(request).agents.command(task_id, "stop", {"subtree": True})
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agent task not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"cancelled_task_ids": result.get("affected_task_ids", [])}


@router.post("/tasks/{task_id}/commands")
async def submit_command(task_id: str, payload: AgentCommandInput, request: Request) -> dict[str, Any]:
    if payload.type == "steer" and not (payload.message or "").strip():
        raise HTTPException(status_code=422, detail="Steering message cannot be empty")
    try:
        return await _runtime(request).agents.command(task_id, payload.type, payload.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agent task not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/tasks/{task_id}/commands")
async def task_commands(task_id: str, request: Request,
                        after: int = Query(default=0, ge=0)) -> list[dict[str, Any]]:
    try:
        return _runtime(request).agent_tasks.commands(task_id, after)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agent task not found") from exc


@router.get("/sessions/{session_id}/background")
async def session_background(session_id: str, request: Request) -> dict[str, Any]:
    runtime = _runtime(request)
    try:
        runtime.repository.get_session(session_id, include_history=False)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    background = runtime.agent_tasks.background_for_session(session_id)
    heartbeat = runtime.agent_heartbeats.for_session(session_id)
    return background | {
        "watches": heartbeat["watches"],
        "heartbeat_events": heartbeat["events"],
    }


@router.post("/receipts/{receipt_id}/acknowledge")
async def acknowledge_receipt(receipt_id: str, request: Request) -> dict[str, Any]:
    try:
        return _runtime(request).agent_tasks.acknowledge_receipt(receipt_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agent completion receipt not found") from exc


@router.post("/heartbeat-events/{event_id}/acknowledge")
async def acknowledge_heartbeat_event(event_id: str, request: Request) -> dict[str, Any]:
    try:
        return _runtime(request).agent_heartbeats.acknowledge(event_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agent heartbeat event not found") from exc


@router.get("/learning")
async def learning_proposals(request: Request, session_id: str | None = None,
                             status: Literal["pending", "approved", "rejected"] | None = None) -> list[dict[str, Any]]:
    return _runtime(request).agent_learning.list(session_id=session_id, status=status)


@router.post("/learning/{proposal_id}/decision")
async def decide_learning(proposal_id: str, payload: LearningDecision, request: Request) -> dict[str, Any]:
    try:
        # Approval records consent. Applying content to MemoryStore/SkillStore is deliberately
        # a separate explicit operation so a proposal can be inspected or edited first.
        return _runtime(request).agent_learning.decide(proposal_id, payload.approved)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
