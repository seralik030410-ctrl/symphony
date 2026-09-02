from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, StreamingResponse, Response

from backend.api.schemas import (
    ApprovalDecision,
    EventRead,
    ModelProfileRead,
    SessionCreate,
    SessionRead,
    SessionSummary,
    SessionUpdate,
    TurnCreate,
    TurnCreated,
    TurnRead,
    SkillInstall, SkillUpdate, SkillValidate, SkillTestPrompt,
)
from backend.storage.repository import ConflictError, FINAL_TURN_STATUSES, NotFoundError
from backend.tools.contracts import ToolError
from backend.models.base import ProviderError
from backend.tools.inspection import read_project_file, project_changes


router = APIRouter(prefix="/api")


def _state(request: Request) -> Any:
    return request.app.state.runtime


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    sandbox_ready, sandbox_message = await _state(request).sandbox.health()
    return {
        "status": "ok",
        "stage": "research",
        "version": "0.7.0-dev",
        "sandbox": {"ready": sandbox_ready, "message": sandbox_message},
    }


@router.get("/sandbox/health")
async def sandbox_health(request: Request) -> dict[str, Any]:
    ready, message = await _state(request).sandbox.health()
    return {"ready": ready, "message": message, "image": _state(request).settings.sandbox_image}


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(request: Request) -> list[dict[str, Any]]:
    return _state(request).repository.list_sessions()


