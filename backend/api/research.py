from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.api.context import editable, runtime_for

router = APIRouter(prefix="/api/sessions/{session_id}/research")


class ResearchSettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    allowed_domains: list[str] = Field(default_factory=list, max_length=50)


@router.get("")
async def settings(session_id: str, request: Request):
    return runtime_for(request, session_id).research.settings(session_id)


@router.put("")
async def update(session_id: str, payload: ResearchSettingsInput, request: Request):
    runtime = runtime_for(request, session_id)
    previous = runtime.research.settings(session_id)
    # Emergency network-off remains possible during a turn, but grants do not.
    if payload.enabled or sorted(payload.allowed_domains) != sorted(previous["allowed_domains"]):
        editable(runtime, session_id)
    try:
        return runtime.research.update(session_id, enabled=payload.enabled, allowed_domains=payload.allowed_domains)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/sources")
async def sources(session_id: str, request: Request, turn_id: str | None = None):
    return runtime_for(request, session_id).research.sources(session_id, turn_id)
