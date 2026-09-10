"""FastAPI router for Office document inspection, editing, rendering, and conversion."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.storage.repository import NotFoundError
from backend.tools.contracts import ToolError
from backend.office.inspector import inspect_document
from backend.office.editor import patch_document, create_document
from backend.office.analytics import analyze_spreadsheet
from backend.office.converter import (
    markdown_to_docx,
    docx_to_markdown,
    html_to_docx,
    pdf_to_docx,
    csv_to_xlsx,
    xlsx_to_csv,
)

router = APIRouter(prefix="/api/sessions/{session_id}/office", tags=["office"])

MIME_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".pdf": "application/pdf",
    ".csv": "text/csv",
    ".md": "text/markdown",
    ".html": "text/html",
}


def runtime_for(request: Request, session_id: str):
    runtime = request.app.state.runtime
    runtime.repository.get_session(session_id, include_history=False)
    return runtime


def error_response(error: Exception):
    if isinstance(error, (NotFoundError, FileNotFoundError)):
        return HTTPException(status_code=404, detail=str(error))
    return HTTPException(status_code=400, detail=str(error))


class SaveOfficeDocInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    path: str = Field(min_length=1, max_length=500)
    format: str | None = None
    # Surgical updates
    paragraph_updates: list[dict[str, Any]] | None = None
    append_paragraphs: list[dict[str, Any]] | None = None
    table_updates: list[dict[str, Any]] | None = None
    cell_updates: list[dict[str, Any]] | None = None
    append_rows: list[list[Any]] | None = None
    new_sheets: list[str] | None = None
    style_updates: list[dict[str, Any]] | None = None
    fill_ranges: list[dict[str, Any]] | None = None
    sort_operations: list[dict[str, Any]] | None = None
    row_operations: list[dict[str, Any]] | None = None
    col_operations: list[dict[str, Any]] | None = None
    charts: list[dict[str, Any]] | None = None
    slide_updates: list[dict[str, Any]] | None = None
    append_slides: list[dict[str, Any]] | None = None
    # Full replacements
    content_base64: str | None = None
    text_content: str | None = None


class AnalyzeOfficeDocInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    path: str = Field(min_length=1, max_length=500)
    sheet_name: str | None = None
    deep: bool = True


class ConvertOfficeDocInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    source_path: str = Field(min_length=1, max_length=500)
    target_format: str = Field(min_length=1, max_length=10)
    output_path: str | None = None


@router.get("/inspect")
async def inspect_office_file(session_id: str, path: str, request: Request):
    """Inspects a workspace office document and returns structured representation."""
    try:
        runtime = runtime_for(request, session_id)
        resolved_path = runtime.workspaces.resolve(session_id, path, must_exist=True)
        return inspect_document(resolved_path)
    except Exception as error:
        raise error_response(error) from error


@router.get("/raw")
async def get_raw_office_file(session_id: str, path: str, request: Request):
    """Downloads or streams raw office file."""
    try:
        runtime = runtime_for(request, session_id)
        resolved_path = runtime.workspaces.resolve(session_id, path, must_exist=True)
        media_type = MIME_TYPES.get(resolved_path.suffix.lower(), "application/octet-stream")
        return FileResponse(
            resolved_path,
            media_type=media_type,
            filename=resolved_path.name,
            content_disposition_type="inline" if resolved_path.suffix.lower() == ".pdf" else "attachment",
            headers={"Cache-Control": "no-cache"},
        )
    except Exception as error:
        raise error_response(error) from error


@router.post("/save")
async def save_office_file(session_id: str, payload: SaveOfficeDocInput, request: Request):
    """Saves or patches an office document inside the session workspace with snapshot tracking."""
    try:
        runtime = runtime_for(request, session_id)
        resolved_path = runtime.workspaces.resolve(session_id, payload.path)
        existed = resolved_path.exists()

        # Snapshot before mutating existing files
        if existed and runtime.tools.snapshots:
            try:
                runtime.tools.snapshots.create(session_id, "user-save", f"save {payload.path}")
            except Exception:
                pass  # Non-fatal snapshot warning

        # Binary base64 replacement
        if payload.content_base64:
            raw_data = base64.b64decode(payload.content_base64)
            resolved_path.parent.mkdir(parents=True, exist_ok=True)
            resolved_path.write_bytes(raw_data)
        # Plain text / markdown replacement
        elif payload.text_content is not None:
            resolved_path.parent.mkdir(parents=True, exist_ok=True)
            resolved_path.write_text(payload.text_content, encoding="utf-8")
        # Surgical patching
        elif existed:
            patch_document(
                resolved_path,
                paragraph_updates=payload.paragraph_updates,
                append_paragraphs=payload.append_paragraphs,
                table_updates=payload.table_updates,
                cell_updates=payload.cell_updates,
                append_rows=payload.append_rows,
                new_sheets=payload.new_sheets,
                style_updates=payload.style_updates,
                fill_ranges=payload.fill_ranges,
                sort_operations=payload.sort_operations,
                row_operations=payload.row_operations,
                col_operations=payload.col_operations,
                charts=payload.charts,
                slide_updates=payload.slide_updates,
                append_slides=payload.append_slides,
            )
        else:
            raise ValueError(f"File {payload.path} does not exist and no content was provided to create it.")

        # Re-inspect and return updated state
        updated_doc = inspect_document(resolved_path)
        return {
            "status": "saved",
            "path": runtime.workspaces.relative(session_id, resolved_path),
            "document": updated_doc,
        }
    except Exception as error:
        raise error_response(error) from error


@router.post("/analyze")
async def analyze_office_file(session_id: str, payload: AnalyzeOfficeDocInput, request: Request):
    """Deeply analyzes an Excel/CSV spreadsheet and returns statistics, column profiles, and formula audit."""
    try:
        runtime = runtime_for(request, session_id)
        resolved_path = runtime.workspaces.resolve(session_id, payload.path, must_exist=True)
        return analyze_spreadsheet(resolved_path, sheet_name=payload.sheet_name, deep=payload.deep)
    except Exception as error:
        raise error_response(error) from error


@router.post("/convert")
async def convert_office_file(session_id: str, payload: ConvertOfficeDocInput, request: Request):
    """Converts a document to another format."""
    try:
        runtime = runtime_for(request, session_id)
        src = runtime.workspaces.resolve(session_id, payload.source_path, must_exist=True)
        src_suffix = src.suffix.lower().lstrip(".")
        tgt_format = payload.target_format.lower().lstrip(".")

        if payload.output_path:
            out_path = runtime.workspaces.resolve(session_id, payload.output_path)
        else:
            out_path = src.with_name(f"{src.stem}.{tgt_format}")

        if runtime.tools.snapshots:
            try:
                runtime.tools.snapshots.create(session_id, "user-convert", f"convert {payload.source_path}")
            except Exception:
                pass

        if src_suffix in ("md", "markdown") and tgt_format == "docx":
            text = src.read_text(encoding="utf-8", errors="replace")
            markdown_to_docx(text, out_path, title=src.stem.replace("_", " ").title())
        elif src_suffix == "docx" and tgt_format in ("md", "markdown"):
            md_text = docx_to_markdown(src)
            out_path.write_text(md_text, encoding="utf-8")
        elif src_suffix in ("html", "htm") and tgt_format == "docx":
            html_text = src.read_text(encoding="utf-8", errors="replace")
            html_to_docx(html_text, out_path)
        elif src_suffix == "pdf" and tgt_format == "docx":
            pdf_to_docx(src, out_path)
        elif src_suffix in ("csv", "tsv") and tgt_format == "xlsx":
            csv_to_xlsx(src, out_path)
        elif src_suffix in ("xlsx", "xlsm") and tgt_format == "csv":
            xlsx_to_csv(src, out_path)
        else:
            raise ValueError(f"Conversion from {src_suffix} to {tgt_format} is not supported")

        relative_out = runtime.workspaces.relative(session_id, out_path)
        return {
            "status": "converted",
            "source": payload.source_path,
            "output_path": relative_out,
            "target_format": tgt_format,
            "document": inspect_document(out_path),
        }
    except Exception as error:
        raise error_response(error) from error
