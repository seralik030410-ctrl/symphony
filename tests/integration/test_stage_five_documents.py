from __future__ import annotations

import asyncio
import base64
import json
import os
import copy
import httpx
import pytest

from backend.artifacts.renderers import render_job
from backend.artifacts.schemas import EXAMPLES
from backend.main import create_app
from backend.models.base import ModelCapabilities, ModelStreamEvent, ToolCall
from backend.models.gateway import ModelGateway
from backend.tools.contracts import ToolContext, ToolError
from backend.storage.repository import NotFoundError
from conftest import FakeAdapter, wait_for_final


class LocalTestRunner:
    """Test seam only: exercises actual renderer code, without requiring Docker."""
    async def render(self, job, on_output=None):
        try: render_job(job)
        except Exception as error: raise ToolError("document_render_failed", str(error)) from error


class DocumentAdapter(FakeAdapter):
    def __init__(self, name, format):
        super().__init__(name); self.format = format

    def get_capabilities(self, model): return ModelCapabilities(native_tools=True)

    async def stream_chat(self, request):
        self.requests.append(request)
        step = len(self.requests)
        calls = [
            ("artifact.schema", {"format": self.format}),
            ("fs.write", {"path": "report.json", "content": json.dumps(EXAMPLES[self.format], ensure_ascii=False)}),
            ("artifact.render", {"format": self.format, "spec_path": "report.json"}),
        ]
        if step <= len(calls):
            name, arguments = calls[step - 1]
            yield ModelStreamEvent(type="tool_call", tool_call=ToolCall(str(step), name, arguments))
        else: yield ModelStreamEvent(type="text_delta", delta="Документ создан и проверен.")


@pytest.mark.parametrize("format,provider", [("pdf", "ollama"), ("xlsx", "openai")])
async def test_document_model_tool_loop_and_durable_api_isolation(settings, format, provider):
    adapter = DocumentAdapter(provider, format)
    app = create_app(settings, ModelGateway({provider: adapter}))
    app.state.runtime.artifacts.runner = LocalTestRunner()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            session = (await client.post("/api/sessions", json={"provider": provider})).json()
            other = (await client.post("/api/sessions", json={"provider": provider})).json()
            turn = (await client.post(f"/api/sessions/{session['id']}/turns", json={"content": f"Создай {format}"})).json()["turn"]
            final = await wait_for_final(client, turn["id"], timeout=10)
            assert final["status"] == "completed", final
            events = (await client.get(f"/api/turns/{turn['id']}/events")).json()
            created = [event for event in events if event["type"] == "artifact.created"]
            assert len(created) == 1, events
            document = created[0]["payload"]
            downloaded = await client.get(document["download_url"])
            assert downloaded.status_code == 200 and len(downloaded.content) > 1000
            assert downloaded.headers["content-disposition"].startswith("attachment;")
            assert (await client.get(document["download_url"].replace(session["id"], other["id"])) ).status_code == 404
            assert (await client.get(f"/api/sessions/{other['id']}/artifacts")).json() == []
            detail = (await client.get(document["detail_url"])).json()
            assert detail["validation"]["valid"] and detail["validation"]["files"][f"document.{format}"]["sha256"]
            assert len((await client.get(f"/api/sessions/{session['id']}/artifacts")).json()) == 1
            assert detail["pages"] if format == "pdf" else detail["tables"]
            assert [e["type"] for e in events].index("artifact.validated") < [e["type"] for e in events].index("artifact.created")
            assert not any(call["name"] == "sandbox.shell" for call in app.state.runtime.repository.list_tool_calls(turn["id"]))
    # Reopen the same database through a fresh application: no memory-only artifact state.
    fresh = create_app(settings, ModelGateway({provider: adapter}))
    assert fresh.state.runtime.artifacts.get(session["id"], document["id"])["version"] == 1


def seed(runtime, format="pdf"):
    session = runtime.repository.create_session(title="Document QA", provider="ollama", model="test-model", system_prompt="", context_window=16384, max_output=2048)
    turn = runtime.repository.create_turn(session["id"], "Create document")["turn"]
    path = runtime.workspaces.resolve(session["id"], "report.json")
    path.write_text(json.dumps(EXAMPLES[format], ensure_ascii=False), encoding="utf-8")
    return ToolContext(session_id=session["id"], turn_id=turn["id"])


