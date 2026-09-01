from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from backend.config import Settings
from backend.main import create_app
from backend.models.base import ChatRequest, ModelAdapter, ModelCapabilities, ModelStreamEvent, TokenUsage
from backend.models.gateway import ModelGateway


class FakeAdapter(ModelAdapter):
    title = "Test provider"
    base_url = "memory://provider"
    default_model = "test-model"

    def __init__(self, name: str, chunks: list[str] | None = None) -> None:
        self.name = name
        self.chunks = chunks or ["Тестовый ", "ответ"]
        self.requests: list[ChatRequest] = []
        self.reasoning_chunks: list[str] = []
        self.usage: TokenUsage | None = None
        self.cancelled: list[str] = []
        self.pause_after_first = False
        self.first_chunk_sent = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()

    async def list_models(self) -> list[str]:
        return [self.default_model]

    def get_capabilities(self, model: str) -> ModelCapabilities:
        return ModelCapabilities(max_context=16_384, max_output=2_048)

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[ModelStreamEvent]:
        self.requests.append(request)
        for chunk in self.reasoning_chunks:
            yield ModelStreamEvent(type="reasoning_delta", delta=chunk)
        for index, chunk in enumerate(self.chunks):
            yield ModelStreamEvent(type="text_delta", delta=chunk)
            if index == 0:
                self.first_chunk_sent.set()
                if self.pause_after_first:
                    await self.release.wait()
            await asyncio.sleep(0)
        if self.usage is not None:
            yield ModelStreamEvent(type="usage", usage=self.usage)

    async def cancel(self, request_id: str) -> None:
        self.cancelled.append(request_id)
        self.release.set()

    async def health(self) -> tuple[bool, str]:
        return True, "ready"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "symphony-test.db",
        workspace_root=tmp_path / "workspaces",
        skills_root=tmp_path / "skills",
        seed_bundled_skills=False,
        ollama_model="test-model",
        openai_model="test-model",
        discovery_timeout_seconds=0.05,
    )


@pytest.fixture
def adapters() -> dict[str, FakeAdapter]:
    return {
        "ollama": FakeAdapter("ollama"),
        "openai": FakeAdapter("openai"),
    }


@pytest_asyncio.fixture
async def app(settings: Settings, adapters: dict[str, FakeAdapter]):
    application = create_app(settings, ModelGateway(adapters))
    async with application.router.lifespan_context(application):
        yield application


@pytest_asyncio.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as active_client:
        yield active_client


async def wait_for_final(client: httpx.AsyncClient, turn_id: str, timeout: float = 2.0) -> dict:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        turn = (await client.get(f"/api/turns/{turn_id}")).json()
        if turn["status"] in {"completed", "failed", "cancelled", "interrupted"}:
            return turn
        await asyncio.sleep(0.01)
    raise AssertionError(f"Turn {turn_id} did not finish in {timeout} seconds")
