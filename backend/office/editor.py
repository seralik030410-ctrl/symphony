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
    from openpyxl.utils.cell import range_boundaries, coordinate_to_tuple
    from openpyxl.chart import BarChart, LineChart, PieChart, AreaChart, Reference
except ImportError:
    openpyxl = None
    BarChart = None
    LineChart = None
    PieChart = None
    AreaChart = None
    Reference = None

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
    style_updates: list[dict[str, Any]] | None = None,
    fill_ranges: list[dict[str, Any]] | None = None,
    sort_operations: list[dict[str, Any]] | None = None,
    row_operations: list[dict[str, Any]] | None = None,
    col_operations: list[dict[str, Any]] | None = None,
    charts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Applies surgical cell, formula, style, structure, and chart edits to an existing Excel .xlsx file."""
    if openpyxl is None:
        raise RuntimeError("openpyxl is not installed")

    path = Path(file_path)
    wb = openpyxl.load_workbook(path)
    active_sheet = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active
    updated_cells = 0
    added_rows = 0
    styled_cells = 0
    filled_cells = 0
    added_charts = 0

    if new_sheets:
        for s_name in new_sheets:
            if s_name not in wb.sheetnames:
                wb.create_sheet(title=s_name)

    # Structural operations: row & column insert / delete
    if row_operations:
        for rop in row_operations:
            target_sheet = wb[rop["sheet"]] if "sheet" in rop and rop["sheet"] in wb.sheetnames else active_sheet
            op = rop.get("op", "insert")
            idx = rop.get("index", 1)
            amt = rop.get("amount", 1)
            if op == "insert":
                target_sheet.insert_rows(idx, amt)
            elif op == "delete":
                target_sheet.delete_rows(idx, amt)

    if col_operations:
        for cop in col_operations:
            target_sheet = wb[cop["sheet"]] if "sheet" in cop and cop["sheet"] in wb.sheetnames else active_sheet
            op = cop.get("op", "insert")
            idx = cop.get("index", 1)
            amt = cop.get("amount", 1)
            if op == "insert":
                target_sheet.insert_cols(idx, amt)
            elif op == "delete":
                target_sheet.delete_cols(idx, amt)

    # Cell updates
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

    # Fill ranges with formula templates or sequences
    if fill_ranges:
        for fr in fill_ranges:
            target_sheet = wb[fr["sheet"]] if "sheet" in fr and fr["sheet"] in wb.sheetnames else active_sheet
            start_cell = fr.get("start_cell") or fr.get("start", "A1")
            end_cell = fr.get("end_cell") or fr.get("end", start_cell)
            formula_tpl = fr.get("formula", "")
            seq_start = fr.get("sequence_start")
            seq_step = fr.get("sequence_step", 1)

            min_c, min_r, max_c, max_r = range_boundaries(f"{start_cell}:{end_cell}")
            curr_val = seq_start
            for r in range(min_r, max_r + 1):
                for c in range(min_c, max_c + 1):
                    if formula_tpl:
                        c_letter = get_column_letter(c)
                        rendered = formula_tpl.format(row=r, col=c, col_letter=c_letter)
                        target_sheet.cell(row=r, column=c, value=rendered)
                        filled_cells += 1
                    elif curr_val is not None:
                        target_sheet.cell(row=r, column=c, value=curr_val)
                        curr_val += seq_step
                        filled_cells += 1

    # Cell styling updates
    if style_updates:
        for su in style_updates:
            target_sheet = wb[su["sheet"]] if "sheet" in su and su["sheet"] in wb.sheetnames else active_sheet
            cells_to_style: list[openpyxl.cell.Cell] = []
            if "cell" in su:
                cells_to_style.append(target_sheet[su["cell"]])
            elif "range" in su:
                min_c, min_r, max_c, max_r = range_boundaries(su["range"])
                for r in range(min_r, max_r + 1):
                    for c in range(min_c, max_c + 1):
                        cells_to_style.append(target_sheet.cell(row=r, column=c))
            elif "row" in su and "col" in su:
                cells_to_style.append(target_sheet.cell(row=su["row"], column=su["col"]))

            for cell in cells_to_style:
                # Font updates
                font_kwargs: dict[str, Any] = {}
                if "bold" in su:
                    font_kwargs["bold"] = bool(su["bold"])
                if "italic" in su:
                    font_kwargs["italic"] = bool(su["italic"])
                if "color" in su:
                    c_val = str(su["color"]).lstrip("#").upper()
                    font_kwargs["color"] = c_val
                if font_kwargs:
                    cell.font = Font(**font_kwargs)

                # Background fill
                if "bg_color" in su:
                    bg_val = str(su["bg_color"]).lstrip("#").upper()
                    cell.fill = PatternFill(start_color=bg_val, end_color=bg_val, fill_type="solid")

                # Alignment
                if "align" in su:
                    cell.alignment = Alignment(horizontal=su["align"], vertical="center")

                # Number format
                if "number_format" in su:
                    cell.number_format = str(su["number_format"])

                styled_cells += 1

    # Sorting
    if sort_operations:
        for so in sort_operations:
            target_sheet = wb[so["sheet"]] if "sheet" in so and so["sheet"] in wb.sheetnames else active_sheet
            by_col = so.get("column", 1)
            ascending = so.get("ascending", True)
            has_headers = so.get("has_headers", True)
            col_idx = int(by_col) if isinstance(by_col, int) else (openpyxl.utils.column_index_from_string(by_col) if by_col.isalpha() else 1)

            all_rows = list(target_sheet.iter_rows(values_only=False))
            if len(all_rows) > (1 if has_headers else 0):
                header_row = all_rows[0] if has_headers else None
                body_rows = all_rows[1:] if has_headers else all_rows

                def get_sort_val(row_cells: Any) -> Any:
                    if col_idx - 1 < len(row_cells):
                        v = row_cells[col_idx - 1].value
                        return (0, float(v)) if isinstance(v, (int, float)) else (1, str(v or ""))
                    return (2, "")

                # Store row values
                extracted = [[c.value for c in r] for r in body_rows]
                extracted.sort(key=lambda r: (0, float(r[col_idx - 1])) if col_idx - 1 < len(r) and isinstance(r[col_idx - 1], (int, float)) else (1, str(r[col_idx - 1] or "")), reverse=not ascending)

                start_r = 2 if has_headers else 1
                for r_idx, r_vals in enumerate(extracted, start=start_r):
                    for c_idx, val in enumerate(r_vals, start=1):
                        target_sheet.cell(row=r_idx, column=c_idx, value=val)

    # Charts
    if charts and BarChart is not None:
        for ch in charts:
            target_sheet = wb[ch["sheet"]] if "sheet" in ch and ch["sheet"] in wb.sheetnames else active_sheet
            c_type = ch.get("chart_type", "bar").lower()
            d_range = ch.get("data_range", "")
            cats_range = ch.get("categories_range")
            title = ch.get("title", "")
            tgt_cell = ch.get("target_cell", "E2")

            if c_type == "line":
                chart_obj = LineChart()
            elif c_type == "pie":
                chart_obj = PieChart()
            elif c_type == "area":
                chart_obj = AreaChart()
            else:
                chart_obj = BarChart()

            chart_obj.title = title
            if d_range:
                min_c, min_r, max_c, max_r = range_boundaries(d_range)
                data_ref = Reference(target_sheet, min_col=min_c, min_row=min_r, max_col=max_c, max_row=max_r)
                chart_obj.add_data(data_ref, titles_from_data=True)

            if cats_range:
                c_min_c, c_min_r, c_max_c, c_max_r = range_boundaries(cats_range)
                cats_ref = Reference(target_sheet, min_col=c_min_c, min_row=c_min_r, max_col=c_max_c, max_row=c_max_r)
                chart_obj.set_categories(cats_ref)

            target_sheet.add_chart(chart_obj, tgt_cell)
            added_charts += 1

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
        "styled_cells": styled_cells,
        "filled_cells": filled_cells,
        "added_charts": added_charts,
        "sheet_names": wb.sheetnames,
        "file_size": path.stat().st_size,
    }


def add_chart_to_xlsx(
    file_path: Path | str,
    *,
    sheet_name: str | None = None,
    chart_type: str = "bar",
    data_range: str = "",
    categories_range: str | None = None,
    title: str = "",
    target_cell: str = "E2",
) -> dict[str, Any]:
    """Adds a native Excel chart (bar, line, pie, area) to an existing .xlsx file."""
    return patch_xlsx(
        file_path,
        sheet_name=sheet_name,
        charts=[{
            "chart_type": chart_type,
            "data_range": data_range,
            "categories_range": categories_range,
            "title": title,
            "target_cell": target_cell,
        }],
    )


def fill_range_xlsx(
    file_path: Path | str,
    *,
    sheet_name: str | None = None,
    start_cell: str = "A1",
    end_cell: str = "A1",
    formula_template: str = "",
) -> dict[str, Any]:
    """Fills a range with a formula template (e.g. '=A{row}*B{row}') or values."""
    return patch_xlsx(
        file_path,
        sheet_name=sheet_name,
        fill_ranges=[{
            "start_cell": start_cell,
            "end_cell": end_cell,
            "formula": formula_template,
        }],
    )


def sort_xlsx(
    file_path: Path | str,
    *,
    sheet_name: str | None = None,
    by_column: int | str = 1,
    ascending: bool = True,
    has_headers: bool = True,
) -> dict[str, Any]:
    """Sorts sheet data by a given column index or column letter."""
    return patch_xlsx(
        file_path,
        sheet_name=sheet_name,
        sort_operations=[{
            "column": by_column,
            "ascending": ascending,
            "has_headers": has_headers,
        }],
    )


def modify_structure_xlsx(
    file_path: Path | str,
    *,
    sheet_name: str | None = None,
    insert_row: int | None = None,
    delete_row: int | None = None,
    insert_col: int | None = None,
    delete_col: int | None = None,
) -> dict[str, Any]:
    """Inserts or deletes rows and columns in an Excel sheet."""
    row_ops: list[dict[str, Any]] = []
    col_ops: list[dict[str, Any]] = []

    if insert_row is not None:
        row_ops.append({"op": "insert", "index": insert_row, "amount": 1})
    if delete_row is not None:
        row_ops.append({"op": "delete", "index": delete_row, "amount": 1})
    if insert_col is not None:
        col_ops.append({"op": "insert", "index": insert_col, "amount": 1})
    if delete_col is not None:
        col_ops.append({"op": "delete", "index": delete_col, "amount": 1})

    return patch_xlsx(
        file_path,
        sheet_name=sheet_name,
        row_operations=row_ops if row_ops else None,
        col_operations=col_ops if col_ops else None,
    )


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
        xlsx_keys = {
            "sheet_name", "cell_updates", "append_rows", "new_sheets",
            "style_updates", "fill_ranges", "sort_operations",
            "row_operations", "col_operations", "charts",
        }
        filtered = {k: v for k, v in kwargs.items() if k in xlsx_keys and v is not None}
        return patch_xlsx(path, **filtered)
    elif suffix == ".pptx":
        pptx_keys = {"slide_updates", "append_slides"}
        filtered = {k: v for k, v in kwargs.items() if k in pptx_keys and v is not None}
        return patch_pptx(path, **filtered)
    else:
        raise ValueError(f"Unsupported format for patching: {suffix}")
