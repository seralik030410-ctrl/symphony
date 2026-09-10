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
)
from .converter import (
    markdown_to_docx,
    docx_to_markdown,
    html_to_docx,
    pdf_to_docx,
    csv_to_xlsx,
    xlsx_to_csv,
)

__all__ = [
    "inspect_document",
    "inspect_docx",
    "inspect_xlsx",
    "inspect_pptx",
    "inspect_pdf",
    "inspect_markdown",
    "inspect_html",
    "inspect_csv",
    "create_document",
    "create_docx",
    "create_xlsx",
    "create_pptx",
    "patch_document",
    "patch_docx",
    "patch_xlsx",
    "patch_pptx",
    "markdown_to_docx",
    "docx_to_markdown",
    "html_to_docx",
    "pdf_to_docx",
    "csv_to_xlsx",
    "xlsx_to_csv",
]
