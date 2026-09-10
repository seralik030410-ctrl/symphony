from __future__ import annotations

import base64
import binascii
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

from backend.media.schemas import MediaJobCreate, MediaUpload
from backend.storage.repository import ConflictError, NotFoundError
from backend.tools.contracts import ToolError


router = APIRouter(prefix="/api/sessions/{session_id}/media", tags=["media"])


def _runtime(request: Request, session_id: str) -> Any:
    runtime = request.app.state.runtime
    runtime.repository.get_session(session_id, include_history=False)
    return runtime


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ToolError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@router.post("/assets", status_code=status.HTTP_201_CREATED)
async def upload_asset(session_id: str, payload: MediaUpload, request: Request) -> dict[str, Any]:
    try:
        raw = base64.b64decode(payload.content_base64, validate=True)
        asset, created = _runtime(request, session_id).media.assets.put(
            session_id, raw, filename=payload.filename, mime_type=payload.mime_type,
            source=payload.source, provenance=payload.provenance,
        )
        return {**asset, "created": created}
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Media content is not valid base64") from exc
    except (NotFoundError, ConflictError, ToolError, OSError) as exc:
        raise _error(exc) from exc


@router.get("/assets")
async def list_assets(session_id: str, request: Request, deleted: bool = False) -> list[dict[str, Any]]:
    try: return _runtime(request, session_id).media.assets.list(session_id, deleted=deleted)
    except (NotFoundError, ToolError) as exc: raise _error(exc) from exc


@router.get("/assets/{asset_id}")
async def get_asset(session_id: str, asset_id: str, request: Request) -> dict[str, Any]:
    try: return _runtime(request, session_id).media.assets.get(session_id, asset_id)
    except (NotFoundError, ToolError) as exc: raise _error(exc) from exc


@router.get("/assets/{asset_id}/content")
async def download_asset(session_id: str, asset_id: str, request: Request) -> FileResponse:
    try: path, asset = _runtime(request, session_id).media.assets.verified_file(session_id, asset_id)
    except (NotFoundError, ToolError) as exc: raise _error(exc) from exc
    return FileResponse(path, media_type=asset["mime_type"], filename=asset["filename"],
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                                 "Content-Security-Policy": "default-src 'none'; sandbox"})


@router.get("/assets/{asset_id}/preview")
async def preview_asset(session_id: str, asset_id: str, request: Request) -> FileResponse:
    try: path, _asset = _runtime(request, session_id).media.assets.verified_file(session_id, asset_id, preview=True)
    except (NotFoundError, ToolError) as exc: raise _error(exc) from exc
    return FileResponse(path, media_type="image/jpeg", content_disposition_type="inline",
                        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff",
                                 "Content-Security-Policy": "default-src 'none'; sandbox"})


@router.delete("/assets/{asset_id}")
async def trash_asset(session_id: str, asset_id: str, request: Request) -> dict[str, Any]:
    try: return _runtime(request, session_id).media.assets.trash(session_id, asset_id)
    except (NotFoundError, ToolError) as exc: raise _error(exc) from exc


@router.post("/assets/{asset_id}/restore")
async def restore_asset(session_id: str, asset_id: str, request: Request) -> dict[str, Any]:
    try: return _runtime(request, session_id).media.assets.restore(session_id, asset_id)
    except (NotFoundError, ConflictError, ToolError) as exc: raise _error(exc) from exc


@router.delete("/assets/{asset_id}/permanent")
async def purge_asset(session_id: str, asset_id: str, request: Request) -> dict[str, Any]:
    try: return _runtime(request, session_id).media.assets.purge(session_id, asset_id)
    except (NotFoundError, ConflictError, ToolError) as exc: raise _error(exc) from exc


@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
async def create_job(session_id: str, payload: MediaJobCreate, request: Request) -> dict[str, Any]:
    try:
        return _runtime(request, session_id).media.enqueue(
            session_id, payload.kind, payload.input, turn_id=payload.turn_id,
            provider_profile_id=payload.provider_profile_id,
        )
    except (NotFoundError, ConflictError, ToolError) as exc: raise _error(exc) from exc


@router.get("/jobs")
async def list_jobs(session_id: str, request: Request) -> list[dict[str, Any]]:
    try: return _runtime(request, session_id).media.jobs.list(session_id)
    except (NotFoundError, ToolError) as exc: raise _error(exc) from exc


@router.get("/jobs/{job_id}")
async def get_job(session_id: str, job_id: str, request: Request) -> dict[str, Any]:
    try: return _runtime(request, session_id).media.jobs.get(session_id, job_id)
    except (NotFoundError, ToolError) as exc: raise _error(exc) from exc


@router.get("/jobs/{job_id}/events")
async def list_job_events(session_id: str, job_id: str, request: Request,
                          after: int = Query(default=0, ge=0)) -> list[dict[str, Any]]:
    try: return _runtime(request, session_id).media.jobs.events(session_id, job_id, after)
    except (NotFoundError, ToolError) as exc: raise _error(exc) from exc


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(session_id: str, job_id: str, request: Request) -> dict[str, Any]:
    try: return _runtime(request, session_id).media.cancel(session_id, job_id)
    except (NotFoundError, ConflictError, ToolError) as exc: raise _error(exc) from exc


@router.post("/jobs/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_job(session_id: str, job_id: str, request: Request) -> dict[str, Any]:
    try: return _runtime(request, session_id).media.retry(session_id, job_id)
    except (NotFoundError, ConflictError, ToolError) as exc: raise _error(exc) from exc
