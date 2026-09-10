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
    add_chart_to_xlsx,
    fill_range_xlsx,
    sort_xlsx,
    modify_structure_xlsx,
)
from backend.office.analytics import analyze_spreadsheet
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


def test_spreadsheet_analytics(tmp_path: Path):
    xlsx_path = tmp_path / "metrics_data.xlsx"

    create_xlsx(
        xlsx_path,
        sheets=[
            {
                "name": "Metrics",
                "headers": ["Product", "Q1_Units", "Price", "Revenue", "BadFormula"],
                "rows": [
                    ["Alpha", 100, 25.0, "=B2*C2", 0],
                    ["Beta", 200, 30.0, "=B3*C3", "=10/E2"],  # division by zero
                    ["Gamma", 300, 15.0, "=B4*C4", 1],
                ],
            }
        ],
    )

    analysis = analyze_spreadsheet(xlsx_path, sheet_name="Metrics")
    assert analysis["file_name"] == "metrics_data.xlsx"
    assert analysis["sheet_name"] == "Metrics"
    assert analysis["dimensions"]["max_row"] >= 4
    assert analysis["dimensions"]["data_row_count"] == 3

    # Check columns
    cols_by_name = {c["name"]: c for c in analysis["columns"]}
    assert cols_by_name["Product"]["type"] == "text"
    assert cols_by_name["Q1_Units"]["type"] == "numeric"
    assert cols_by_name["Q1_Units"]["stats"]["min"] == 100
    assert cols_by_name["Q1_Units"]["stats"]["max"] == 300
    assert cols_by_name["Q1_Units"]["stats"]["sum"] == 600

    # Formula audit
    assert analysis["formula_audit"]["total_formulas"] >= 4
    assert len(analysis["formula_audit"]["formulas_sample"]) >= 1


def test_xlsx_charts_fill_sort_structure(tmp_path: Path):
    xlsx_path = tmp_path / "sales_chart.xlsx"

    create_xlsx(
        xlsx_path,
        sheets=[
            {
                "name": "Sales",
                "headers": ["Region", "Q1", "DoubleQ1"],
                "rows": [
                    ["North", 300, ""],
                    ["South", 100, ""],
                    ["East", 200, ""],
                ],
            }
        ],
    )

    # 1. Fill range with formula
    fill_res = fill_range_xlsx(
        xlsx_path,
        sheet_name="Sales",
        start_cell="C2",
        end_cell="C4",
        formula_template="=B{row}*2",
    )
    assert fill_res["status"] == "success"
    assert fill_res["filled_cells"] == 3

    # 2. Sort by Q1 column (col 2) ascending
    sort_res = sort_xlsx(xlsx_path, sheet_name="Sales", by_column=2, ascending=True, has_headers=True)
    assert sort_res["status"] == "success"

    # 3. Add chart
    chart_res = add_chart_to_xlsx(
        xlsx_path,
        sheet_name="Sales",
        chart_type="bar",
        data_range="B1:B4",
        categories_range="A2:A4",
        title="Q1 Regional Sales",
        target_cell="E2",
    )
    assert chart_res["status"] == "success"
    assert chart_res["added_charts"] == 1

    # 4. Modify structure
    struct_res = modify_structure_xlsx(xlsx_path, sheet_name="Sales", insert_row=5)
    assert struct_res["status"] == "success"

    # 5. Inspect to verify
    info = inspect_xlsx(xlsx_path)
    sheet_info = info["sheets"][0]
    assert sheet_info["chart_count"] == 1
    assert sheet_info["charts"][0]["type"] == "BarChart"
    assert sheet_info["charts"][0]["title"] == "Q1 Regional Sales"

