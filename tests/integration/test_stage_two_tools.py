from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from backend.models.base import (
    ChatRequest,
    ModelAdapter,
    ModelCapabilities,
    ModelStreamEvent,
    ToolCall,
)
from backend.models.gateway import ModelGateway
from backend.tools.contracts import Tool, ToolContext, ToolInput, ToolResult
from backend.tools.registry import ToolRegistry

from conftest import wait_for_final


class ToolScriptAdapter(ModelAdapter):
    name = "ollama"
    title = "Tool script"
    base_url = "memory://tools"
    default_model = "test-model"

    def __init__(self) -> None:
        self.requests: list[ChatRequest] = []

    async def list_models(self) -> list[str]:
        return [self.default_model]

    def get_capabilities(self, model: str) -> ModelCapabilities:
        return ModelCapabilities(native_tools=True)

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[ModelStreamEvent]:
        self.requests.append(request)
        step = len(self.requests)
        if step == 1:
            yield ModelStreamEvent(
                type="tool_call",
                tool_call=ToolCall(
                    id="call-one",
                    name="fs.write",
                    arguments={"path": "brief.md", "content": "# Brief\nDraft\n"},
                ),
            )
            yield ModelStreamEvent(
                type="tool_call",
                tool_call=ToolCall(
                    id="call-two",
                    name="fs.write",
                    arguments={"path": "notes/todo.txt", "content": "review brief\n"},
                ),
            )
        elif step == 2:
            yield ModelStreamEvent(
                type="tool_call",
                tool_call=ToolCall(
                    id="call-three",
                    name="fs.apply_patch",
                    arguments={
                        "path": "brief.md",
                        "old_text": "Draft",
                        "new_text": "Ready",
                    },
                ),
            )
        else:
            yield ModelStreamEvent(type="text_delta", delta="Созданы два файла, brief.md обновлён.")

    async def cancel(self, request_id: str) -> None:
        return None

    async def health(self) -> tuple[bool, str]:
        return True, "ready"


async def test_model_creates_and_edits_multiple_workspace_files(settings):
    import httpx

    from backend.main import create_app

    adapter = ToolScriptAdapter()
    app = create_app(settings, ModelGateway({"ollama": adapter, "openai": adapter}))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            session = (
                await client.post(
                    "/api/sessions",
                    json={"provider": "ollama", "model": "test-model"},
                )
            ).json()
            created = (
                await client.post(
                    f"/api/sessions/{session['id']}/turns",
                    json={"content": "Создай brief и todo, затем подготовь brief"},
                )
            ).json()
            final = await wait_for_final(client, created["turn"]["id"])
            events = (await client.get(f"/api/turns/{final['id']}/events")).json()
            tree = (await client.get(f"/api/sessions/{session['id']}/tree")).json()
            restored = (await client.get(f"/api/sessions/{session['id']}")).json()

    assert final["status"] == "completed"
    assert restored["messages"][-1]["content"] == "Созданы два файла, brief.md обновлён."
    assert {item["path"] for item in tree["entries"] if item["type"] == "file"} == {
        "brief.md",
        "notes/todo.txt",
    }
    workspace = settings.workspace_root / session["id"] / "worktree"
    assert (workspace / "brief.md").read_text(encoding="utf-8") == "# Brief\nReady\n"
    assert [event["type"] for event in events].count("tool.completed") == 3
    assert [event["type"] for event in events].count("file.changed") == 3
    assert all(request.tools for request in adapter.requests)
    assert adapter.requests[-1].messages[-1]["role"] == "tool"


async def test_retry_creates_a_new_turn_for_failed_input(app, client):
    runtime = app.state.runtime
    session = runtime.repository.create_session(
        title="Новый чат",
        provider="ollama",
        model="test-model",
        system_prompt="You are helpful.",
        context_window=16_384,
        max_output=2_048,
    )
    original = runtime.repository.create_turn(session["id"], "Повтори этот запрос")
    runtime.repository.set_message_status(original["turn"]["assistant_message_id"], "failed")
    runtime.repository.set_turn_status(original["turn"]["id"], "failed", error="boom", finished=True)

    response = await client.post(f"/api/turns/{original['turn']['id']}/retry")
    assert response.status_code == 202
    retried = response.json()
    assert retried["turn"]["id"] != original["turn"]["id"]
    assert retried["user_message"]["content"] == "Повтори этот запрос"
    final = await wait_for_final(client, retried["turn"]["id"])
    assert final["status"] == "completed"


class HangingInput(ToolInput):
    pass


class HangingTool(Tool):
    name = "test.hang"
    title = "Hanging action"
    description = "Waits until the turn is cancelled."
    input_model = HangingInput

    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def execute(self, context: ToolContext, arguments: HangingInput) -> ToolResult:
        self.started.set()
        await asyncio.Event().wait()
        return ToolResult({})


class HangingAdapter(ToolScriptAdapter):
    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[ModelStreamEvent]:
        self.requests.append(request)
        yield ModelStreamEvent(
            type="tool_call",
            tool_call=ToolCall(id="hang", name="test.hang", arguments={}),
        )


async def test_stop_cancels_an_active_tool_and_persists_terminal_state(settings):
    import httpx

    from backend.main import create_app

    adapter = HangingAdapter()
    app = create_app(settings, ModelGateway({"ollama": adapter, "openai": adapter}))
    hanging = HangingTool()
    registry = ToolRegistry([hanging], default_timeout=30)
    app.state.runtime.tools = registry
    app.state.runtime.turn_service.tools = registry
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            session = (await client.post("/api/sessions", json={})).json()
            turn = (
                await client.post(
                    f"/api/sessions/{session['id']}/turns",
                    json={"content": "Run the hanging action"},
                )
            ).json()["turn"]
            await asyncio.wait_for(hanging.started.wait(), timeout=1)
            cancelled = await client.post(f"/api/turns/{turn['id']}/cancel")
            events = (await client.get(f"/api/turns/{turn['id']}/events")).json()
            calls = app.state.runtime.repository.list_tool_calls(turn["id"])

    assert cancelled.json()["status"] == "cancelled"
    assert calls[0]["status"] == "cancelled"
    assert any(event["type"] == "tool.cancelled" for event in events)
    assert events[-1]["type"] == "turn.cancelled"
