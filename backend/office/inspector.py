"""Deep inspection of office documents (.docx, .xlsx, .pptx, .pdf) for FinControl IDE."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import os
import re

try:
    import docx
except ImportError:
    docx = None

try:
    import openpyxl
except ImportError:
    openpyxl = None

try:
    import pptx
except ImportError:
    pptx = None

try:
    import pymupdf  # fitz
except ImportError:
    pymupdf = None


def inspect_document(file_path: Path | str) -> dict[str, Any]:
    """Inspects any supported office document and returns structured representation."""
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".docx":
        return inspect_docx(path)
    elif suffix in (".xlsx", ".xlsm", ".xltx"):
        return inspect_xlsx(path)
    elif suffix == ".pptx":
        return inspect_pptx(path)
    elif suffix == ".pdf":
        return inspect_pdf(path)
    elif suffix in (".md", ".markdown"):
        return inspect_markdown(path)
    elif suffix in (".html", ".htm"):
        return inspect_html(path)
    elif suffix in (".csv", ".tsv"):
        return inspect_csv(path)
    else:
        raise ValueError(f"Unsupported office document format: {suffix}")


def inspect_docx(path: Path) -> dict[str, Any]:
    """Inspects a Word .docx document, extracting paragraphs, headings, and tables."""
    if docx is None:
        raise RuntimeError("python-docx is not installed")

    doc = docx.Document(path)
    paragraphs_data: list[dict[str, Any]] = []
    headings: list[dict[str, Any]] = []
    tables_data: list[dict[str, Any]] = []
    total_words = 0

    for i, p in enumerate(doc.paragraphs):
        text = p.text.strip()
        if not text:
            continue
        words = len(text.split())
        total_words += words
        style_name = p.style.name if p.style else "Normal"
        style_lower = style_name.lower()
        is_heading = style_lower.startswith("heading") or style_lower == "title"
        level = 0 if style_lower == "title" else 1
        if is_heading and style_lower != "title":
            digits = re.findall(r"\d+", style_name)
            level = int(digits[0]) if digits else 1
        if is_heading:
            headings.append({"index": i, "level": level, "text": text})

        paragraphs_data.append({
            "index": i,
            "style": style_name,
            "text": text,
            "is_heading": is_heading,
            "level": level if is_heading else None,
        })

    for t_idx, table in enumerate(doc.tables):
        rows: list[list[str]] = []
        for row in table.rows:
            rows.append([cell.text.strip() for cell in row.cells])
        tables_data.append({
            "index": t_idx,
            "row_count": len(rows),
            "col_count": len(rows[0]) if rows else 0,
            "rows": rows[:100],  # bounded sample
        })

    return {
        "format": "docx",
        "file_name": path.name,
        "file_size": path.stat().st_size,
        "paragraph_count": len(paragraphs_data),
        "total_words": total_words,
        "headings": headings,
        "paragraphs": paragraphs_data,
        "tables": tables_data,
    }


def inspect_xlsx(path: Path) -> dict[str, Any]:
    """Inspects an Excel .xlsx workbook, extracting sheets, formulas, dimensions, and rows."""
    if openpyxl is None:
        raise RuntimeError("openpyxl is not installed")

    wb = openpyxl.load_workbook(path, data_only=False, read_only=False)
    sheets_data: list[dict[str, Any]] = []
    total_formulas = 0

    for name in wb.sheetnames:
        sheet = wb[name]
        max_row = min(sheet.max_row or 0, 500)
        max_col = min(sheet.max_column or 0, 50)
        formulas_in_sheet: list[dict[str, str]] = []
        rows: list[list[Any]] = []

        for r in range(1, max_row + 1):
            row_vals: list[Any] = []
            for c in range(1, max_col + 1):
                cell = sheet.cell(row=r, column=c)
                val = cell.value
                val_str = str(val) if val is not None else ""
                if isinstance(val, str) and val.startswith("="):
                    formulas_in_sheet.append({"cell": cell.coordinate, "formula": val})
                    total_formulas += 1
                row_vals.append(val_str)
            if any(row_vals):
                rows.append(row_vals)

        sheets_data.append({
            "name": name,
            "max_row": sheet.max_row,
            "max_column": sheet.max_column,
            "formula_count": len(formulas_in_sheet),
            "sample_formulas": formulas_in_sheet[:20],
            "rows": rows[:100],  # first 100 rows for preview
            "headers": rows[0] if rows else [],
        })

    return {
        "format": "xlsx",
        "file_name": path.name,
        "file_size": path.stat().st_size,
        "sheet_names": wb.sheetnames,
        "sheet_count": len(wb.sheetnames),
        "total_formulas": total_formulas,
        "sheets": sheets_data,
        "sheets_by_name": {s["name"]: s for s in sheets_data},
    }


def inspect_pptx(path: Path) -> dict[str, Any]:
    """Inspects a PowerPoint .pptx presentation, extracting slides, titles, shapes, and notes."""
    if pptx is None:
        raise RuntimeError("python-pptx is not installed")

    prs = pptx.Presentation(path)
    slides_data: list[dict[str, Any]] = []

    for s_idx, slide in enumerate(prs.slides):
        title = ""
        paragraphs: list[str] = []
        shapes_info: list[dict[str, Any]] = []

        for shape in slide.shapes:
            if shape.has_text_frame:
                text = shape.text.strip()
                if not text:
                    continue
                if not title and (shape == slide.shapes[0] or "title" in shape.name.lower()):
                    title = text
                else:
                    paragraphs.append(text)
            shapes_info.append({
                "name": shape.name,
                "shape_type": str(shape.shape_type),
            })

        notes = ""
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
            notes = slide.notes_slide.notes_text_frame.text.strip()

        bullets = [line.strip() for p in paragraphs for line in p.splitlines() if line.strip()]
        slides_data.append({
            "index": s_idx,
            "title": title or f"Slide {s_idx + 1}",
            "paragraphs": paragraphs,
            "bullets": bullets,
            "shape_count": len(slide.shapes),
            "notes": notes,
        })

    return {
        "format": "pptx",
        "file_name": path.name,
        "file_size": path.stat().st_size,
        "slide_count": len(slides_data),
        "slides": slides_data,
    }


def inspect_pdf(path: Path) -> dict[str, Any]:
    """Inspects a PDF document, extracting page count, text samples, and dimensions."""
    if pymupdf is None:
        raise RuntimeError("pymupdf is not installed")

    doc = pymupdf.open(path)
    pages_data: list[dict[str, Any]] = []
    total_words = 0

    for p_idx, page in enumerate(doc):
        text = page.get_text().strip()
        words = len(text.split())
        total_words += words
        rect = page.rect
        pages_data.append({
            "page_number": p_idx + 1,
            "width": rect.width,
            "height": rect.height,
            "word_count": words,
            "text_snippet": text[:400] if text else "",
        })

    return {
        "format": "pdf",
        "file_name": path.name,
        "file_size": path.stat().st_size,
        "page_count": len(doc),
        "total_words": total_words,
        "pages": pages_data,
    }


def inspect_markdown(path: Path) -> dict[str, Any]:
    """Inspects a Markdown file, extracting headings, code blocks, and lines."""
    content = path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()
    headings: list[dict[str, Any]] = []
    code_blocks = 0
    in_code = False

    for i, line in enumerate(lines):
        if line.startswith("```"):
            in_code = not in_code
            if in_code:
                code_blocks += 1
            continue
        if not in_code and line.startswith("#"):
            match = re.match(r"^(#{1,6})\s+(.*)$", line)
            if match:
                headings.append({"index": i, "level": len(match.group(1)), "text": match.group(2).strip()})

    return {
        "format": "md",
        "file_name": path.name,
        "file_size": path.stat().st_size,
        "line_count": len(lines),
        "total_words": len(content.split()),
        "headings": headings,
        "code_blocks": code_blocks,
        "content": content[:50_000],  # bounded sample
    }


def inspect_html(path: Path) -> dict[str, Any]:
    """Inspects an HTML file, extracting title, headings, and character length."""
    content = path.read_text(encoding="utf-8", errors="replace")
    title_match = re.search(r"<title>(.*?)</title>", content, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else ""
    headings = re.findall(r"<(h[1-6])[^>]*>(.*?)</\1>", content, re.IGNORECASE | re.DOTALL)
    cleaned_headings = [{"level": int(tag[1]), "text": re.sub(r"<[^>]+>", "", text).strip()} for tag, text in headings]

    return {
        "format": "html",
        "file_name": path.name,
        "file_size": path.stat().st_size,
        "title": title,
        "headings": cleaned_headings,
        "content_length": len(content),
        "content": content[:50_000],
    }


def inspect_csv(path: Path) -> dict[str, Any]:
    """Inspects a CSV / TSV file, returning delimiter, headers, and rows."""
    import csv
    content = path.read_text(encoding="utf-8", errors="replace")
    delimiter = "\t" if path.suffix.lower() == ".tsv" or "\t" in content[:1000] else ","
    reader = csv.reader(content.splitlines(), delimiter=delimiter)
    rows = list(reader)

    return {
        "format": "csv",
        "file_name": path.name,
        "file_size": path.stat().st_size,
        "row_count": len(rows),
        "headers": rows[0] if rows else [],
        "rows": rows[:100],
    }
