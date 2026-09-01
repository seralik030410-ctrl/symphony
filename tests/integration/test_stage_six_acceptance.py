import asyncio
import json

import pytest

from backend.agent.context import ContextBuilder
from backend.models.base import ModelStreamEvent, ProviderError, TokenUsage
from backend.sandbox.runtime import SandboxResult
from backend.tools.contracts import ToolError
from tests.conftest import wait_for_final
from tests.integration.test_stage_six_context import upload, png


def history(runtime, session_id, count=12, length=100):
    for index in range(count):
        created = runtime.repository.create_turn(session_id, f"Пара {index}. " + "Подробности. " * length)
        runtime.repository.append_assistant_delta(created["assistant_message"]["id"], f"Решили {index}.")
        runtime.repository.set_message_status(created["assistant_message"]["id"], "complete")
        runtime.repository.set_turn_status(created["turn"]["id"], "completed", finished=True)


def semantic_adapter(monkeypatch, adapter):
    requests = []
    async def stream(request):
        requests.append(request)
        if request.response_json:
            yield ModelStreamEvent(type="text_delta", delta=json.dumps({"facts": ["Работаем локально"], "decisions": ["Использовать SQLite"], "open_tasks": ["Проверить готовый сайт"], "artifact_index": ["dist/index.html v2"]}, ensure_ascii=False))
            yield ModelStreamEvent(type="usage", usage=TokenUsage(100, 60))
        else:
            yield ModelStreamEvent(type="text_delta", delta="Готово")
    monkeypatch.setattr(adapter, "stream_chat", stream)
    return requests


@pytest.mark.parametrize("provider", ["ollama", "openai"])
async def test_semantic_memory_uses_gateway_keeps_tail_and_isolates(app, client, adapters, monkeypatch, provider):
    runtime = app.state.runtime
    session = (await client.post("/api/sessions", json={"provider": provider})).json()
    other = (await client.post("/api/sessions", json={})).json()
    history(runtime, session["id"])
    original = runtime.repository.list_context_records(session["id"])
    requests = semantic_adapter(monkeypatch, adapters[provider])
    snapshot = (await client.post(f"/api/sessions/{session['id']}/memory/snapshot")).json()
    assert snapshot["kind"] == "automatic" and snapshot["facts"] == ["Работаем локально"]
    assert snapshot["source_message_ids"] == [item["id"] for item in original[:-10]]
    assert snapshot["input_tokens"] == 100 and snapshot["output_tokens"] == 60
    assert requests[0].tools is None and requests[0].response_json
    assert original[0]["content"] in json.loads(requests[0].messages[1]["content"].split("older_messages:\n")[1])[0]["content"]
    pack = ContextBuilder(runtime.repository).build(session["id"], memory_source_ids=set(snapshot["source_message_ids"]), evidence=runtime.memory.prompt(snapshot))
    assert pack.messages[-10:] == [{"role": item["role"], "content": item["content"]} for item in original[-10:]]
    assert runtime.repository.list_context_records(session["id"]) == original
    assert (await client.get(f"/api/sessions/{other['id']}/memory")).json()["version"] == 0
    assert snapshot["version"] == (await client.post(f"/api/sessions/{session['id']}/memory/snapshot")).json()["version"]
    edited = (await client.put(f"/api/sessions/{session['id']}/memory", json={"facts": ["Уточнённый факт"]})).json()
    assert edited["source_message_ids"] == snapshot["source_message_ids"]
    assert len((await client.get(f"/api/sessions/{session['id']}/memory/versions")).json()) == 2


async def test_automatic_memory_has_events_and_stop_does_not_publish_partial(app, client, adapters, monkeypatch):
    runtime = app.state.runtime
    session = (await client.post("/api/sessions", json={})).json()
    history(runtime, session["id"], count=14, length=250)
    requests = semantic_adapter(monkeypatch, adapters["ollama"])
    created = (await client.post(f"/api/sessions/{session['id']}/turns", json={"content": "Что решили?"})).json()
    final = await wait_for_final(client, created["turn"]["id"], timeout=10)
    assert final["status"] == "completed", final
    events = runtime.repository.list_events(final["id"])
    assert any(item["type"] == "memory.started" for item in events)
    assert any(item["type"] == "memory.snapshot" for item in events)
    assert any(request.response_json for request in requests)
    second = (await client.post("/api/sessions", json={})).json()
    history(runtime, second["id"], count=14, length=250)
    started = asyncio.Event()
    async def paused(request):
        if request.response_json:
            started.set()
            yield ModelStreamEvent(type="text_delta", delta='{"facts":[')
            await asyncio.Event().wait()
    monkeypatch.setattr(adapters["ollama"], "stream_chat", paused)
    turn = (await client.post(f"/api/sessions/{second['id']}/turns", json={"content": "Продолжай"})).json()["turn"]
    await asyncio.wait_for(started.wait(), 3)
    assert (await client.put(f"/api/sessions/{second['id']}/memory", json={"facts": ["race"]})).status_code == 409
    assert (await client.post(f"/api/turns/{turn['id']}/cancel")).json()["status"] == "cancelled"
    assert runtime.memory.get(second["id"])["version"] == 0
    assert not runtime.memory.busy(second["id"])


