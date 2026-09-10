"""Office document analysis, generation, editing, and conversion engine for FinControl IDE."""
from __future__ import annotations

from .inspector import (
    inspect_document,
    inspect_docx,
    inspect_xlsx,
    inspect_pptx,
    inspect_pdf,
    inspect_markdown,
    inspect_html,
    inspect_csv,
)
from .editor import (
    create_document,
    create_docx,
    create_xlsx,
    create_pptx,
    patch_document,
    patch_docx,
    patch_xlsx,
    patch_pptx,
    add_chart_to_xlsx,
    fill_range_xlsx,
    sort_xlsx,
    modify_structure_xlsx,
)
from .converter import (
    markdown_to_docx,
    docx_to_markdown,
    html_to_docx,
    pdf_to_docx,
    csv_to_xlsx,
    xlsx_to_csv,
)
from .analytics import analyze_spreadsheet

__all__ = [
    "inspect_document",
    "inspect_docx",
    "inspect_xlsx",
    "inspect_pptx",
    "inspect_pdf",
    "inspect_markdown",
    "inspect_html",
    "inspect_csv",
    "analyze_spreadsheet",
    "create_document",
    "create_docx",
    "create_xlsx",
    "create_pptx",
    "patch_document",
    "patch_docx",
    "patch_xlsx",
    "patch_pptx",
    "add_chart_to_xlsx",
    "fill_range_xlsx",
    "sort_xlsx",
    "modify_structure_xlsx",
    "markdown_to_docx",
    "docx_to_markdown",
    "html_to_docx",
    "pdf_to_docx",
    "csv_to_xlsx",
    "xlsx_to_csv",
]
