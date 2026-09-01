from __future__ import annotations

import asyncio

import pytest

from backend.models.base import ModelCapabilities
from conftest import wait_for_final


@pytest.mark.parametrize("provider", ["ollama", "openai"])
async def test_context_settings_persist_and_reach_selected_provider(client, adapters, provider):
    adapters[provider].get_capabilities = lambda model: ModelCapabilities(max_context=65_536)
    session = (await client.post("/api/sessions", json={"provider": provider})).json()
    other = (await client.post("/api/sessions", json={"provider": provider})).json()
    endpoint = f"/api/sessions/{session['id']}"
    assert (await client.get(f"{endpoint}/model-limits")).json()["max_context"] == 65_536
    changed = await client.patch(endpoint, json={"context_window": 32_768, "max_output": 4_096})
    assert changed.status_code == 200
    restored = (await client.get(endpoint)).json()
    assert (restored["context_window"], restored["max_output"]) == (32_768, 4_096)
    untouched = (await client.get(f"/api/sessions/{other['id']}")).json()
    assert (untouched["context_window"], untouched["max_output"]) == (16_384, 2_048)
    created = await client.post(f"{endpoint}/turns", json={"content": "Проверка лимитов"})
    assert created.status_code == 202
    turn = await wait_for_final(client, created.json()["turn"]["id"])
    assert turn["status"] == "completed"
    request = adapters[provider].requests[-1]
    assert (request.context_window, request.max_output) == (32_768, 4_096)
    events = (await client.get(f"/api/turns/{turn['id']}/events")).json()
    assert next(item for item in events if item["type"] == "context.built")["payload"]["context_window"] == 32_768


@pytest.mark.parametrize("invalid", [
    {"context_window": 32_768}, {"context_window": 4_096, "max_output": 4_096},
    {"max_output": 16_384}, {"context_window": 1023}, {"max_output": 63},
])
async def test_invalid_context_settings_do_not_mutate_chat(client, invalid):
    session = (await client.post("/api/sessions", json={})).json()
    endpoint = f"/api/sessions/{session['id']}"
    assert (await client.patch(endpoint, json=invalid)).status_code == 422
    restored = (await client.get(endpoint)).json()
    assert (restored["context_window"], restored["max_output"]) == (16_384, 2_048)


async def test_context_settings_locked_during_generation(client, adapters):
    adapter = adapters["ollama"]
    adapter.pause_after_first = True
    adapter.release.clear()
    session = (await client.post("/api/sessions", json={})).json()
    endpoint = f"/api/sessions/{session['id']}"
    created = (await client.post(f"{endpoint}/turns", json={"content": "Привет"})).json()
    await asyncio.wait_for(adapter.first_chunk_sent.wait(), timeout=2)
    try:
        changed = await client.patch(endpoint, json={"context_window": 8_192, "max_output": 1_024})
        assert changed.status_code == 409
        assert (await client.get(endpoint)).json()["context_window"] == 16_384
    finally:
        await client.post(f"/api/turns/{created['turn']['id']}/cancel")


async def test_switching_model_clamps_context_to_its_limit(client, adapters):
    adapters["ollama"].get_capabilities = lambda model: ModelCapabilities(max_context=65_536 if model == "large" else 8_192)
    session = (await client.post("/api/sessions", json={"model": "large"})).json()
    endpoint = f"/api/sessions/{session['id']}"
    assert (await client.patch(endpoint, json={"context_window": 65_536})).status_code == 200
    changed = await client.patch(endpoint, json={"model": "small"})
    assert changed.status_code == 200
    assert changed.json()["context_window"] == 8_192
    assert (await client.get(f"{endpoint}/model-limits")).json()["max_context"] == 8_192
