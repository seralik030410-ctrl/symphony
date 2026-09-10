from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status

from backend.media.providers.comfyui import HOP_BY_HOP_HEADERS
from backend.media.schemas import (
    ComfyUIConnectionUpdate,
    ComfyUIQuickGenerate,
    ComfyUIWorkflowImport,
    ComfyUIWorkflowRun,
)
from backend.storage.repository import ConflictError, NotFoundError
from backend.tools.contracts import ToolError


router = APIRouter(prefix="/api/comfyui", tags=["comfyui"])
MAX_PROXY_BODY_BYTES = 2_000_000


def _media(request: Request):
    return request.app.state.runtime.media


def _session(request: Request, session_id: str):
    runtime = request.app.state.runtime
    runtime.repository.get_session(session_id, include_history=False)
    return runtime.media


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(404, str(exc))
    if isinstance(exc, ConflictError):
        return HTTPException(409, str(exc))
    if isinstance(exc, ToolError):
        return HTTPException(422, str(exc))
    return HTTPException(400, "ComfyUI request could not be completed")


@router.get("/connection")
async def connection(request: Request) -> dict[str, Any]:
    connector = _media(request).comfyui
    return {
        "configured": connector is not None,
        "origin": connector.origin if connector else None,
        "studio_url": "/api/comfyui/proxy/" if connector else None,
        "managed_process_running": bool(_media(request).comfyui_process and _media(request).comfyui_process.running),
    }


@router.put("/connection")
async def update_connection(payload: ComfyUIConnectionUpdate, request: Request) -> dict[str, Any]:
    try:
        return _media(request).configure_comfyui(
            payload.base_url, allow_private_network=payload.allow_private_network, timeout_seconds=payload.timeout_seconds,
        )
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/health")
async def health(request: Request) -> dict[str, Any]:
    try:
        return await _media(request).comfyui_health()
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/templates")
async def templates(request: Request, kind: str | None = None) -> list[dict[str, Any]]:
    if kind is not None and kind not in {"image", "video"}:
        raise HTTPException(422, "Template kind must be image or video")
    return _media(request).workflows.list(kind)  # type: ignore[arg-type]


@router.post("/sessions/{session_id}/quick", status_code=status.HTTP_202_ACCEPTED)
async def quick_generate(session_id: str, payload: ComfyUIQuickGenerate, request: Request) -> dict[str, Any]:
    try:
        return _session(request, session_id).quick_generate(
            session_id, payload.kind, payload.template_id, payload.values,
            turn_id=payload.turn_id, provider_profile_id=payload.provider_profile_id,
        )
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/sessions/{session_id}/workflows/import")
async def import_workflow(session_id: str, payload: ComfyUIWorkflowImport, request: Request) -> dict[str, Any]:
    """Validate only. Importing a graph must never execute it implicitly."""
    _session(request, session_id)
    try:
        # Uses the same media job JSON restrictions without creating a job.
        from backend.media.jobs import _validate_json
        _validate_json(payload.workflow)
        if len(json.dumps(payload.workflow, ensure_ascii=False).encode("utf-8")) > 512_000:
            raise ToolError("invalid_workflow", "Imported workflow exceeds 512 KB")
        return {"title": payload.title, "workflow": payload.workflow, "executable": False}
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/sessions/{session_id}/workflows/run", status_code=status.HTTP_202_ACCEPTED)
async def run_workflow(session_id: str, payload: ComfyUIWorkflowRun, request: Request) -> dict[str, Any]:
    try:
        return _session(request, session_id).enqueue_workflow(
            session_id, payload.kind, payload.workflow, title=payload.title,
            turn_id=payload.turn_id, provider_profile_id=payload.provider_profile_id,
        )
    except Exception as exc:
        raise _error(exc) from exc


async def _controlled_proxy(path: str, request: Request) -> Response:
    """Same-origin bridge to the *configured* ComfyUI origin, never a URL relay."""
    body = await request.body()
    if len(body) > MAX_PROXY_BODY_BYTES:
        raise HTTPException(413, "ComfyUI proxy body is too large")
    source_headers = {
        key: value for key, value in request.headers.items()
        if key.lower() in {"accept", "accept-language", "content-type", "if-none-match", "if-modified-since", "range", "user-agent"}
    }
    try:
        connector = _media(request).comfyui
        if not connector:
            raise ToolError("comfyui_not_configured", "ComfyUI Studio is not configured")
        upstream = await connector.proxy(request.method, path, query=request.url.query, body=body or None, headers=source_headers)
    except Exception as exc:
        raise _error(exc) from exc
    response_headers = {
        key: value for key, value in upstream.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS | {"content-length", "set-cookie", "server"}
    }
    response_headers["Cache-Control"] = "private, no-store"
    response_headers["X-Content-Type-Options"] = "nosniff"
    return Response(content=upstream.content if request.method != "HEAD" else b"", status_code=upstream.status_code,
                    headers=response_headers, media_type=upstream.headers.get("content-type"))


@router.get("/proxy/{path:path}")
async def controlled_proxy_get(path: str, request: Request) -> Response:
    return await _controlled_proxy(path, request)


@router.head("/proxy/{path:path}")
async def controlled_proxy_head(path: str, request: Request) -> Response:
    return await _controlled_proxy(path, request)


@router.post("/proxy/{path:path}")
async def controlled_proxy_post(path: str, request: Request) -> Response:
    return await _controlled_proxy(path, request)
