from __future__ import annotations

import base64
import uuid
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.storage.repository import NotFoundError
from backend.tools.contracts import ToolError

router = APIRouter(prefix="/api/sessions/{session_id}")


def runtime_for(request, session_id):
    runtime = request.app.state.runtime
    runtime.repository.get_session(session_id, include_history=False)
    return runtime


def error_response(error):
    return HTTPException(status_code=404 if isinstance(error, NotFoundError) else 409, detail=str(error))


@router.get("/artifacts")
async def list_artifacts(session_id: str, request: Request):
    try: return runtime_for(request, session_id).artifacts.list(session_id)
    except (NotFoundError, ToolError) as error: raise error_response(error) from error


@router.get("/artifacts/{artifact_id}")
@router.get("/artifacts/{artifact_id}/versions/{version}")
async def get_artifact(session_id: str, artifact_id: str, request: Request, version: int | None = None):
    try: return runtime_for(request, session_id).artifacts.get(session_id, artifact_id, version)
    except (NotFoundError, ToolError) as error: raise error_response(error) from error


@router.get("/artifacts/{artifact_id}/versions/{version}/files/{filename}")
async def download_artifact(session_id: str, artifact_id: str, version: int, filename: str, request: Request):
    try: path = runtime_for(request, session_id).artifacts.file(session_id, artifact_id, version, filename)
    except (NotFoundError, ToolError) as error: raise error_response(error) from error
    media = {".pdf": "application/pdf", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation", ".png": "image/png", ".json": "application/json"}[path.suffix]
    return FileResponse(path, media_type=media, filename=path.name, content_disposition_type="inline" if path.suffix == ".png" else "attachment",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; sandbox"})


class UploadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=150, pattern=r"(?i)^[^/\\:\x00]+\.(?:txt|md|csv|json|pdf|docx|pptx|xlsx|png|jpe?g|webp)$")
    content_base64: str = Field(max_length=33_333_336)


@router.post("/inputs", status_code=201)
async def upload_input(session_id: str, payload: UploadInput, request: Request):
    try:
        runtime = runtime_for(request, session_id)
        raw = base64.b64decode(payload.content_base64, validate=True)
        suffix = "." + payload.filename.rsplit(".", 1)[-1].lower()
        limit = 10_000_000 if suffix in {".png", ".jpg", ".jpeg", ".webp"} else 25_000_000
        if len(raw) > limit: raise ValueError(f"File must be at most {limit // 1_000_000} MB")
        relative = f"inputs/{uuid.uuid4().hex[:12]}-{payload.filename}"
        path = runtime.workspaces.resolve(session_id, relative)
        path.parent.mkdir(exist_ok=True)
        with path.open("xb") as file: file.write(raw)
        try:
            attachment = runtime.file_index.register_attachment(session_id, relative, payload.filename)
            indexed = await runtime.file_index.index_document(session_id, relative) if suffix not in {".png", ".jpg", ".jpeg", ".webp"} else None
        except Exception:
            if 'attachment' in locals():
                runtime.file_index.remove_pending_attachment(session_id, attachment["id"])
            path.unlink(missing_ok=True)
            raise
        return {**attachment, "indexed": indexed}
    except (NotFoundError, ToolError) as error: raise error_response(error) from error
    except (ValueError, OSError) as error: raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/inputs")
async def list_pending_inputs(session_id: str, request: Request):
    try:
        return runtime_for(request, session_id).file_index.list_attachments(session_id, pending_only=True)
    except (NotFoundError, ToolError) as error: raise error_response(error) from error


@router.get("/inputs/{attachment_id}")
async def get_input(session_id: str, attachment_id: str, request: Request):
    try:
        runtime = runtime_for(request, session_id)
        attachment = runtime.file_index.get_attachment(session_id, attachment_id)
        runtime.file_index.verified_bytes(session_id, attachment)
        path = runtime.workspaces.resolve(session_id, attachment["path"], must_exist=True)
        inline = attachment["mime_type"].startswith("image/")
        return FileResponse(path, media_type=attachment["mime_type"], filename=attachment["filename"], content_disposition_type="inline" if inline else "attachment",
                            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; sandbox"})
    except (NotFoundError, ToolError) as error: raise error_response(error) from error


@router.delete("/inputs/{attachment_id}", status_code=204)
async def delete_input(session_id: str, attachment_id: str, request: Request):
    try:
        runtime = runtime_for(request, session_id)
        runtime.file_index.remove_pending_attachment(session_id, attachment_id)
        return None
    except (NotFoundError, ToolError) as error: raise error_response(error) from error
