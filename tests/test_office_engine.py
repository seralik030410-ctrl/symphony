"""Unit tests for the backend Office engine (docx, xlsx, pptx, converter)."""
from __future__ import annotations

from pathlib import Path
import pytest

from backend.office.editor import (
    create_docx,
    create_xlsx,
    create_pptx,
    patch_docx,
    patch_xlsx,
    patch_pptx,
)
from backend.office.inspector import (
    inspect_docx,
    inspect_xlsx,
    inspect_pptx,
    inspect_document,
)
from backend.office.converter import (
    markdown_to_docx,
    docx_to_markdown,
    csv_to_xlsx,
    xlsx_to_csv,
)


def test_docx_create_inspect_patch(tmp_path: Path):
    doc_path = tmp_path / "test_doc.docx"

    # 1. Create DOCX
    create_res = create_docx(
        doc_path,
        title="Quarterly Financial Report",
        sections=[
            {
                "heading": "Executive Summary",
                "level": 1,
                "paragraphs": ["Revenue grew by 24% YoY.", "Gross margins expanded by 180 bps."],
                "table": {
                    "headers": ["Metric", "Q1 Actual", "Q1 Budget"],
                    "rows": [
                        ["Revenue", "$12.4M", "$11.8M"],
                        ["Net Income", "$2.1M", "$1.9M"],
                    ],
                },
            }
        ],
    )
    assert create_res["status"] == "created"
    assert doc_path.exists()

    # 2. Inspect DOCX
    info = inspect_docx(doc_path)
    assert info["format"] == "docx"
    assert "Quarterly Financial Report" in [h["text"] for h in info["headings"]]
    assert len(info["tables"]) == 1
    assert info["tables"][0]["rows"][0] == ["Metric", "Q1 Actual", "Q1 Budget"]

    # 3. Patch DOCX
    patch_res = patch_docx(
        doc_path,
        paragraph_updates=[
            {"index": 1, "text": "Revenue grew by 28% YoY after restatement."}
        ],
        table_updates=[
            {"table_index": 0, "row": 1, "col": 1, "text": "$13.1M"}
        ],
        append_paragraphs=[
            {"text": "Conclusion: Outperformed targets across all regions.", "style": "Normal"}
        ],
    )
    assert patch_res["status"] == "success"
    assert patch_res["modified_paragraphs"] >= 1

    # Re-inspect to verify patch
    updated_info = inspect_docx(doc_path)
    assert updated_info["tables"][0]["rows"][1][1] == "$13.1M"
    all_text = " ".join(p["text"] for p in updated_info["paragraphs"])
    assert "Revenue grew by 28% YoY" in all_text
    assert "Conclusion: Outperformed targets" in all_text


def test_xlsx_create_inspect_patch(tmp_path: Path):
    xlsx_path = tmp_path / "financial_model.xlsx"

    # 1. Create XLSX
    create_res = create_xlsx(
        xlsx_path,
        sheets=[
            {
                "name": "P&L",
                "headers": ["Item", "2025", "2026", "Growth"],
                "rows": [
                    ["Revenue", 1000, 1250, "=C2/B2-1"],
                    ["COGS", 400, 480, "=C3/B3-1"],
                    ["Gross Profit", "=B2-B3", "=C2-C3", "=C4/B4-1"],
                ],
            },
            {
                "name": "Headcount",
                "headers": ["Department", "FTEs"],
                "rows": [
                    ["Engineering", 45],
                    ["Sales", 30],
                ],
            },
        ],
    )
    assert create_res["status"] == "created"
    assert xlsx_path.exists()

    # 2. Inspect XLSX
    info = inspect_xlsx(xlsx_path)
    assert info["format"] == "xlsx"
    assert "P&L" in info["sheets_by_name"]
    assert "Headcount" in info["sheets_by_name"]
    p_and_l = info["sheets_by_name"]["P&L"]
    assert p_and_l["max_row"] == 4
    assert p_and_l["max_column"] == 4

    # 3. Patch XLSX
    patch_res = patch_xlsx(
        xlsx_path,
        sheet_name="P&L",
        cell_updates=[
            {"cell": "C2", "value": 1300},
        ],
        append_rows=[
            ["Operating Expenses", 300, 350, "=C5/B5-1"],
        ],
        new_sheets=["Assumptions"],
    )
    assert patch_res["status"] == "success"
    assert patch_res["updated_cells"] == 1
    assert patch_res["added_rows"] == 1
    assert "Assumptions" in patch_res["sheet_names"]

    # Re-inspect to verify patch
    updated_info = inspect_xlsx(xlsx_path)
    assert updated_info["sheets_by_name"]["P&L"]["rows"][1][2] == "1300" or updated_info["sheets_by_name"]["P&L"]["rows"][1][2] == 1300
    assert "Assumptions" in updated_info["sheets_by_name"]


