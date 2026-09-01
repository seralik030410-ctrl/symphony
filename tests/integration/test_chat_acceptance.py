from __future__ import annotations

import asyncio

from conftest import FakeAdapter, wait_for_final
from backend.models.base import TokenUsage


async def create_session(client, provider: str = "ollama") -> dict:
    response = await client.post(
        "/api/sessions",
        json={"title": "Новый чат", "provider": provider, "model": "test-model"},
    )
    assert response.status_code == 201
    return response.json()


async def test_scenario_a_direct_chat_streams_and_persists_events(client, adapters):
    adapters["ollama"].chunks = ["Небо ", "кажется голубым из-за рассеяния света."]
    session = await create_session(client)

    response = await client.post(
        f"/api/sessions/{session['id']}/turns",
        json={"content": "Почему небо голубое?"},
    )
    assert response.status_code == 202
    turn_id = response.json()["turn"]["id"]
    turn = await wait_for_final(client, turn_id)
    restored = (await client.get(f"/api/sessions/{session['id']}")).json()
    events = (await client.get(f"/api/turns/{turn_id}/events")).json()

    assert turn["status"] == "completed"
    assert restored["messages"][-1]["content"] == "Небо кажется голубым из-за рассеяния света."
    assert [event["type"] for event in events] == [
        "turn.started",
        "context.built",
        "model.started",
        "model.delta",
        "model.delta",
        "model.completed",
        "turn.completed",
    ]
    assert not any(
        forbidden in event["type"]
        for event in events
        for forbidden in ("document", "skill", "tool", "sandbox", "artifact")
    )


async def test_scenario_f_new_session_has_zero_previous_context(client, adapters):
    first = await create_session(client)
    first_turn = (
        await client.post(
            f"/api/sessions/{first['id']}/turns",
            json={"content": "Запомни, что мы говорим о Японии."},
        )
    ).json()["turn"]
    await wait_for_final(client, first_turn["id"])

    second = await create_session(client)
    second_turn = (
        await client.post(
            f"/api/sessions/{second['id']}/turns",
            json={"content": "О какой стране мы говорили?"},
        )
    ).json()["turn"]
    await wait_for_final(client, second_turn["id"])

    last_request = adapters["ollama"].requests[-1]
    provider_context = "\n".join(message["content"] for message in last_request.messages)
    assert "Япони" not in provider_context
    assert "О какой стране" in provider_context


async def test_scenario_h_refresh_recovers_partial_turn_and_events(client, adapters):
    adapter: FakeAdapter = adapters["ollama"]
    adapter.chunks = ["Первая часть. ", "Вторая часть."]
    adapter.pause_after_first = True
    adapter.release.clear()
    session = await create_session(client)
    created = (
        await client.post(
            f"/api/sessions/{session['id']}/turns",
            json={"content": "Ответь в двух частях"},
        )
    ).json()
    await asyncio.wait_for(adapter.first_chunk_sent.wait(), timeout=1)

    refreshed = (await client.get(f"/api/sessions/{session['id']}")).json()
    persisted_events = (await client.get(f"/api/turns/{created['turn']['id']}/events")).json()

    assert refreshed["turns"][-1]["status"] == "model_running"
    assert refreshed["messages"][-1]["content"] == "Первая часть. "
    assert persisted_events[-1]["type"] == "model.delta"
    adapter.release.set()
    final = await wait_for_final(client, created["turn"]["id"])
    assert final["status"] == "completed"


async def test_cancel_stops_provider_and_preserves_partial_text(client, adapters):
    adapter: FakeAdapter = adapters["ollama"]
    adapter.chunks = ["Сохранённая часть", "Эта часть не должна появиться"]
    adapter.pause_after_first = True
    adapter.release.clear()
    session = await create_session(client)
    created = (
        await client.post(
            f"/api/sessions/{session['id']}/turns",
            json={"content": "Длинный ответ"},
        )
    ).json()
    await asyncio.wait_for(adapter.first_chunk_sent.wait(), timeout=1)

    cancelled = await client.post(f"/api/turns/{created['turn']['id']}/cancel")
    restored = (await client.get(f"/api/sessions/{session['id']}")).json()
    events = (await client.get(f"/api/turns/{created['turn']['id']}/events")).json()

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert adapter.cancelled == [f"{created['turn']['request_id']}:1"]
    assert restored["messages"][-1]["content"] == "Сохранённая часть"
    assert restored["messages"][-1]["status"] == "cancelled"
    assert events[-1]["type"] == "turn.cancelled"


async def test_same_flow_works_with_openai_compatible_profile(client, adapters):
    session = await create_session(client, provider="openai")
    created = (
        await client.post(
            f"/api/sessions/{session['id']}/turns",
            json={"content": "API parity"},
        )
    ).json()
    turn = await wait_for_final(client, created["turn"]["id"])

    assert turn["provider"] == "openai"
    assert turn["status"] == "completed"
    assert adapters["openai"].requests[-1].messages[-1]["content"] == "API parity"


async def test_reasoning_usage_and_context_window_are_durable(client, adapters):
    adapter: FakeAdapter = adapters["ollama"]
    adapter.reasoning_chunks = ["Сначала анализ. ", "Затем ответ."]
    adapter.usage = TokenUsage(input_tokens=321, output_tokens=45, reasoning_tokens=17)
    session = await create_session(client)
    created = (
        await client.post(
            f"/api/sessions/{session['id']}/turns",
            json={"content": "Покажи метрики"},
        )
    ).json()
    final = await wait_for_final(client, created["turn"]["id"])
    events = (await client.get(f"/api/turns/{final['id']}/events")).json()

    reasoning = "".join(
        event["payload"]["delta"]
        for event in events
        if event["type"] == "model.reasoning_delta"
    )
    usage = next(event for event in events if event["type"] == "model.usage")
    completed = next(event for event in events if event["type"] == "turn.completed")
    assert reasoning == "Сначала анализ. Затем ответ."
    assert usage["payload"]["input_tokens"] == 321
    assert usage["payload"]["context_window"] == 16_384
    assert completed["payload"]["output_tokens"] == 45
    assert completed["payload"]["reasoning_tokens"] == 17