async def test_ocr_mode_works_on_text_model_and_retry_retains_attachment(app, client, monkeypatch, adapters):
    runtime = app.state.runtime
    session = (await client.post("/api/sessions", json={})).json()
    attachment = await upload(client, session["id"], "receipt.png", png("TOTAL 42"))
    async def execute(**kwargs):
        assert kwargs["network"] is False
        return SandboxResult(0, "TOTAL 42", "", 12)
    monkeypatch.setattr(runtime.sandbox, "execute", execute)
    turn = (await client.post(f"/api/sessions/{session['id']}/turns", json={"content": "Прочитай чек", "attachment_ids": [attachment["id"]], "image_mode": "ocr"})).json()["turn"]
    final = await wait_for_final(client, turn["id"])
    assert final["status"] == "completed", final
    messages = adapters["ollama"].requests[-1].messages
    assert all("images" not in item and isinstance(item["content"], str) for item in messages)
    assert "TOTAL 42" in "\n".join(item["content"] for item in messages)
    events = runtime.repository.list_events(turn["id"])
    assert any(item["type"] == "vision.ocr_completed" for item in events)
    runtime.repository.set_turn_status(turn["id"], "cancelled", finished=True)
    retry = (await client.post(f"/api/turns/{turn['id']}/retry")).json()
    assert retry["user_message"]["attachments"][0]["id"] == attachment["id"]
    assert retry["user_message"]["attachments"][0]["image_mode"] == "ocr"
    assert (await wait_for_final(client, retry["turn"]["id"]))["status"] == "completed"
    assert (await client.delete(f"/api/sessions/{session['id']}/inputs/{attachment['id']}")).status_code == 409
    assert runtime.workspaces.resolve(session["id"], attachment["path"]).exists()


async def test_index_freshness_upload_limits_and_changed_attachment(app, client):
    runtime = app.state.runtime
    session = (await client.post("/api/sessions", json={})).json()
    path = runtime.workspaces.resolve(session["id"], "facts.txt")
    path.write_text("Секреткалибровка = 42", encoding="utf-8")
    await runtime.file_index.index_document(session["id"], "facts.txt")
    assert runtime.file_index.search(session["id"], "Секреткалибровка")
    path.write_text("Изменено полностью", encoding="utf-8")
    assert not runtime.file_index.search(session["id"], "Секреткалибровка")
    assert runtime.file_index.get_file(session["id"], "facts.txt")["status"] == "failed"
    for index in range(8):
        await upload(client, session["id"], f"{index}.png", png(str(index)))
    pending = runtime.file_index.list_attachments(session["id"], pending_only=True)
    import base64
    ninth = await client.post(f"/api/sessions/{session['id']}/inputs", json={"filename": "nine.png", "content_base64": base64.b64encode(png("9")).decode()})
    assert ninth.status_code == 409
    runtime.workspaces.resolve(session["id"], pending[0]["path"]).write_bytes(b"changed")
    response = await client.post(f"/api/sessions/{session['id']}/turns", json={"content": "OCR", "attachment_ids": [pending[0]["id"]], "image_mode": "ocr"})
    assert response.status_code == 409
    assert runtime.repository.get_session(session["id"], include_history=True)["turns"] == []


async def test_model_capability_override_is_explicit_and_persistent(app, client):
    session = (await client.post("/api/sessions", json={"provider": "openai"})).json()
    path = f"/api/sessions/{session['id']}/model-capabilities"
    assert (await client.get(path)).json()["vision"] is False
    assert (await client.put(path, json={"vision": True, "max_context": 32768})).status_code == 200
    caps = await app.state.runtime.gateway.resolve_capabilities("openai", session["model"])
    assert caps.vision and caps.max_context == 32768
    assert (await client.put(path, json={"vision": True, "max_context": 999999})).status_code == 422
    assert (await client.put(path, json={})).json()["vision"] is False
