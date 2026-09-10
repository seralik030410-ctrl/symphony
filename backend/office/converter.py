"""Document conversion utilities between Markdown, HTML, PDF, DOCX, XLSX, and CSV."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import re
from html.parser import HTMLParser

try:
    import docx
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
except ImportError:
    docx = None

try:
    import pymupdf
except ImportError:
    pymupdf = None

try:
    import openpyxl
except ImportError:
    openpyxl = None


def parse_inline_markdown(paragraph, text: str) -> None:
    """Adds styled runs to a docx paragraph parsing basic markdown (**bold**, *italic*, `code`)."""
    pattern = re.compile(r'(\*\*.*?\*\*|\*.*?\*|`.*?`)')
    parts = pattern.split(text)
    for part in parts:
        if not part:
            continue
        if part.startswith('**') and part.endswith('**') and len(part) >= 4:
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        elif part.startswith('*') and part.endswith('*') and len(part) >= 2:
            run = paragraph.add_run(part[1:-1])
            run.italic = True
        elif part.startswith('`') and part.endswith('`') and len(part) >= 2:
            run = paragraph.add_run(part[1:-1])
            run.font.name = 'Consolas'
            run.font.size = Pt(9.5)
            run.font.color.rgb = RGBColor(0x33, 0x33, 0x88)
        else:
            paragraph.add_run(part)


def markdown_to_docx(md_content: str, output_path: Path | str, title: str | None = None) -> Path:
    """Converts markdown text to a formatted DOCX document."""
    if docx is None:
        raise RuntimeError("python-docx is not installed")

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    doc = docx.Document()

    if title:
        p = doc.add_heading(title, level=0)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    lines = md_content.splitlines()
    in_code_block = False
    code_block_lines: list[str] = []
    in_table = False
    table_rows: list[list[str]] = []

    def flush_table():
        nonlocal in_table, table_rows
        if not table_rows:
            in_table = False
            return
        # Filter out separator lines (|---|---|)
        data_rows = [r for r in table_rows if not all(re.match(r'^:?-+:?$', c.strip()) for c in r if c.strip())]
        if data_rows:
            num_cols = max(len(r) for r in data_rows)
            t = doc.add_table(rows=len(data_rows), cols=num_cols)
            t.style = 'Table Grid'
            for r_idx, row in enumerate(data_rows):
                for c_idx, cell_value in enumerate(row):
                    if c_idx < num_cols:
                        cell = t.cell(r_idx, c_idx)
                        cell.text = cell_value.strip()
                        if r_idx == 0:
                            # Header styling
                            for p in cell.paragraphs:
                                for run in p.runs:
                                    run.bold = True
        table_rows = []
        in_table = False

    for line in lines:
        stripped = line.strip()

        # Code block handling
        if stripped.startswith('```'):
            if in_code_block:
                code_text = "\n".join(code_block_lines)
                p = doc.add_paragraph()
                run = p.add_run(code_text)
                run.font.name = 'Consolas'
                run.font.size = Pt(9)
                run.font.color.rgb = RGBColor(0x22, 0x22, 0x22)
                code_block_lines = []
                in_code_block = False
            else:
                if in_table:
                    flush_table()
                in_code_block = True
                code_block_lines = []
            continue

        if in_code_block:
            code_block_lines.append(line)
            continue

        # Table row handling (| cell | cell |)
        if stripped.startswith('|') and stripped.endswith('|'):
            cells = [c.strip() for c in stripped[1:-1].split('|')]
            table_rows.append(cells)
            in_table = True
            continue
        elif in_table:
            flush_table()

        if not stripped:
            continue

        # Headings
        if stripped.startswith('# '):
            doc.add_heading(stripped[2:], level=1)
        elif stripped.startswith('## '):
            doc.add_heading(stripped[3:], level=2)
        elif stripped.startswith('### '):
            doc.add_heading(stripped[4:], level=3)
        elif stripped.startswith('#### '):
            doc.add_heading(stripped[5:], level=4)
        # Bullet list
        elif stripped.startswith(('- ', '* ')):
            p = doc.add_paragraph(style='List Bullet')
            parse_inline_markdown(p, stripped[2:])
        # Numbered list
        elif re.match(r'^\d+\.\s', stripped):
            num_match = re.match(r'^\d+\.\s', stripped)
            text_part = stripped[num_match.end():]
            p = doc.add_paragraph(style='List Number')
            parse_inline_markdown(p, text_part)
        # Blockquote
        elif stripped.startswith('> '):
            p = doc.add_paragraph(style='Quote')
            parse_inline_markdown(p, stripped[2:])
        else:
            p = doc.add_paragraph()
            parse_inline_markdown(p, stripped)

    if in_table:
        flush_table()

    doc.save(str(out_file))
    return out_file


def docx_to_markdown(docx_path: Path | str) -> str:
    """Extracts content from a DOCX file and formats as Markdown."""
    if docx is None:
        raise RuntimeError("python-docx is not installed")

    path = Path(docx_path)
    if not path.exists():
        raise FileNotFoundError(f"DOCX file not found: {path}")

    doc = docx.Document(path)
    output_lines: list[str] = []

    for element in doc.element.body:
        tag = element.tag.split('}')[-1]
        if tag == 'p':
            for p in doc.paragraphs:
                if p._element is element:
                    text = p.text.strip()
                    if not text:
                        continue
                    style_name = p.style.name.lower() if p.style else ""
                    if "heading 1" in style_name:
                        output_lines.append(f"# {text}\n")
                    elif "heading 2" in style_name:
                        output_lines.append(f"## {text}\n")
                    elif "heading 3" in style_name:
                        output_lines.append(f"### {text}\n")
                    elif "heading 4" in style_name:
                        output_lines.append(f"#### {text}\n")
                    elif "bullet" in style_name:
                        output_lines.append(f"- {text}")
                    elif "number" in style_name:
                        output_lines.append(f"1. {text}")
                    elif "quote" in style_name:
                        output_lines.append(f"> {text}\n")
                    else:
                        output_lines.append(f"{text}\n")
                    break
        elif tag == 'tbl':
            for t in doc.tables:
                if t._element is element:
                    rows = []
                    for row in t.rows:
                        rows.append([cell.text.strip().replace("\n", " ") for cell in row.cells])
                    if rows:
                        header = rows[0]
                        output_lines.append("| " + " | ".join(header) + " |")
                        output_lines.append("| " + " | ".join(["---"] * len(header)) + " |")
                        for r in rows[1:]:
                            output_lines.append("| " + " | ".join(r) + " |")
                        output_lines.append("")
                    break

    return "\n".join(output_lines)


class SimpleHTMLToDocxParser(HTMLParser):
    def __init__(self, doc):
        super().__init__()
        self.doc = doc
        self.current_tag = None
        self.current_paragraph = None
        self.in_table = False
        self.current_table = None
        self.current_row = None
        self.current_cell = None
        self.tag_stack = []

    def handle_starttag(self, tag, attrs):
        self.tag_stack.append(tag)
        tag_lower = tag.lower()
        if tag_lower in ('h1', 'h2', 'h3', 'h4'):
            level = int(tag_lower[1])
            self.current_paragraph = self.doc.add_heading(level=level)
        elif tag_lower == 'p':
            self.current_paragraph = self.doc.add_paragraph()
        elif tag_lower == 'li':
            self.current_paragraph = self.doc.add_paragraph(style='List Bullet')
        elif tag_lower == 'table':
            self.in_table = True
            self.current_table = []
        elif tag_lower == 'tr' and self.in_table:
            self.current_row = []
        elif tag_lower in ('td', 'th') and self.in_table:
            self.current_cell = []

    def handle_endtag(self, tag):
        if self.tag_stack and self.tag_stack[-1] == tag:
            self.tag_stack.pop()
        tag_lower = tag.lower()
        if tag_lower in ('h1', 'h2', 'h3', 'h4', 'p', 'li'):
            self.current_paragraph = None
        elif tag_lower in ('td', 'th') and self.in_table:
            if self.current_row is not None and self.current_cell is not None:
                self.current_row.append(" ".join(self.current_cell).strip())
            self.current_cell = None
        elif tag_lower == 'tr' and self.in_table:
            if self.current_table is not None and self.current_row is not None:
                self.current_table.append(self.current_row)
            self.current_row = None
        elif tag_lower == 'table' and self.in_table:
            if self.current_table:
                num_cols = max(len(r) for r in self.current_table)
                t = self.doc.add_table(rows=len(self.current_table), cols=num_cols)
                t.style = 'Table Grid'
                for r_idx, row in enumerate(self.current_table):
                    for c_idx, val in enumerate(row):
                        if c_idx < num_cols:
                            t.cell(r_idx, c_idx).text = val
            self.in_table = False
            self.current_table = None

    def handle_data(self, data):
        cleaned = data.strip()
        if not cleaned:
            return
        if self.in_table and self.current_cell is not None:
            self.current_cell.append(cleaned)
        elif self.current_paragraph is not None:
            run = self.current_paragraph.add_run(cleaned)
            if 'b' in self.tag_stack or 'strong' in self.tag_stack:
                run.bold = True
            if 'i' in self.tag_stack or 'em' in self.tag_stack:
                run.italic = True
        else:
            p = self.doc.add_paragraph()
            run = p.add_run(cleaned)


def html_to_docx(html_content: str, output_path: Path | str) -> Path:
    """Converts HTML text to a DOCX document."""
    if docx is None:
        raise RuntimeError("python-docx is not installed")

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    doc = docx.Document()
    parser = SimpleHTMLToDocxParser(doc)
    parser.feed(html_content)
    doc.save(str(out_file))
    return out_file


def pdf_to_docx(pdf_path: Path | str, output_path: Path | str) -> Path:
    """Extracts structured text from a PDF and creates a matching DOCX document."""
    if pymupdf is None:
        raise RuntimeError("pymupdf (fitz) is not installed")
    if docx is None:
        raise RuntimeError("python-docx is not installed")

    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_file}")

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    pdf_doc = pymupdf.open(str(pdf_file))
    word_doc = docx.Document()

    for page_num in range(len(pdf_doc)):
        page = pdf_doc[page_num]
        blocks = page.get_text("blocks")
        if page_num > 0:
            word_doc.add_page_break()

        for b in blocks:
            text = b[4].strip()
            if not text:
                continue
            # Simple heuristic: single short line in uppercase or bold-like font could be a heading
            if len(text.splitlines()) == 1 and len(text) < 60 and not text.endswith('.'):
                word_doc.add_heading(text, level=2)
            else:
                p = word_doc.add_paragraph()
                p.add_run(text)

    pdf_doc.close()
    word_doc.save(str(out_file))
    return out_file


def csv_to_xlsx(csv_path: Path | str, output_path: Path | str) -> Path:
    """Converts a CSV file to an Excel workbook with styled headers."""
    if openpyxl is None:
        raise RuntimeError("openpyxl is not installed")

    import csv
    src = Path(csv_path)
    dst = Path(output_path)
    dst.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = src.stem[:31]

    with open(src, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        for r_idx, row in enumerate(reader, start=1):
            for c_idx, val in enumerate(row, start=1):
                # Auto-detect numbers
                parsed_val: Any = val
                try:
                    if "." in val:
                        parsed_val = float(val)
                    else:
                        parsed_val = int(val)
                except ValueError:
                    pass
                cell = ws.cell(row=r_idx, column=c_idx, value=parsed_val)
                if r_idx == 1:
                    cell.font = openpyxl.styles.Font(bold=True)
                    cell.fill = openpyxl.styles.PatternFill(start_color="E0E7FF", end_color="E0E7FF", fill_type="solid")

    wb.save(str(dst))
    return dst


def xlsx_to_csv(xlsx_path: Path | str, output_path: Path | str, sheet_name: str | None = None) -> Path:
    """Converts an Excel sheet to a CSV file."""
    if openpyxl is None:
        raise RuntimeError("openpyxl is not installed")

    import csv
    src = Path(xlsx_path)
    dst = Path(output_path)
    dst.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.load_workbook(str(src), data_only=True)
    ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active

    with open(dst, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        for row in ws.iter_rows(values_only=True):
            if any(cell is not None for cell in row):
                writer.writerow([cell if cell is not None else "" for cell in row])

    return dst
