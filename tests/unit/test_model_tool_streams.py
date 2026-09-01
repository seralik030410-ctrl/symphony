from __future__ import annotations

import json

import httpx

from backend.models.base import ChatRequest
from backend.models.ollama import OllamaAdapter
from backend.models.openai_compatible import OpenAICompatibleAdapter


def request_with_tools() -> ChatRequest:
    return ChatRequest(
        request_id="request-1",
        model="tool-model",
        messages=[{"role": "user", "content": "create a file"}],
        max_output=256,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "fs.write",
                    "description": "write",
                    "parameters": {"type": "object"},
                },
            }
        ],
    )


async def test_ollama_adapter_parses_native_tool_call(monkeypatch):
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        body = json.dumps(
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "thinking": "Проверяю workspace.",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "fs.write",
                                "arguments": {"path": "a.txt", "content": "hello"},
                            }
                        }
                    ],
                },
                "done": True,
                "prompt_eval_count": 42,
                "eval_count": 17,
            }
        )
        return httpx.Response(200, text=body + "\n")

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "backend.models.ollama.httpx.AsyncClient",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    adapter = OllamaAdapter("http://ollama.test", "tool-model")
    chat_request = request_with_tools()
    chat_request.context_window = 32_768
    chat_request.max_output = 4_096
    events = [event async for event in adapter.stream_chat(chat_request)]

    assert captured[0]["tools"][0]["function"]["name"] == "fs.write"
    assert captured[0]["think"] is True
    assert captured[0]["options"]["num_ctx"] == 32_768
    assert captured[0]["options"]["num_predict"] == 4_096
    reasoning = next(event for event in events if event.type == "reasoning_delta")
    tool = next(event for event in events if event.tool_call is not None)
    usage = next(event for event in events if event.usage is not None)
    assert reasoning.delta == "Проверяю workspace."
    assert tool.tool_call is not None
    assert tool.tool_call.arguments["path"] == "a.txt"
    assert usage.usage is not None
    assert usage.usage.input_tokens == 42
    assert usage.usage.output_tokens == 17


async def test_openai_adapter_accumulates_streamed_tool_arguments(monkeypatch):
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        chunks = [
            {"choices": [{"delta": {"reasoning_content": "Планирую. ", "tool_calls": [{"index": 0, "id": "call_", "function": {"name": "fs.", "arguments": "{\"path\":"}}]}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "one", "function": {"name": "read", "arguments": "\"a.txt\"}"}}]}}]},
            {"choices": [], "usage": {"prompt_tokens": 31, "completion_tokens": 9, "completion_tokens_details": {"reasoning_tokens": 4}}},
        ]
        body = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "backend.models.openai_compatible.httpx.AsyncClient",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    adapter = OpenAICompatibleAdapter("http://api.test/v1", "tool-model")
    events = [event async for event in adapter.stream_chat(request_with_tools())]

    assert captured[0]["tools"][0]["function"]["name"] == "fs.write"
    assert captured[0]["stream_options"] == {"include_usage": True}
    assert captured[0]["max_tokens"] == 256
    reasoning = next(event for event in events if event.type == "reasoning_delta")
    usage = next(event for event in events if event.usage is not None)
    tool = next(event for event in events if event.tool_call is not None)
    assert reasoning.delta == "Планирую. "
    assert usage.usage is not None
    assert usage.usage.input_tokens == 31
    assert usage.usage.reasoning_tokens == 4
    assert tool.tool_call is not None
    assert tool.tool_call.id == "call_one"
    assert tool.tool_call.name == "fs.read"
    assert tool.tool_call.arguments == {"path": "a.txt"}


async def test_ollama_reads_and_caches_model_context_window(monkeypatch):
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        assert request.url.path == "/api/show"
        return httpx.Response(
            200,
            json={"model_info": {"qwen3.context_length": 131_072}},
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "backend.models.ollama.httpx.AsyncClient",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    adapter = OllamaAdapter("http://ollama.test", "qwen3")

    assert await adapter.context_window("qwen3") == 131_072
    assert await adapter.context_window("qwen3") == 131_072
    assert requests == 1
