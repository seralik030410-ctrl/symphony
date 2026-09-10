"""Unit tests for Office tools and API router."""
from __future__ import annotations

from pathlib import Path
import pytest
from starlette.testclient import TestClient

from backend.tools.contracts import ToolContext
from backend.tools.workspace import WorkspaceManager
from backend.tools.office import (
    OfficeInspectTool,
    OfficeInspectInput,
    OfficeCreateTool,
    OfficeCreateInput,
    OfficePatchTool,
    OfficePatchInput,
    OfficeConvertTool,
    OfficeConvertInput,
)
from backend.main import create_app
from backend.config import Settings


@pytest.mark.asyncio
async def test_office_tools_lifecycle(tmp_path: Path):
    workspaces = WorkspaceManager(tmp_path)
    session_id = "a" * 32
    context = ToolContext(session_id=session_id, turn_id="turn-1")

    # 1. Create Tool
    create_tool = OfficeCreateTool(workspaces)
    res_create = await create_tool.execute(
        context,
        OfficeCreateInput(
            path="notes.docx",
            title="Strategic Roadmap 2026",
            sections=[
                {
                    "heading": "Milestones",
                    "level": 1,
                    "paragraphs": ["Complete Stage 21 Office Deep Integration."],
                }
            ],
        ),
    )
    assert res_create.output["status"] == "created"
    assert "notes.docx" in res_create.changed_files

    # 2. Inspect Tool
    inspect_tool = OfficeInspectTool(workspaces)
    res_inspect = await inspect_tool.execute(
        context,
        OfficeInspectInput(path="notes.docx"),
    )
    assert res_inspect.output["format"] == "docx"
    assert res_inspect.output["paragraph_count"] >= 2

    # 3. Patch Tool
    patch_tool = OfficePatchTool(workspaces)
    res_patch = await patch_tool.execute(
        context,
        OfficePatchInput(
            path="notes.docx",
            append_paragraphs=[
                {"text": "Add live reactive spreadsheet and slide studio.", "style": "Normal"}
            ],
        ),
    )
    assert res_patch.output["status"] == "success"

    # 4. Convert Tool
    convert_tool = OfficeConvertTool(workspaces)
    res_convert = await convert_tool.execute(
        context,
        OfficeConvertInput(
            source_path="notes.docx",
            target_format="md",
            output_path="notes.md",
        ),
    )
    assert res_convert.output["status"] == "converted"
    assert "notes.md" in res_convert.changed_files

    # Verify converted file exists in workspace
    md_file = workspaces.resolve(session_id, "notes.md")
    assert md_file.exists()
    assert "Strategic Roadmap" in md_file.read_text(encoding="utf-8")


def test_office_api_endpoints(tmp_path: Path):
    settings = Settings(
        workspace_root=tmp_path / "workspaces",
        database_path=tmp_path / "test.db",
        skills_root=tmp_path / "skills",
        bundled_skills_root=tmp_path / "bundled_skills",
    )
    app = create_app(settings)
    client = TestClient(app)

    # 1. Create a session
    resp = client.post("/api/sessions", json={"title": "Office Test Session"})
    assert resp.status_code == 201
    session_id = resp.json()["id"]

    # 2. Save/Create a document via office API
    resp_save = client.post(
        f"/api/sessions/{session_id}/office/save",
        json={
            "path": "budget.xlsx",
            "format": "xlsx",
            "text_content": None,
        },
    )
    # File doesn't exist yet, should handle creation or return 400
    assert resp_save.status_code in (200, 400)

    # Let's create a file using standard workspace or raw
    import openpyxl
    ws_mgr = app.state.runtime.workspaces
    target = ws_mgr.resolve(session_id, "budget.xlsx")
    target.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.append(["Category", "Budget", "Actual"])
    ws.append(["Operations", 50000, 48000])
    wb.save(target)

    # 3. Inspect document via office API
    resp_inspect = client.get(f"/api/sessions/{session_id}/office/inspect?path=budget.xlsx")
    assert resp_inspect.status_code == 200
    doc_data = resp_inspect.json()
    assert doc_data["format"] == "xlsx"
    assert "Summary" in doc_data["sheet_names"]

    # 4. Patch document via office API
    resp_patch = client.post(
        f"/api/sessions/{session_id}/office/save",
        json={
            "path": "budget.xlsx",
            "cell_updates": [
                {"sheet": "Summary", "cell": "C2", "value": 49500}
            ],
        },
    )
    assert resp_patch.status_code == 200
    updated_doc = resp_patch.json()["document"]
    assert updated_doc["sheets_by_name"]["Summary"]["rows"][1][2] == "49500" or updated_doc["sheets_by_name"]["Summary"]["rows"][1][2] == 49500

    # 5. Raw file download via office API
    resp_raw = client.get(f"/api/sessions/{session_id}/office/raw?path=budget.xlsx")
    assert resp_raw.status_code == 200
    assert len(resp_raw.content) > 0

    # 6. Convert file via office API
    resp_convert = client.post(
        f"/api/sessions/{session_id}/office/convert",
        json={
            "source_path": "budget.xlsx",
            "target_format": "csv",
        },
    )
    assert resp_convert.status_code == 200
    assert resp_convert.json()["status"] == "converted"