async def test_versions_are_immutable_integrity_checked_and_private(app):
    runtime = app.state.runtime; runtime.artifacts.runner = LocalTestRunner()
    context = seed(runtime)
    first = await runtime.artifacts.render(context, "pdf", "report.json", None)
    source = copy.deepcopy(EXAMPLES["pdf"]); source["title"] = "Вторая версия"
    runtime.workspaces.resolve(context.session_id, "report.json").write_text(json.dumps(source), encoding="utf-8")
    second = await runtime.artifacts.render(context, "pdf", "report.json", first["id"])
    assert second["id"] == first["id"] and second["version"] == 2
    assert runtime.artifacts.get(context.session_id, first["id"], 1)["title"] == "Отчёт"
    foreign = seed(runtime)
    with pytest.raises(NotFoundError): await runtime.artifacts.render(foreign, "pdf", "report.json", first["id"])
    path = runtime.artifacts.file(context.session_id, first["id"], 1, "document.pdf")
    path.write_bytes(b"tampered")
    with pytest.raises(ToolError, match="missing or changed"): runtime.artifacts.file(context.session_id, first["id"], 1, "document.pdf")


async def test_render_cancel_publishes_nothing_and_cleans_staging(app):
    runtime = app.state.runtime; context = seed(runtime)
    started = asyncio.Event(); stopped = asyncio.Event()
    class WaitingRunner:
        async def render(self, job, on_output=None):
            started.set()
            try: await asyncio.Event().wait()
            finally: stopped.set()
    runtime.artifacts.runner = WaitingRunner()
    task = asyncio.create_task(runtime.artifacts.render(context, "pdf", "report.json", None))
    await started.wait(); task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert stopped.is_set() and runtime.artifacts.list(context.session_id) == []
    assert list(runtime.artifacts.root(context.session_id).glob(".job-*")) == []


async def test_bad_spec_and_failed_renderer_publish_nothing(app):
    runtime = app.state.runtime; context = seed(runtime)
    path = runtime.workspaces.resolve(context.session_id, "report.json")
    path.write_text('{"title":"Bad","python":"print(1)"}')
    with pytest.raises(ToolError, match="sections"): await runtime.artifacts.render(context, "pdf", "report.json", None)
    assert not runtime.artifacts.list(context.session_id)


async def test_corrected_spec_can_rerender_same_path_but_unchanged_input_is_duplicate(settings):
    class RepairAdapter(DocumentAdapter):
        async def stream_chat(self, request):
            self.requests.append(request)
            step = len(self.requests)
            if step in {1, 3}:
                spec = copy.deepcopy(EXAMPLES["xlsx"])
                if step == 1: spec["sheets"][0]["formulas"]["B3"] = "=SUM(C2:C2)"
                name, args = "fs.write", {"path": "repair.json", "content": json.dumps(spec), "overwrite": step == 3}
            elif step in {2, 4, 5}: name, args = "artifact.render", {"format": "xlsx", "spec_path": "repair.json"}
            else:
                yield ModelStreamEvent(type="text_delta", delta="Готово после исправления ссылки."); return
            yield ModelStreamEvent(type="tool_call", tool_call=ToolCall(str(step), name, args))
    adapter = RepairAdapter("ollama", "xlsx")
    app = create_app(settings, ModelGateway({"ollama": adapter})); app.state.runtime.artifacts.runner = LocalTestRunner()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            session = (await client.post("/api/sessions", json={})).json()
            turn = (await client.post(f"/api/sessions/{session['id']}/turns", json={"content": "Создай таблицу"})).json()["turn"]
            final = await wait_for_final(client, turn["id"], timeout=10)
            events = (await client.get(f"/api/turns/{turn['id']}/events")).json()
            assert final["status"] == "completed", {"turn": final, "events": events}
            assert len([event for event in events if event["type"] == "artifact.created"]) == 1
            errors = [event["payload"]["code"] for event in events if event["type"] == "tool.failed"]
            assert errors == ["document_render_failed", "duplicate_tool_call"]


