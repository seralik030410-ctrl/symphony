from __future__ import annotations

from typing import Annotated
import asyncio
from dataclasses import asdict
from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from backend.storage.repository import NotFoundError, ConflictError, FINAL_TURN_STATUSES
from backend.models.base import ProviderError
from backend.tools.contracts import ToolError


router = APIRouter(prefix="/api/sessions/{session_id}")


def runtime_for(request: Request, session_id: str):
    runtime = request.app.state.runtime
    try:
        runtime.repository.get_session(session_id, include_history=False)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return runtime


def failure(exc: Exception) -> HTTPException:
    return HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 400, detail=str(exc))


def editable(runtime, session_id):
    session = runtime.repository.get_session(session_id, include_history=True)
    if runtime.memory.busy(session_id) or any(turn["status"] not in FINAL_TURN_STATUSES for turn in session["turns"]):
        raise HTTPException(status_code=409, detail="Дождитесь завершения текущего ответа или сжатия памяти")


class PathInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=1024)


class MemoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    facts: list[Annotated[str, Field(max_length=400)]] = Field(default_factory=list, max_length=24)
    decisions: list[Annotated[str, Field(max_length=400)]] = Field(default_factory=list, max_length=16)
    open_tasks: list[Annotated[str, Field(max_length=400)]] = Field(default_factory=list, max_length=16)
    artifact_index: list[Annotated[str, Field(max_length=400)]] = Field(default_factory=list, max_length=20)


class CapabilityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vision: bool | None = None
    max_context: int | None = Field(default=None, ge=1024, le=262144)


@router.get("/model-capabilities")
async def model_capabilities(session_id: str, request: Request):
    runtime = runtime_for(request, session_id)
    session = runtime.repository.get_session(session_id, include_history=False)
    return asdict(await runtime.gateway.resolve_capabilities(session["provider"], session["model"]))


@router.put("/model-capabilities")
async def update_capabilities(session_id: str, payload: CapabilityUpdate, request: Request):
    runtime = runtime_for(request, session_id)
    editable(runtime, session_id)
    session = runtime.repository.get_session(session_id, include_history=False)
    with runtime.database.read() as connection:
        active = connection.execute("SELECT 1 FROM turns WHERE provider=? AND model=? AND status IN ('queued','preparing','model_running') LIMIT 1", (session["provider"], session["model"])).fetchone()
    if active:
        raise HTTPException(status_code=409, detail="Эта модель сейчас отвечает в другом чате. Дождитесь завершения.")
    # An override is explicit, never inferred from a model's name.
    runtime.gateway.set_capabilities(session["provider"], session["model"], payload.model_dump(exclude_none=True))
    return asdict(await runtime.gateway.resolve_capabilities(session["provider"], session["model"]))


@router.get("/sources")
async def sources(session_id: str, request: Request, query: str | None = Query(default=None, max_length=2000)):
    try:
        runtime = runtime_for(request, session_id)
        matches = await asyncio.to_thread(runtime.file_index.search, session_id, query) if query else []
        return {"files": runtime.file_index.list_files(session_id), "matches": matches}
    except (NotFoundError, ToolError) as exc:
        raise failure(exc) from exc


@router.post("/sources/index")
async def index_source(session_id: str, payload: PathInput, request: Request):
    try:
        return await runtime_for(request, session_id).file_index.index_document(session_id, payload.path)
    except (NotFoundError, ToolError) as exc:
        raise failure(exc) from exc


@router.delete("/sources")
async def remove_source(session_id: str, request: Request, path: str = Query(min_length=1, max_length=1024)):
    try:
        runtime = runtime_for(request, session_id)
        editable(runtime, session_id)
        runtime.file_index.remove_index(session_id, path)
        return Response(status_code=204)
    except (NotFoundError, ToolError) as exc:
        raise failure(exc) from exc


@router.get("/memory")
async def get_memory(session_id: str, request: Request):
    return runtime_for(request, session_id).memory.get(session_id)


@router.put("/memory")
async def update_memory(session_id: str, payload: MemoryUpdate, request: Request):
    runtime = runtime_for(request, session_id)
    editable(runtime, session_id)
    return runtime.memory.update(session_id, payload.model_dump())


@router.post("/memory/snapshot")
async def create_memory_snapshot(session_id: str, request: Request):
    runtime = runtime_for(request, session_id)
    editable(runtime, session_id)
    try:
        return await runtime.memory.snapshot(session_id, runtime.gateway, runtime.repository)
    except (ProviderError, ConflictError) as exc:
        raise HTTPException(status_code=409 if isinstance(exc, ConflictError) else 422, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Модель не завершила сжатие за 180 секунд; история сохранена") from exc


@router.get("/memory/versions")
async def memory_versions(session_id: str, request: Request):
    return runtime_for(request, session_id).memory.history(session_id)


@router.delete("/memory", status_code=204)
async def clear_memory(session_id: str, request: Request):
    runtime = runtime_for(request, session_id)
    editable(runtime, session_id)
    runtime.memory.clear(session_id)
    return None
