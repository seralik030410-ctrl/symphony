from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import httpx

from backend.main import create_app
from backend.models.base import ChatRequest, ModelAdapter, ModelCapabilities, ModelStreamEvent, ToolCall
from backend.models.gateway import ModelGateway
from backend.sandbox.runtime import SandboxResult
from backend.tools.registry import ToolRegistry

from conftest import wait_for_final


class FakeSandbox:
    def __init__(self, workspaces) -> None:
        self.workspaces = workspaces
        self.calls: list[dict] = []

    async def health(self):
        return True, "Fake sandbox ready"

    async def execute(self, **arguments):
        self.calls.append(arguments)
        root = self.workspaces.session_root(arguments["session_id"])
        output = root / "dist" / "index.html"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            "<!doctype html><title>Symphony Preview</title><h1>Сайт готов</h1>",
            encoding="utf-8",
        )
        return SandboxResult(
            exit_code=0,
            stdout="build passed\n",
            stderr="",
            duration_ms=12,
            changed_files=["dist/index.html"],
        )


class SiteBuilderAdapter(ModelAdapter):
    name = "ollama"
    title = "Scripted builder"
    base_url = "memory://builder"
    default_model = "test-model"

    def __init__(self, *, network: bool = False) -> None:
        self.requests: list[ChatRequest] = []
        self.network = network

    async def list_models(self):
        return [self.default_model]

    def get_capabilities(self, model: str):
        return ModelCapabilities(native_tools=True)

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[ModelStreamEvent]:
        self.requests.append(request)
        step = len(self.requests)
        if step == 1:
            yield ModelStreamEvent(
                type="tool_call",
                tool_call=ToolCall(
                    id="source",
                    name="fs.write",
                    arguments={"path": "src/index.html", "content": "<h1>Сайт</h1>\n"},
                ),
            )
        elif step == 2:
            yield ModelStreamEvent(
                type="tool_call",
                tool_call=ToolCall(
                    id="build",
                    name="sandbox.shell",
                    arguments={
                        "command": "npm run build" if not self.network else "npm install",
                        "network": self.network,
                    },
                ),
            )
        elif step == 3:
            yield ModelStreamEvent(
                type="tool_call",
                tool_call=ToolCall(
                    id="preview",
                    name="sandbox.preview",
                    arguments={"entry": "dist/index.html"},
                ),
            )
        else:
            yield ModelStreamEvent(type="text_delta", delta="Сайт собран, preview готов.")

    async def cancel(self, request_id: str):
        return None

    async def health(self):
        return True, "ready"


def install_fake_sandbox(app):
    sandbox = FakeSandbox(app.state.runtime.workspaces)
    registry = ToolRegistry.stage_three(app.state.runtime.workspaces, sandbox)  # type: ignore[arg-type]
    app.state.runtime.sandbox = sandbox
    app.state.runtime.tools = registry
    app.state.runtime.turn_service.tools = registry
    return sandbox


async def test_simple_site_build_persists_and_exposes_preview(settings):
    adapter = SiteBuilderAdapter()
    app = create_app(settings, ModelGateway({"ollama": adapter, "openai": adapter}))
    sandbox = install_fake_sandbox(app)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            session = (await client.post("/api/sessions", json={})).json()
            created = (
                await client.post(
                    f"/api/sessions/{session['id']}/turns",
                    json={"content": "Создай простой сайт, собери и покажи preview"},
                )
            ).json()
            final = await wait_for_final(client, created["turn"]["id"])
            events = (await client.get(f"/api/turns/{final['id']}/events")).json()
            preview = await client.get(f"/api/sessions/{session['id']}/preview/dist/index.html")

    assert final["status"] == "completed"
    assert sandbox.calls[0]["network"] is False
    assert "Сайт готов" in preview.text
    assert preview.headers["cache-control"] == "no-store"
    assert any(event["type"] == "preview.ready" for event in events)
    assert [event["type"] for event in events].count("tool.completed") == 3


async def test_network_command_waits_for_durable_approval(settings):
    adapter = SiteBuilderAdapter(network=True)
    app = create_app(settings, ModelGateway({"ollama": adapter, "openai": adapter}))
    sandbox = install_fake_sandbox(app)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            session = (await client.post("/api/sessions", json={})).json()
            created = (
                await client.post(
                    f"/api/sessions/{session['id']}/turns",
                    json={"content": "Установи зависимости и собери сайт"},
                )
            ).json()
            for _ in range(100):
                pending = (await client.get(f"/api/sessions/{session['id']}/approvals")).json()
                if pending:
                    break
                await asyncio.sleep(0.01)
            else:
                raise AssertionError("Approval was not requested")

            assert sandbox.calls == []
            decision = await client.post(
                f"/api/approvals/{pending[0]['id']}/decision",
                json={"approved": True},
            )
            final = await wait_for_final(client, created["turn"]["id"])
            events = (await client.get(f"/api/turns/{final['id']}/events")).json()

    assert decision.status_code == 200
    assert final["status"] == "completed"
    assert sandbox.calls[0]["network"] is True
    assert any(event["type"] == "approval.requested" for event in events)
    assert any(event["type"] == "approval.approved" for event in events)


async def test_preview_route_cannot_cross_chat_workspaces(settings):
    adapter = SiteBuilderAdapter()
    app = create_app(settings, ModelGateway({"ollama": adapter, "openai": adapter}))
    install_fake_sandbox(app)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            first = (await client.post("/api/sessions", json={})).json()
            second = (await client.post("/api/sessions", json={})).json()
            root = app.state.runtime.workspaces.session_root(first["id"])
            (root / "index.html").write_text("secret", encoding="utf-8")
            response = await client.get(f"/api/sessions/{second['id']}/preview/index.html")
            owner_response = await client.get(f"/api/sessions/{first['id']}/preview/index.html")

    assert response.status_code == 404
    assert owner_response.status_code == 200
    assert owner_response.text == "secret"