async def test_upload_and_read_table_scoped_and_no_overwrite(client, app):
    first = (await client.post("/api/sessions", json={})).json()
    other = (await client.post("/api/sessions", json={})).json()
    response = await client.post(f"/api/sessions/{first['id']}/inputs", json={"filename": "input.csv", "content_base64": base64.b64encode("Статья,Сумма\nПлан,100\nФакт,120".encode()).decode()})
    assert response.status_code == 201
    path = response.json()["path"]
    result = await app.state.runtime.tools.execute("artifact.read_table", {"path": path}, ToolContext(session_id=first["id"], turn_id="unused"))
    assert result.output["rows"][1] == ["План", "100"]
    with pytest.raises(ToolError): await app.state.runtime.tools.execute("artifact.read_table", {"path": path}, ToolContext(session_id=other["id"], turn_id="unused"))
    for filename in ["../bad.csv", "C:\\bad.csv", "macro.xlsm"]:
        assert (await client.post(f"/api/sessions/{first['id']}/inputs", json={"filename": filename, "content_base64": ""})).status_code == 422


async def test_ordinary_chat_does_not_create_documents(client, app):
    session = (await client.post("/api/sessions", json={})).json()
    turn = (await client.post(f"/api/sessions/{session['id']}/turns", json={"content": "Как дела?"})).json()["turn"]
    await wait_for_final(client, turn["id"])
    events = (await client.get(f"/api/turns/{turn['id']}/events")).json()
    assert not any(e["type"].startswith("artifact.") or e["type"].startswith("tool.") for e in events)
    assert app.state.runtime.artifacts.list(session["id"]) == []


async def test_excel_attachment_to_pdf_uses_read_table_result(settings, monkeypatch):
    import io
    import pymupdf
    from openpyxl import Workbook
    book = Workbook(); book.active.append(["Показатель", "Значение"]); book.active.append(["Факт", 125])
    content = io.BytesIO(); book.save(content)
    class TableReportAdapter(DocumentAdapter):
        path = ""
        async def stream_chat(self, request):
            self.requests.append(request)
            step = len(self.requests)
            if step == 1: name, args = "artifact.read_table", {"path": self.path, "limit": 2}
            elif step == 2:
                observed = json.loads(request.messages[-1]["content"])["output"]["rows"]
                spec = {"title": "Из Excel", "sections": [{"heading": "Данные источника", "table": {"columns": observed[0], "rows": observed[1:]}}]}
                name, args = "fs.write", {"path": "report.json", "content": json.dumps(spec, ensure_ascii=False)}
            elif step == 3: name, args = "artifact.render", {"format": "pdf", "spec_path": "report.json"}
            else:
                yield ModelStreamEvent(type="text_delta", delta="Отчёт по прикреплённой таблице готов."); return
            yield ModelStreamEvent(type="tool_call", tool_call=ToolCall(str(step), name, args))
    adapter = TableReportAdapter("ollama", "pdf")
    app = create_app(settings, ModelGateway({"ollama": adapter})); app.state.runtime.artifacts.runner = LocalTestRunner()
    async def fixture_extract(raw, suffix):
        # This test isolates the PDF workflow; real extraction has Docker acceptance coverage.
        return "Показатель\tЗначение\nФакт\t125"
    monkeypatch.setattr(app.state.runtime.file_index.extractor, "extract", fixture_extract)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            session = (await client.post("/api/sessions", json={})).json()
            upload = (await client.post(f"/api/sessions/{session['id']}/inputs", json={"filename": "source.XLSX", "content_base64": base64.b64encode(content.getvalue()).decode()})).json()
            adapter.path = upload["path"]
            turn = (await client.post(f"/api/sessions/{session['id']}/turns", json={"content": f"Сделай PDF по таблице {adapter.path}"})).json()["turn"]
            assert (await wait_for_final(client, turn["id"], timeout=10))["status"] == "completed"
            artifacts = (await client.get(f"/api/sessions/{session['id']}/artifacts")).json()
            assert len(artifacts) == 1
            pdf = (await client.get(artifacts[0]["download_url"])).content
            with pymupdf.open(stream=pdf, filetype="pdf") as document:
                assert "125" in document[0].get_text()