def test_pptx_create_inspect_patch(tmp_path: Path):
    pptx_path = tmp_path / "deck.pptx"

    # 1. Create PPTX
    create_res = create_pptx(
        pptx_path,
        title="Series A Pitch Deck",
        subtitle="Transforming AI Orchestration",
        slides=[
            {
                "title": "Problem",
                "bullets": [
                    "Manual document preparation is slow and error-prone.",
                    "Siloed applications make collaboration tedious.",
                ],
                "notes": "Speaker note: emphasize the 40% time spent on reporting.",
            },
            {
                "title": "Solution: FinControl IDE",
                "bullets": [
                    "Native deep office engine integrated into workspace.",
                    "AI agent with surgical document editing capabilities.",
                ],
            },
        ],
    )
    assert create_res["status"] == "created"
    assert pptx_path.exists()

    # 2. Inspect PPTX
    info = inspect_pptx(pptx_path)
    assert info["format"] == "pptx"
    assert info["slide_count"] == 3  # Title slide + 2 content slides
    assert info["slides"][1]["title"] == "Problem"
    assert len(info["slides"][1]["bullets"]) == 2
    assert "emphasize the 40%" in info["slides"][1]["notes"]

    # 3. Patch PPTX
    patch_res = patch_pptx(
        pptx_path,
        slide_updates=[
            {
                "index": 1,
                "title": "The Core Problem",
                "bullets": ["Enterprises lose billions on clerical document overhead."],
            }
        ],
        append_slides=[
            {
                "title": "Market Size",
                "bullets": ["$45B TAM in enterprise productivity software."],
            }
        ],
    )
    assert patch_res["status"] == "success"
    assert patch_res["updated_slides"] == 1
    assert patch_res["added_slides"] == 1

    # Re-inspect to verify
    updated_info = inspect_pptx(pptx_path)
    assert updated_info["slide_count"] == 4
    assert updated_info["slides"][1]["title"] == "The Core Problem"
    assert updated_info["slides"][3]["title"] == "Market Size"


def test_markdown_and_csv_conversions(tmp_path: Path):
    # Markdown -> DOCX -> Markdown
    md_content = """# Executive Briefing

Here is the operational summary for **Q3 2026**.

## Key Highlights
- Launched multi-agent framework
- Achieved sub-50ms query latency

| Department | Headcount | Budget |
| Engineering | 50 | $5M |
| Marketing | 15 | $1.2M |
"""
    docx_file = tmp_path / "briefing.docx"
    markdown_to_docx(md_content, docx_file)
    assert docx_file.exists()

    # Inspect the converted docx
    info = inspect_document(docx_file)
    assert info["format"] == "docx"
    assert len(info["tables"]) == 1

    # Convert back to Markdown
    roundtrip_md = docx_to_markdown(docx_file)
    assert "Executive Briefing" in roundtrip_md
    assert "Engineering" in roundtrip_md

    # CSV -> XLSX -> CSV
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("Product,Q1,Q2\nAlpha,100,150\nBeta,200,280\n", encoding="utf-8")
    xlsx_file = tmp_path / "data.xlsx"
    csv_to_xlsx(csv_file, xlsx_file)
    assert xlsx_file.exists()

    csv_out = tmp_path / "roundtrip.csv"
    xlsx_to_csv(xlsx_file, csv_out)
    assert csv_out.exists()
    content = csv_out.read_text(encoding="utf-8")
    assert "Alpha" in content
    assert "Beta" in content
