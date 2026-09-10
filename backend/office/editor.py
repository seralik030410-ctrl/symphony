"""Document creation and patching (.docx, .xlsx, .pptx, .pdf) for FinControl IDE."""
from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import docx
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
except ImportError:
    docx = None

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    openpyxl = None

try:
    import pptx
    from pptx.util import Inches as PptxInches, Pt as PptxPt
    from pptx.dml.color import RGBColor as PptxRGBColor
except ImportError:
    pptx = None

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table as RlTable, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
except ImportError:
    SimpleDocTemplate = None


def patch_docx(
    file_path: Path | str,
    *,
    paragraph_updates: list[dict[str, Any]] | None = None,
    append_paragraphs: list[dict[str, Any]] | None = None,
    table_updates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Applies surgical edits to an existing Word .docx file."""
    if docx is None:
        raise RuntimeError("python-docx is not installed")

    path = Path(file_path)
    doc = docx.Document(path)
    modified_paragraphs = 0
    added_paragraphs = 0
    modified_cells = 0

    if paragraph_updates:
        for update in paragraph_updates:
            idx = update.get("index")
            search_text = update.get("search")
            new_text = update.get("text", "")
            if idx is not None and 0 <= idx < len(doc.paragraphs):
                doc.paragraphs[idx].text = new_text
                modified_paragraphs += 1
            elif search_text:
                for p in doc.paragraphs:
                    if search_text in p.text:
                        p.text = p.text.replace(search_text, new_text)
                        modified_paragraphs += 1
                        break

    if append_paragraphs:
        for item in append_paragraphs:
            text = item.get("text", "")
            heading_level = item.get("heading")
            if heading_level:
                doc.add_heading(text, level=int(heading_level))
            else:
                p = doc.add_paragraph(text)
                if item.get("bullet"):
                    p.style = "List Bullet"
            added_paragraphs += 1

    if table_updates:
        for tup in table_updates:
            t_idx = tup.get("table_index", 0)
            if 0 <= t_idx < len(doc.tables):
                table = doc.tables[t_idx]
                # Direct flat update {table_index, row, col, text}
                if "row" in tup and "col" in tup:
                    r = tup.get("row", 0)
                    c = tup.get("col", 0)
                    text = str(tup.get("text", ""))
                    if 0 <= r < len(table.rows) and 0 <= c < len(table.columns):
                        table.cell(r, c).text = text
                        modified_cells += 1
                # Nested cells list
                for cell_update in tup.get("cells", []):
                    r = cell_update.get("row", 0)
                    c = cell_update.get("col", 0)
                    text = str(cell_update.get("text", ""))
                    if 0 <= r < len(table.rows) and 0 <= c < len(table.columns):
                        table.cell(r, c).text = text
                        modified_cells += 1

    doc.save(path)
    return {
        "status": "success",
        "file_name": path.name,
        "modified_paragraphs": modified_paragraphs,
        "added_paragraphs": added_paragraphs,
        "modified_cells": modified_cells,
        "file_size": path.stat().st_size,
    }


def patch_xlsx(
    file_path: Path | str,
    *,
    sheet_name: str | None = None,
    cell_updates: list[dict[str, Any]] | None = None,
    append_rows: list[list[Any]] | None = None,
    new_sheets: list[str] | None = None,
) -> dict[str, Any]:
    """Applies surgical cell and formula edits to an existing Excel .xlsx file."""
    if openpyxl is None:
        raise RuntimeError("openpyxl is not installed")

    path = Path(file_path)
    wb = openpyxl.load_workbook(path)
    active_sheet = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active
    updated_cells = 0
    added_rows = 0

    if new_sheets:
        for s_name in new_sheets:
            if s_name not in wb.sheetnames:
                wb.create_sheet(title=s_name)

    if cell_updates:
        for cu in cell_updates:
            coord = cu.get("cell")  # e.g. "B5" or row/col
            val = cu.get("value")
            target_sheet = wb[cu["sheet"]] if "sheet" in cu and cu["sheet"] in wb.sheetnames else active_sheet
            if coord:
                target_sheet[coord] = val
                updated_cells += 1
            elif "row" in cu and "col" in cu:
                target_sheet.cell(row=cu["row"], column=cu["col"], value=val)
                updated_cells += 1

    if append_rows:
        for row in append_rows:
            active_sheet.append(row)
            added_rows += 1

    wb.save(path)
    return {
        "status": "success",
        "file_name": path.name,
        "updated_cells": updated_cells,
        "added_rows": added_rows,
        "sheet_names": wb.sheetnames,
        "file_size": path.stat().st_size,
    }


def patch_pptx(
    file_path: Path | str,
    *,
    slide_updates: list[dict[str, Any]] | None = None,
    append_slides: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Applies edits to an existing PowerPoint .pptx presentation."""
    if pptx is None:
        raise RuntimeError("python-pptx is not installed")

    path = Path(file_path)
    prs = pptx.Presentation(path)
    updated_slides = 0
    added_slides = 0

    if slide_updates:
        for su in slide_updates:
            idx = su.get("index")
            if idx is not None and 0 <= idx < len(prs.slides):
                slide = prs.slides[idx]
                if "title" in su and slide.shapes.title:
                    slide.shapes.title.text = su["title"]
                if "bullets" in su and len(slide.placeholders) > 1:
                    body = slide.placeholders[1]
                    tf = body.text_frame
                    bullets = su["bullets"]
                    tf.text = ""
                    for i, b in enumerate(bullets):
                        if i == 0:
                            tf.text = b
                        else:
                            p = tf.add_paragraph()
                            p.text = b
                if "notes" in su:
                    slide.notes_slide.notes_text_frame.text = su["notes"]
                updated_slides += 1

    if append_slides:
        content_slide_layout = prs.slide_layouts[1]
        for s_spec in append_slides:
            slide = prs.slides.add_slide(content_slide_layout)
            slide_title = s_spec.get("title", "")
            slide.shapes.title.text = slide_title
            bullets = s_spec.get("bullets", [])
            if bullets and len(slide.placeholders) > 1:
                body = slide.placeholders[1]
                tf = body.text_frame
                for i, b in enumerate(bullets):
                    if i == 0:
                        tf.text = b
                    else:
                        p = tf.add_paragraph()
                        p.text = b
            notes = s_spec.get("notes")
            if notes:
                slide.notes_slide.notes_text_frame.text = notes
            added_slides += 1

    prs.save(path)
    return {
        "status": "success",
        "file_name": path.name,
        "updated_slides": updated_slides,
        "added_slides": added_slides,
        "slide_count": len(prs.slides),
        "file_size": path.stat().st_size,
    }


def create_docx(
    file_path: Path | str,
    *,
    title: str,
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    """Creates a new structured Word .docx document."""
    if docx is None:
        raise RuntimeError("python-docx is not installed")

    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = docx.Document()

    # Title
    doc.add_heading(title, level=0)

    for sec in sections:
        heading = sec.get("heading")
        level = sec.get("level", 1)
        if heading:
            doc.add_heading(heading, level=level)

        paragraphs = sec.get("paragraphs") or sec.get("content")
        if paragraphs:
            if isinstance(paragraphs, str):
                doc.add_paragraph(paragraphs)
            elif isinstance(paragraphs, list):
                for para in paragraphs:
                    doc.add_paragraph(str(para))

        bullets = sec.get("bullets")
        if bullets:
            for b in bullets:
                doc.add_paragraph(str(b), style="List Bullet")

        table_data = sec.get("table")
        if table_data:
            if isinstance(table_data, dict):
                headers = table_data.get("headers", [])
                rows = table_data.get("rows", [])
                table_matrix = ([headers] if headers else []) + list(rows)
            elif isinstance(table_data, list):
                table_matrix = table_data
            else:
                table_matrix = []

            if table_matrix and len(table_matrix) > 0:
                cols = max(len(r) for r in table_matrix)
                table = doc.add_table(rows=len(table_matrix), cols=cols)
                table.style = "Table Grid"
                for r_idx, row in enumerate(table_matrix):
                    for c_idx, val in enumerate(row):
                        if c_idx < cols:
                            cell = table.cell(r_idx, c_idx)
                            cell.text = str(val)
                            if r_idx == 0 and isinstance(table_data, dict) and table_data.get("headers"):
                                for p in cell.paragraphs:
                                    for run in p.runs:
                                        run.bold = True

    doc.save(path)
    return {
        "status": "created",
        "file_name": path.name,
        "format": "docx",
        "file_size": path.stat().st_size,
    }


def create_xlsx(
    file_path: Path | str,
    *,
    sheets: list[dict[str, Any]],
) -> dict[str, Any]:
    """Creates a new structured Excel .xlsx workbook with formatting and formulas."""
    if openpyxl is None:
        raise RuntimeError("openpyxl is not installed")

    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    header_fill = PatternFill(start_color="182027", end_color="182027", fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    cell_font = Font(name="Segoe UI", size=10)
    thin_border = Border(
        left=Side(style="thin", color="DFE4E8"),
        right=Side(style="thin", color="DFE4E8"),
        top=Side(style="thin", color="DFE4E8"),
        bottom=Side(style="thin", color="DFE4E8"),
    )

    for sheet_spec in sheets:
        name = sheet_spec.get("name", "Sheet")
        ws = wb.create_sheet(title=name)
        headers = sheet_spec.get("headers", [])
        rows = sheet_spec.get("rows", [])

        if headers:
            ws.append(headers)
            for col_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=1, column=col_idx)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.border = thin_border

        for row in rows:
            ws.append(row)

        # Apply cell formatting and column auto-width
        for row_idx in range(2 if headers else 1, ws.max_row + 1):
            for col_idx in range(1, ws.max_column + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.font = cell_font
                cell.border = thin_border

        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    wb.save(path)
    return {
        "status": "created",
        "file_name": path.name,
        "format": "xlsx",
        "sheet_count": len(sheets),
        "file_size": path.stat().st_size,
    }


def create_pptx(
    file_path: Path | str,
    *,
    title: str,
    subtitle: str = "",
    slides: list[dict[str, Any]],
) -> dict[str, Any]:
    """Creates a new structured PowerPoint .pptx presentation."""
    if pptx is None:
        raise RuntimeError("python-pptx is not installed")

    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    prs = pptx.Presentation()

    # Title slide
    title_slide_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(title_slide_layout)
    slide.shapes.title.text = title
    if subtitle and len(slide.placeholders) > 1:
        slide.placeholders[1].text = subtitle

    # Content slides
    content_slide_layout = prs.slide_layouts[1]
    for s_spec in slides:
        slide = prs.slides.add_slide(content_slide_layout)
        slide_title = s_spec.get("title", "")
        slide.shapes.title.text = slide_title

        bullets = s_spec.get("bullets", [])
        if bullets and len(slide.placeholders) > 1:
            body = slide.placeholders[1]
            tf = body.text_frame
            for i, b in enumerate(bullets):
                if i == 0:
                    tf.text = b
                else:
                    p = tf.add_paragraph()
                    p.text = b

        notes = s_spec.get("notes")
        if notes:
            slide.notes_slide.notes_text_frame.text = notes

    prs.save(path)
    return {
        "status": "created",
        "file_name": path.name,
        "format": "pptx",
        "slide_count": len(prs.slides),
        "file_size": path.stat().st_size,
    }


def create_document(file_path: Path | str, **kwargs: Any) -> dict[str, Any]:
    """Universal dispatcher to create office documents by extension."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        docx_keys = {"title", "sections"}
        filtered = {k: v for k, v in kwargs.items() if k in docx_keys and v is not None}
        return create_docx(path, **filtered)
    elif suffix in (".xlsx", ".xlsm"):
        xlsx_keys = {"sheets"}
        filtered = {k: v for k, v in kwargs.items() if k in xlsx_keys and v is not None}
        return create_xlsx(path, **filtered)
    elif suffix == ".pptx":
        pptx_keys = {"title", "subtitle", "slides"}
        filtered = {k: v for k, v in kwargs.items() if k in pptx_keys and v is not None}
        return create_pptx(path, **filtered)
    else:
        raise ValueError(f"Unsupported format for creation: {suffix}")


def patch_document(file_path: Path | str, **kwargs: Any) -> dict[str, Any]:
    """Universal dispatcher to patch existing office documents by extension."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        docx_keys = {"paragraph_updates", "append_paragraphs", "table_updates"}
        filtered = {k: v for k, v in kwargs.items() if k in docx_keys and v is not None}
        return patch_docx(path, **filtered)
    elif suffix in (".xlsx", ".xlsm"):
        xlsx_keys = {"sheet_name", "cell_updates", "append_rows", "new_sheets"}
        filtered = {k: v for k, v in kwargs.items() if k in xlsx_keys and v is not None}
        return patch_xlsx(path, **filtered)
    elif suffix == ".pptx":
        pptx_keys = {"slide_updates", "append_slides"}
        filtered = {k: v for k, v in kwargs.items() if k in pptx_keys and v is not None}
        return patch_pptx(path, **filtered)
    else:
        raise ValueError(f"Unsupported format for patching: {suffix}")
