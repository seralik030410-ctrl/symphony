"""Agent tools for inspecting, creating, patching, and converting office documents."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from pydantic import Field

from backend.tools.contracts import Tool, ToolContext, ToolError, ToolInput, ToolResult
from backend.tools.workspace import WorkspaceManager
from backend.office.inspector import inspect_document
from backend.office.editor import create_document, patch_document
from backend.office.converter import (
    markdown_to_docx,
    docx_to_markdown,
    html_to_docx,
    pdf_to_docx,
    csv_to_xlsx,
    xlsx_to_csv,
)


class OfficeInspectInput(ToolInput):
    path: str = Field(min_length=1, max_length=500, description="Path to .docx, .xlsx, .pptx, .pdf, .md, .html, or .csv file")


class OfficeInspectTool(Tool):
    name = "office.inspect"
    title = "Inspect office document"
    description = (
        "Deeply inspect office documents (.docx, .xlsx, .pptx, .pdf, .md, .html, .csv). "
        "Returns structured text, headings, tables, sheets, cells, formulas, or slide notes."
    )
    input_model = OfficeInspectInput
    read_only = True

    def __init__(self, workspaces: WorkspaceManager) -> None:
        self.workspaces = workspaces

    async def execute(self, context: ToolContext, arguments: OfficeInspectInput) -> ToolResult:
        try:
            path = self.workspaces.resolve(context.session_id, arguments.path, must_exist=True)
            info = inspect_document(path)
            return ToolResult(info)
        except Exception as exc:
            raise ToolError("office_inspect_error", str(exc)) from exc


class OfficeCreateInput(ToolInput):
    path: str = Field(min_length=1, max_length=500, description="Target path (e.g. report.docx, model.xlsx, slides.pptx)")
    title: str = Field(default="", description="Document or presentation title")
    subtitle: str = Field(default="", description="Optional presentation subtitle or docx subtitle")
    sections: list[dict[str, Any]] = Field(default_factory=list, description="For .docx: list of {heading: str, level: int, paragraphs: list[str], table: {headers: list, rows: list}}")
    sheets: list[dict[str, Any]] = Field(default_factory=list, description="For .xlsx: list of {name: str, headers: list, rows: list}")
    slides: list[dict[str, Any]] = Field(default_factory=list, description="For .pptx: list of {title: str, bullets: list[str], notes: str}")


class OfficeCreateTool(Tool):
    name = "office.create"
    title = "Create office document"
    description = (
        "Create a formatted office document (.docx, .xlsx, .pptx) with structured headings, tables, "
        "spreadsheets with styling, or presentations with bullet points and speaker notes."
    )
    input_model = OfficeCreateInput
    read_only = False
    destructive = True

    def __init__(self, workspaces: WorkspaceManager) -> None:
        self.workspaces = workspaces

    async def execute(self, context: ToolContext, arguments: OfficeCreateInput) -> ToolResult:
        try:
            target_path = self.workspaces.resolve(context.session_id, arguments.path)
            suffix = target_path.suffix.lower()
            if suffix == ".docx":
                result = create_document(
                    target_path,
                    title=arguments.title,
                    sections=arguments.sections,
                )
            elif suffix in (".xlsx", ".xlsm"):
                result = create_document(
                    target_path,
                    sheets=arguments.sheets,
                )
            elif suffix == ".pptx":
                result = create_document(
                    target_path,
                    title=arguments.title,
                    subtitle=arguments.subtitle,
                    slides=arguments.slides,
                )
            else:
                raise ToolError("unsupported_format", f"Office create only supports .docx, .xlsx, and .pptx (got {suffix})")

            relative = self.workspaces.relative(context.session_id, target_path)
            return ToolResult(
                output=result,
                changed_files=[relative],
            )
        except Exception as exc:
            if isinstance(exc, ToolError):
                raise
            raise ToolError("office_create_error", str(exc)) from exc


class OfficePatchInput(ToolInput):
    path: str = Field(min_length=1, max_length=500, description="Path to existing .docx, .xlsx, or .pptx file")
    paragraph_updates: list[dict[str, Any]] | None = Field(default=None, description="For .docx: [{index: int, text: str}] or [{search: str, text: str}]")
    append_paragraphs: list[dict[str, Any]] | None = Field(default=None, description="For .docx: [{text: str, style: str}]")
    table_updates: list[dict[str, Any]] | None = Field(default=None, description="For .docx: [{table_index: int, row: int, col: int, text: str}]")
    cell_updates: list[dict[str, Any]] | None = Field(default=None, description="For .xlsx: [{cell: 'B5', value: 100, sheet: 'Sheet1'}] or [{row: 1, col: 2, value: 'Total'}]")
    append_rows: list[list[Any]] | None = Field(default=None, description="For .xlsx: list of rows to append")
    new_sheets: list[str] | None = Field(default=None, description="For .xlsx: list of sheet names to add")
    slide_updates: list[dict[str, Any]] | None = Field(default=None, description="For .pptx: [{index: int, title: str, bullets: list[str], notes: str}]")
    append_slides: list[dict[str, Any]] | None = Field(default=None, description="For .pptx: [{title: str, bullets: list[str], notes: str}]")


class OfficePatchTool(Tool):
    name = "office.patch"
    title = "Patch office document"
    description = (
        "Surgically update an existing office document (.docx paragraphs/tables, .xlsx cells/formulas/rows, "
        "or .pptx slides/bullets/notes) while preserving all other styles and content."
    )
    input_model = OfficePatchInput
    read_only = False

    def __init__(self, workspaces: WorkspaceManager) -> None:
        self.workspaces = workspaces

    async def execute(self, context: ToolContext, arguments: OfficePatchInput) -> ToolResult:
        try:
            target_path = self.workspaces.resolve(context.session_id, arguments.path, must_exist=True)
            suffix = target_path.suffix.lower()
            if suffix == ".docx":
                result = patch_document(
                    target_path,
                    paragraph_updates=arguments.paragraph_updates,
                    append_paragraphs=arguments.append_paragraphs,
                    table_updates=arguments.table_updates,
                )
            elif suffix in (".xlsx", ".xlsm"):
                result = patch_document(
                    target_path,
                    cell_updates=arguments.cell_updates,
                    append_rows=arguments.append_rows,
                    new_sheets=arguments.new_sheets,
                )
            elif suffix == ".pptx":
                result = patch_document(
                    target_path,
                    slide_updates=arguments.slide_updates,
                    append_slides=arguments.append_slides,
                )
            else:
                raise ToolError("unsupported_format", f"Office patch only supports .docx, .xlsx, and .pptx (got {suffix})")

            relative = self.workspaces.relative(context.session_id, target_path)
            return ToolResult(
                output=result,
                changed_files=[relative],
            )
        except Exception as exc:
            if isinstance(exc, ToolError):
                raise
            raise ToolError("office_patch_error", str(exc)) from exc


class OfficeConvertInput(ToolInput):
    source_path: str = Field(min_length=1, max_length=500, description="Source file path")
    target_format: str = Field(min_length=1, max_length=10, description="Target format: 'docx', 'md', 'csv', 'xlsx'")
    output_path: str | None = Field(default=None, description="Optional target file path. If omitted, derives from source filename.")


class OfficeConvertTool(Tool):
    name = "office.convert"
    title = "Convert office documents"
    description = (
        "Convert between document formats: Markdown -> DOCX, DOCX -> Markdown, "
        "PDF -> DOCX, CSV -> XLSX, XLSX -> CSV, HTML -> DOCX."
    )
    input_model = OfficeConvertInput
    read_only = False

    def __init__(self, workspaces: WorkspaceManager) -> None:
        self.workspaces = workspaces

    async def execute(self, context: ToolContext, arguments: OfficeConvertInput) -> ToolResult:
        try:
            src = self.workspaces.resolve(context.session_id, arguments.source_path, must_exist=True)
            src_suffix = src.suffix.lower().lstrip(".")
            tgt_format = arguments.target_format.lower().lstrip(".")

            if arguments.output_path:
                out_path = self.workspaces.resolve(context.session_id, arguments.output_path)
            else:
                out_name = f"{src.stem}.{tgt_format}"
                out_path = src.with_name(out_name)

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
                raise ToolError("unsupported_conversion", f"Conversion from {src_suffix} to {tgt_format} is not supported")

            relative_out = self.workspaces.relative(context.session_id, out_path)
            return ToolResult(
                output={
                    "status": "converted",
                    "source": arguments.source_path,
                    "output_path": relative_out,
                    "target_format": tgt_format,
                    "file_size": out_path.stat().st_size,
                },
                changed_files=[relative_out],
            )
        except Exception as exc:
            if isinstance(exc, ToolError):
                raise
            raise ToolError("office_convert_error", str(exc)) from exc
