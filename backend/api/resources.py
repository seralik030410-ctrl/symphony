from __future__ import annotations

from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from backend.runtime.contracts import ResourceClaim, ResourceClass, ResourceError, ResourceProfile


router = APIRouter(prefix="/api/resources", tags=["resources"])


class ResourceClaimInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    group: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}:[a-z][a-z0-9_-]{0,63}$")
    units: int = Field(ge=1, le=100_000)


class ResourceSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: Literal["conservative", "balanced", "maximum", "custom"]
    custom_limits: dict[str, Any] = Field(default_factory=dict)


class ResourceGroupUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capacity_units: int = Field(ge=1, le=100_000)
    enabled: bool = True


class ResourceRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_type: str = Field(min_length=1, max_length=160)
    owner_id: str = Field(min_length=1, max_length=160)
    resource_class: ResourceClass
    claims: list[ResourceClaimInput] = Field(min_length=1, max_length=4)
    session_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResourceFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error_code: str = Field(min_length=1, max_length=80)
    error_message: str = Field(min_length=1, max_length=1_000)


def _coordinator(request: Request):
    coordinator = getattr(request.app.state.runtime, "resources", None)
    if coordinator is None:
        raise HTTPException(status_code=503, detail="Resource coordinator is not enabled in this runtime")
    return coordinator


def _result(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return value


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, ResourceError):
        code = 404 if exc.code.endswith("not_found") else 409 if exc.code in {"queue_full", "not_admitted", "not_running", "lease_not_active"} else 422
        return HTTPException(status_code=code, detail=str(exc))
    return HTTPException(status_code=400, detail="Resource coordinator request is invalid")


@router.get("/settings")
async def get_settings(request: Request) -> dict[str, Any]:
    return _coordinator(request).settings()


@router.put("/settings")
async def update_settings(payload: ResourceSettingsUpdate, request: Request) -> dict[str, Any]:
    try:
        return _coordinator(request).update_settings(ResourceProfile(payload.profile), payload.custom_limits)
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/groups")
async def list_groups(request: Request) -> list[dict[str, Any]]:
    return _coordinator(request).list_groups()


@router.put("/groups/{group_name}")
async def update_group(group_name: str, payload: ResourceGroupUpdate, request: Request) -> dict[str, Any]:
    try:
        return _coordinator(request).update_group(group_name, capacity_units=payload.capacity_units, enabled=payload.enabled)
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/diagnostics")
async def diagnostics(request: Request) -> dict[str, Any]:
    runtime = request.app.state.runtime
    dependencies = {
        "voice_configured": bool(getattr(runtime, "voice", None)),
        "media_configured": bool(getattr(runtime, "media", None)),
        "providers_configured": bool(getattr(runtime, "providers", None)),
    }
    return _coordinator(request).diagnostics(dependencies=dependencies)


@router.post("/requests", status_code=status.HTTP_202_ACCEPTED)
async def create_request(payload: ResourceRequestCreate, request: Request) -> dict[str, Any]:
    try:
        item = _coordinator(request).submit(owner_type=payload.owner_type, owner_id=payload.owner_id,
                                            resource_class=payload.resource_class,
                                            claims=[ResourceClaim(item.group, item.units) for item in payload.claims],
                                            session_id=payload.session_id, metadata=payload.metadata)
        return _result(item)
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/requests")
async def list_requests(request: Request, session_id: str | None = Query(default=None, pattern=r"^[0-9a-f]{32}$"), active_only: bool = False) -> list[dict[str, Any]]:
    return [_result(item) for item in _coordinator(request).list(session_id=session_id, active_only=active_only)]


@router.get("/requests/{request_id}")
async def get_request(request_id: str, request: Request) -> dict[str, Any]:
    try:
        return _result(_coordinator(request).get(request_id))
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/requests/{request_id}/events")
async def request_events(request_id: str, request: Request, after: int = Query(default=0, ge=0)) -> list[dict[str, Any]]:
    try:
        return _coordinator(request).events(request_id, after=after)
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/requests/{request_id}/start")
async def start_request(request_id: str, request: Request) -> dict[str, Any]:
    try:
        return _result(_coordinator(request).start(request_id))
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/requests/{request_id}/heartbeat")
async def heartbeat(request_id: str, request: Request) -> dict[str, Any]:
    try:
        return _result(_coordinator(request).heartbeat(request_id))
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/requests/{request_id}/complete")
async def complete(request_id: str, request: Request) -> dict[str, Any]:
    try:
        return _result(_coordinator(request).complete(request_id))
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/requests/{request_id}/fail")
async def fail(request_id: str, payload: ResourceFailure, request: Request) -> dict[str, Any]:
    try:
        return _result(_coordinator(request).fail(request_id, error_code=payload.error_code, error_message=payload.error_message))
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/requests/{request_id}/cancel")
async def cancel(request_id: str, request: Request) -> dict[str, Any]:
    try:
        return _result(_coordinator(request).cancel(request_id))
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/pump")
async def pump(request: Request) -> dict[str, int]:
    return {"admitted": _coordinator(request).pump()}