@router.post("/sessions", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(payload: SessionCreate, request: Request) -> dict[str, Any]:
    runtime = _state(request)
    provider = payload.provider or "ollama"
    adapter = runtime.gateway.get_adapter(provider)
    model = payload.model or adapter.default_model
    if payload.model is None and provider == "ollama":
        try:
            installed = [name for name in await adapter.list_models() if not name.endswith(":cloud")]
            if installed and model not in installed:
                model = installed[-1]
        except ProviderError:
            pass  # Keep a configurable default; sending reports provider unavailability.
    context_window = min(runtime.settings.default_context_window, await runtime.gateway.context_window(provider, model))
    return runtime.repository.create_session(
        title=payload.title,
        provider=provider,
        model=model,
        system_prompt=payload.system_prompt,
        context_window=context_window,
        max_output=min(runtime.settings.default_max_output, context_window // 2),
    )


@router.get("/sessions/{session_id}", response_model=SessionRead)
async def get_session(session_id: str, request: Request) -> dict[str, Any]:
    try:
        return _state(request).repository.get_session(session_id, include_history=True)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/trash")
async def list_trashed_sessions(request: Request) -> list[dict[str, Any]]:
    return _state(request).repository.list_trashed_sessions()


@router.delete("/trash")
async def empty_session_trash(request: Request) -> dict[str, Any]:
    runtime = _state(request)
    session_ids = runtime.repository.purge_trashed_sessions()
    storage_warnings: list[dict[str, str]] = []
    for session_id in session_ids:
        try:
            runtime.workspaces.purge_session(session_id)
        except (OSError, ToolError) as exc:
            storage_warnings.append({"id": session_id, "message": str(exc)})
    return {
        "deleted": len(session_ids),
        "ids": session_ids,
        "storage_warnings": storage_warnings,
    }


@router.delete("/trash/{session_id}")
async def permanently_delete_session(session_id: str, request: Request) -> dict[str, Any]:
    runtime = _state(request)
    try:
        result = runtime.repository.purge_session(session_id)
        runtime.workspaces.purge_session(session_id)
        return result
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ToolError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/sessions/{session_id}")
async def trash_session(session_id: str, request: Request) -> dict[str, Any]:
    runtime = _state(request)
    try:
        session = runtime.repository.get_session(session_id, include_history=True)
        for turn in session["turns"]:
            if turn["status"] not in FINAL_TURN_STATUSES:
                await runtime.turn_service.cancel(turn["id"])
        return runtime.repository.trash_session(session_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/restore", response_model=SessionRead)
async def restore_session(session_id: str, request: Request) -> dict[str, Any]:
    try:
        return _state(request).repository.restore_session(session_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/tree")
async def get_workspace_tree(session_id: str, request: Request) -> dict[str, Any]:
    runtime = _state(request)
    try:
        runtime.repository.get_session(session_id, include_history=False)
        entries = runtime.workspaces.tree(session_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"session_id": session_id, "entries": entries}


@router.get("/sessions/{session_id}/approvals")
async def list_approvals(session_id: str, request: Request) -> list[dict[str, Any]]:
    try:
        return _state(request).repository.list_pending_approvals(session_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/files")
async def inspect_file(session_id: str, request: Request, path: str = Query(min_length=1, max_length=1024)) -> dict:
    runtime = _state(request)
    try:
        runtime.repository.get_session(session_id, include_history=False)
        return await asyncio.to_thread(read_project_file, runtime.workspaces, session_id, path)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ToolError as exc:
        raise HTTPException(status_code=404 if exc.code == "not_found" else 400, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/changes")
async def inspect_changes(session_id: str, request: Request,
                          snapshot_id: str | None = Query(default=None, pattern=r"^[0-9a-f]{32}$")) -> dict:
    runtime = _state(request)
    try:
        runtime.repository.get_session(session_id, include_history=False)
        return await asyncio.to_thread(project_changes, runtime.tools.snapshots, session_id, snapshot_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ToolError as exc:
        raise HTTPException(status_code=404 if exc.code == "not_found" else 400, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/snapshots")
async def list_snapshots(session_id: str, request: Request) -> list[dict[str, Any]]:
    runtime = _state(request)
    try:
        runtime.repository.get_session(session_id, include_history=False)
        return runtime.tools.snapshots.list(session_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/preview/{preview_path:path}", response_model=None)
async def preview_file(session_id: str, preview_path: str, request: Request) -> FileResponse:
    runtime = _state(request)
    try:
        runtime.repository.get_session(session_id, include_history=False)
        candidate = runtime.workspaces.resolve(session_id, preview_path, must_exist=True)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ToolError as exc:
        status_code = 404 if exc.code == "not_found" else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Preview file not found")
    headers = {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Access-Control-Allow-Origin": "*",  # Opaque-origin preview module assets; never credentials.
        "Content-Security-Policy": (
            "sandbox allow-scripts; default-src 'self' data: blob:; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; connect-src 'none'; object-src 'none'; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
        ),
    }
    return FileResponse(candidate, headers=headers)


@router.patch("/sessions/{session_id}", response_model=SessionRead)
async def update_session(
    session_id: str,
    payload: SessionUpdate,
    request: Request,
) -> dict[str, Any]:
    runtime = _state(request)
    if runtime.memory.busy(session_id):
        raise HTTPException(status_code=409, detail="Дождитесь завершения сжатия памяти")
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    try:
        if "provider" in changes:
            runtime.gateway.get_adapter(changes["provider"])
        if {"provider", "model", "context_window", "max_output"} & changes.keys():
            current = runtime.repository.get_session(session_id, include_history=False)
            provider = changes.get("provider", current["provider"])
            model = changes.get("model", current["model"])
            maximum = await runtime.gateway.context_window(provider, model)
            if "context_window" in changes and changes["context_window"] > maximum:
                raise HTTPException(status_code=422, detail=f"Лимит контекста этой модели в runtime — {maximum} токенов")
            context_window = changes.get("context_window", min(current["context_window"], maximum))
            output = changes.get("max_output", current["max_output"])
            if output >= context_window:
                raise HTTPException(status_code=422, detail="Лимит ответа должен быть меньше контекстного окна")
            changes["context_window"] = context_window
        return runtime.repository.update_session(session_id, changes)
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/model-limits")
async def session_model_limits(session_id: str, request: Request) -> dict[str, Any]:
    runtime = _state(request)
    try:
        session = runtime.repository.get_session(session_id, include_history=False)
        maximum = await runtime.gateway.context_window(session["provider"], session["model"])
        return {"max_context": maximum, "provider": session["provider"], "model": session["model"]}
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/sessions/{session_id}/turns",
    response_model=TurnCreated,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_turn(session_id: str, payload: TurnCreate, request: Request) -> dict[str, Any]:
    runtime = _state(request)
    if runtime.memory.busy(session_id):
        raise HTTPException(status_code=409, detail="Дождитесь завершения сжатия памяти")
    try:
        session = runtime.repository.get_session(session_id, include_history=False)
        attachments = [runtime.file_index.get_attachment(session_id, attachment_id) for attachment_id in payload.attachment_ids]
        for item in attachments:
            runtime.file_index.verified_bytes(session_id, item)
        if payload.image_mode == "vision" and any(item["mime_type"].startswith("image/") for item in attachments):
            capabilities = await runtime.gateway.resolve_capabilities(session["provider"], session["model"])
            if not capabilities.vision:
                raise HTTPException(status_code=422, detail="Выбранная модель не поддерживает изображения. Выберите vision-модель или используйте локальный OCR.")
        created = runtime.repository.create_turn(session_id, payload.content, payload.attachment_ids, image_mode=payload.image_mode)
    except ToolError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    runtime.turn_service.start(created["turn"]["id"])
    return created


@router.get("/turns/{turn_id}", response_model=TurnRead)
async def get_turn(turn_id: str, request: Request) -> dict[str, Any]:
    try:
        return _state(request).repository.get_turn(turn_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/turns/{turn_id}/cancel", response_model=TurnRead)
async def cancel_turn(turn_id: str, request: Request) -> dict[str, Any]:
    try:
        return await _state(request).turn_service.cancel(turn_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/approvals/{approval_id}/decision")
async def decide_approval(
    approval_id: str,
    payload: ApprovalDecision,
    request: Request,
) -> dict[str, Any]:
    try:
        return await _state(request).turn_service.resolve_approval(
            approval_id,
            approved=payload.approved,
            note=payload.note,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/turns/{turn_id}/retry", response_model=TurnCreated, status_code=status.HTTP_202_ACCEPTED)
async def retry_turn(turn_id: str, request: Request) -> dict[str, Any]:
    runtime = _state(request)
    try:
        original = runtime.repository.get_turn(turn_id)
        if original["status"] not in {"failed", "cancelled", "interrupted"}:
            raise HTTPException(status_code=409, detail="Only failed or cancelled turns can be retried")
        content = runtime.repository.get_turn_user_content(turn_id)
        if runtime.memory.busy(original["session_id"]):
            raise ConflictError("Дождитесь завершения сжатия памяти")
        attachments = runtime.repository.list_turn_attachments(turn_id)
        for item in attachments:
            runtime.file_index.verified_bytes(original["session_id"], item)
        created = runtime.repository.create_turn(original["session_id"], content, [item["id"] for item in attachments], retry_from_turn=turn_id)
    except ToolError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    runtime.turn_service.start(created["turn"]["id"])
    return created


@router.get("/turns/{turn_id}/events", response_model=None)
async def turn_events(
    turn_id: str,
    request: Request,
    after: int = Query(default=0, ge=0),
    stream: bool = Query(default=False),
) -> Any:
    runtime = _state(request)
    try:
        runtime.repository.get_turn(turn_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not stream:
        return [EventRead.model_validate(item) for item in runtime.repository.list_events(turn_id, after)]

    async def event_stream():
        cursor = after
        while True:
            events = runtime.repository.list_events(turn_id, cursor)
            for event in events:
                cursor = event["sequence"]
                body = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                yield f"id: {cursor}\nevent: {event['type']}\ndata: {body}\n\n"
            turn = runtime.repository.get_turn(turn_id)
            if turn["status"] in FINAL_TURN_STATUSES and not events:
                break
            if await request.is_disconnected():
                break
            yield ": keep-alive\n\n"
            await runtime.turn_service.broker.wait(turn_id, timeout=10.0)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/models", response_model=list[ModelProfileRead])
async def list_models(request: Request) -> list[dict[str, object]]:
    return await _state(request).gateway.list_profiles()


def _skill_error(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ToolError):
        code = 404 if exc.code == "not_found" else 400
        return HTTPException(status_code=code, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/skills")
async def list_skills(request: Request) -> list[dict[str, Any]]:
    return _state(request).skills.list()


@router.get("/skills/trash")
async def list_skill_trash(request: Request) -> list[dict[str, Any]]:
    return _state(request).skills.list(deleted=True)


@router.post("/skills/install", status_code=status.HTTP_201_CREATED)
async def install_skill(payload: SkillInstall, request: Request) -> dict[str, Any]:
    skills = _state(request).skills
    try:
        if payload.source_type == "zip":
            if not payload.zip_base64:
                raise ToolError("invalid_archive", "Choose a ZIP file")
            return await asyncio.to_thread(skills.install_zip, payload.zip_base64,
                                           filename=payload.filename or "skill.zip", mode=payload.mode)
        if payload.source_type == "folder":
            return await asyncio.to_thread(skills.install_folder, payload.source, mode=payload.mode)
        return await asyncio.to_thread(skills.install_git, payload.source, mode=payload.mode)
    except Exception as exc:
        raise _skill_error(exc) from exc


@router.post("/skills/validate")
async def validate_skill(payload: SkillValidate) -> dict[str, Any]:
    try:
        from backend.skills.store import SkillStore
        value = await asyncio.to_thread(SkillStore.validate_text, payload.skill_md)
        return {key: value[key] for key in ("valid", "name", "slug", "description")}
    except Exception as exc:
        raise _skill_error(exc) from exc


@router.post("/skills/test")
async def test_skill_prompt(payload: SkillTestPrompt, request: Request) -> dict[str, Any]:
    return _state(request).skills.match(payload.prompt)


@router.get("/skills/{skill_id}")
async def get_skill(skill_id: str, request: Request) -> dict[str, Any]:
    try:
        return _state(request).skills.get(skill_id)
    except Exception as exc:
        raise _skill_error(exc) from exc


@router.patch("/skills/{skill_id}")
async def update_skill(skill_id: str, payload: SkillUpdate, request: Request) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(_state(request).skills.update, skill_id, **payload.model_dump(exclude_unset=True))
    except Exception as exc:
        raise _skill_error(exc) from exc


@router.delete("/skills/{skill_id}")
async def trash_skill(skill_id: str, request: Request) -> dict[str, Any]:
    try:
        return _state(request).skills.trash(skill_id)
    except Exception as exc:
        raise _skill_error(exc) from exc


@router.post("/skills/{skill_id}/restore")
async def restore_skill(skill_id: str, request: Request) -> dict[str, Any]:
    try:
        return _state(request).skills.restore(skill_id)
    except Exception as exc:
        raise _skill_error(exc) from exc


@router.get("/skills/{skill_id}/resource")
async def get_skill_resource(skill_id: str, request: Request,
                             path: str = Query(min_length=1, max_length=1_024)) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(_state(request).skills.read_resource, skill_id, path)
    except Exception as exc:
        raise _skill_error(exc) from exc


@router.get("/skills/{skill_id}/export")
async def export_skill(skill_id: str, request: Request) -> Response:
    try:
        filename, content = await asyncio.to_thread(_state(request).skills.export_zip, skill_id)
        return Response(content, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"',
                                 "Cache-Control": "no-store"})
    except Exception as exc:
        raise _skill_error(exc) from exc


@router.get("/tools")
async def list_tools(request: Request) -> list[dict[str, Any]]:
    return _state(request).tools.definitions()
