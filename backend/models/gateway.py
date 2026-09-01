from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import asdict

from backend.config import Settings
from backend.models.base import ChatRequest, ModelAdapter, ModelStreamEvent, ModelCapabilities, ProviderError
from backend.storage.database import utc_now
from backend.models.ollama import OllamaAdapter
from backend.models.openai_compatible import OpenAICompatibleAdapter


class ModelGateway:
    """One provider contract for local and API-backed chat completion."""

    def __init__(self, adapters: dict[str, ModelAdapter]) -> None:
        self.adapters = adapters
        self.database = None

    @classmethod
    def from_settings(cls, settings: Settings) -> "ModelGateway":
        return cls(
            {
                "ollama": OllamaAdapter(
                    settings.ollama_base_url,
                    settings.ollama_model,
                    request_timeout=settings.provider_timeout_seconds,
                    discovery_timeout=settings.discovery_timeout_seconds,
                ),
                "openai": OpenAICompatibleAdapter(
                    settings.openai_base_url,
                    settings.openai_model,
                    settings.openai_api_key,
                    profile_title=settings.openai_profile_name,
                    request_timeout=settings.provider_timeout_seconds,
                    discovery_timeout=settings.discovery_timeout_seconds,
                ),
            }
        )

    def get_adapter(self, provider: str) -> ModelAdapter:
        try:
            return self.adapters[provider]
        except KeyError as exc:
            raise ProviderError(f"Unknown provider: {provider}", code="unknown_provider") from exc

    async def stream_chat(self, provider: str, request: ChatRequest) -> AsyncIterator[ModelStreamEvent]:
        adapter = self.get_adapter(provider)
        async for delta in adapter.stream_chat(request):
            yield delta

    async def cancel(self, provider: str, request_id: str) -> None:
        await self.get_adapter(provider).cancel(request_id)

    async def context_window(self, provider: str, model: str) -> int:
        return (await self.resolve_capabilities(provider, model)).max_context

    async def resolve_capabilities(self, provider: str, model: str) -> ModelCapabilities:
        adapter = self.get_adapter(provider)
        caps = asdict(await adapter.resolve_capabilities(model))
        caps["max_context"] = await adapter.context_window(model)
        if self.database:
            with self.database.read() as connection:
                row = connection.execute("SELECT overrides_json FROM model_capability_overrides WHERE provider=? AND model=?", (provider, model)).fetchone()
            if row:
                caps.update(json.loads(row[0]))
        return ModelCapabilities(**caps)

    def set_capabilities(self, provider: str, model: str, overrides: dict):
        self.get_adapter(provider)
        if self.database is None:
            raise ProviderError("Capability store is unavailable")
        with self.database.transaction() as connection:
            connection.execute("INSERT INTO model_capability_overrides(provider,model,overrides_json,updated_at) VALUES(?,?,?,?) ON CONFLICT(provider,model) DO UPDATE SET overrides_json=excluded.overrides_json,updated_at=excluded.updated_at",
                (provider, model, json.dumps(overrides), utc_now()))

    async def list_profiles(self) -> list[dict[str, object]]:
        async def inspect(adapter: ModelAdapter) -> dict[str, object]:
            try:
                models = await adapter.list_models()
                available = True
                message = (
                    f"{len(models)} model(s) available"
                    if models
                    else "Provider is reachable, but returned no models"
                )
            except ProviderError as exc:
                models = []
                available = False
                message = str(exc)
            if adapter.default_model and adapter.default_model not in models:
                models = [adapter.default_model, *models]
            return {
                "provider": adapter.name,
                "title": adapter.title,
                "base_url": adapter.base_url,
                "default_model": adapter.default_model,
                "models": models,
                "available": available,
                "health_message": message,
                "capabilities": asdict(adapter.get_capabilities(adapter.default_model)),
            }

        return list(await asyncio.gather(*(inspect(adapter) for adapter in self.adapters.values())))