@pytest.mark.skipif(os.getenv("SYMPHONY_RUN_DOCKER_TESTS") != "1", reason="Opt-in real Docker document runtime")
@pytest.mark.parametrize("format", ["pdf", "xlsx", "docx", "pptx"])
async def test_real_docker_trusted_renderer_with_native_previews(app, format):
    runtime = app.state.runtime; context = seed(runtime, format)
    if format in {"docx", "pptx"}:
        import io
        from PIL import Image
        buffer = io.BytesIO(); Image.new("RGB", (32, 24), (36, 94, 99)).save(buffer, format="PNG")
        picture = {"png_base64": base64.b64encode(buffer.getvalue()).decode(), "caption": "Тестовая иллюстрация"}
        table = {"columns": ["Период", "Значение"], "rows": [["План", 100], ["Факт", 120]]}
        chart = {"title": "План / факт", "labels": ["План", "Факт"], "values": [100, 120]}
        spec = copy.deepcopy(EXAMPLES[format])
        if format == "docx":
            spec["sections"][0].update({"table": table, "chart": chart, "image": picture, "callout": "Проверяем все элементы документа"})
        else:
            spec["slides"].extend([{"title": "Таблица", "table": table}, {"title": "Диаграмма", "chart": chart}, {"title": "Изображение", "image": picture}])
        runtime.workspaces.resolve(context.session_id, "report.json").write_text(json.dumps(spec), encoding="utf-8")
    result = await runtime.artifacts.render(context, format, "report.json", None)
    detail = runtime.artifacts.get(context.session_id, result["id"])
    assert detail["valid"] and detail["size"] > 1000
    if format == "xlsx": assert detail["validation"]["calculation"]["values"]["Бюджет!B3"] == 100
    else:
        assert len(detail["pages"]) >= 1
        assert runtime.artifacts.file(context.session_id, result["id"], 1, "page-001.png").stat().st_size > 1000
        if format in {"docx", "pptx"}: assert detail["validation"]["preview_pdf"] == "preview.pdf"


def test_document_runner_contract(app):
    from pathlib import Path
    runner = app.state.runtime.artifacts.runner
    arguments = runner.arguments(Path("C:/one/job"), "test-document")
    assert arguments[arguments.index("--network") + 1] == "none"
    assert "--read-only" in arguments and "no-new-privileges" in arguments
    assert not any("target=/workspace" in arg for arg in arguments)
    assert any("target=/opt/artifacts,readonly" in arg for arg in arguments)
    assert arguments[-4:] == ["python", "-m", "artifacts.worker", "/job"]
    tool = app.state.runtime.tools.get("artifact.render")
    decision = app.state.runtime.policy.evaluate(tool, {"format": "pdf", "spec_path": "report.json"}, profile="read_only")
    assert decision.action == "approval_required"


async def test_old_document_image_rejected_before_launch(app, monkeypatch, tmp_path):
    runner = app.state.runtime.artifacts.runner
    async def old_image(*arguments): return 0, "3.1"
    monkeypatch.setattr(runner.sandbox, "_docker_control", old_image)
    runner.sandbox._recovery_done = True
    with pytest.raises(ToolError, match="runtime 5.0 or 6.0 is not ready"):
        await runner.render(tmp_path)


@pytest.mark.skipif(os.getenv("SYMPHONY_RUN_DOCKER_TESTS") != "1", reason="Opt-in real Docker document cancellation")
async def test_real_document_cancel_removes_container(app, monkeypatch):
    runtime = app.state.runtime; context = seed(runtime)
    runner = runtime.artifacts.runner
    original = runner.arguments
    names = []
    def waiting_arguments(job, name):
        names.append(name)
        return original(job, name)[:-4] + ["python", "-c", "import time; time.sleep(120)"]
    monkeypatch.setattr(runner, "arguments", waiting_arguments)
    job = runtime.artifacts.root(context.session_id) / "cancel-test"; job.mkdir()
    task = asyncio.create_task(runner.render(job))
    try:
        for _ in range(100):
            if not names:
                await asyncio.sleep(.1)
                continue
            _, output = await runtime.sandbox._docker_control("ps", "-q", "--filter", f"name={names[0]}")
            if output.strip(): break
            await asyncio.sleep(.1)
        assert output.strip(), "Document container did not start"
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
    _, output = await runtime.sandbox._docker_control("ps", "-aq", "--filter", f"name={names[0]}")
    assert not output.strip()
