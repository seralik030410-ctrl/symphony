from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator

import httpx

from backend.models.base import (
    ChatRequest,
    ModelAdapter,
    ModelCapabilities,
    ModelStreamEvent,
    ProviderError,
    TokenUsage,
    ToolCall,
)


class OllamaAdapter(ModelAdapter):
    name = "ollama"
    title = "Ollama"

    def __init__(
        self,
        base_url: str,
        default_model: str,
        *,
        request_timeout: float = 120.0,
        discovery_timeout: float = 2.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.request_timeout = request_timeout
        self.discovery_timeout = discovery_timeout
        self._cancelled: set[str] = set()
        self._context_windows: dict[str, int] = {}
        self._vision_models: set[str] = set()
        self._discovered_at: dict[str, float] = {}
        self._thinking_models: dict[str, bool] = {}

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=self.discovery_timeout) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
        except (httpx.HTTPError, OSError) as exc:
            raise ProviderError(f"Ollama is unavailable at {self.base_url}: {exc}", code="unavailable") from exc
        return sorted(
            {
                item.get("name") or item.get("model")
                for item in response.json().get("models", [])
                if item.get("name") or item.get("model")
            }
        )

    def get_capabilities(self, model: str) -> ModelCapabilities:
        return ModelCapabilities(
            text=True,
            vision=model in self._vision_models,
            native_tools=True,
            reasoning_stream=True,
            max_context=self._context_windows.get(model, 16_384),
            max_output=2_048,
        )

    async def context_window(self, model: str) -> int:
        cached = self._context_windows.get(model)
        if cached is not None and time.monotonic() - self._discovered_at.get(model, 0) < 300:
            return cached
        try:
            async with httpx.AsyncClient(timeout=self.discovery_timeout) as client:
                response = await client.post(f"{self.base_url}/api/show", json={"model": model})
                response.raise_for_status()
            metadata = response.json()
            if isinstance(metadata.get("capabilities"), list):
                self._thinking_models[model] = "thinking" in metadata["capabilities"]
            if "vision" in metadata.get("capabilities", []):
                self._vision_models.add(model)
            else:
                self._vision_models.discard(model)
            model_info = metadata.get("model_info", {})
            candidates = [
                int(value)
                for key, value in model_info.items()
                if str(key).endswith(".context_length") and isinstance(value, (int, float))
            ]
            context_window = max(candidates) if candidates else self.get_capabilities(model).max_context
        except (httpx.HTTPError, OSError, ValueError, TypeError):
            return self.get_capabilities(model).max_context
        context_window = min(1_048_576, max(1_024, context_window))
        self._context_windows[model] = context_window
        self._discovered_at[model] = time.monotonic()
        return context_window

    async def resolve_capabilities(self, model: str) -> ModelCapabilities:
        await self.context_window(model)
        return self.get_capabilities(model)

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[ModelStreamEvent]:
        self._cancelled.discard(request.request_id)
        messages: list[dict[str, object]] = []
        for source in request.messages:
            message = dict(source)
            if "tool_calls" in message:
                normalized_calls = []
                for source_call in message["tool_calls"]:
                    tool_call = dict(source_call)
                    function = dict(tool_call.get("function", {}))
                    arguments = function.get("arguments", {})
                    if isinstance(arguments, str):
                        try:
                            function["arguments"] = json.loads(arguments)
                        except json.JSONDecodeError:
                            function["arguments"] = {}
                    tool_call["function"] = function
                    normalized_calls.append(tool_call)
                message["tool_calls"] = normalized_calls
            messages.append(message)
        payload = {
            "model": request.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_output,
                "num_ctx": request.context_window,
            },
        }
        if request.tools:
            payload["tools"] = request.tools
        if request.thinking is not None:
            payload["think"] = request.thinking
        elif self._thinking_models.get(request.model, True):
            payload["think"] = True
        if request.response_json:
            payload["format"] = "json"
        timeout = httpx.Timeout(self.request_timeout, connect=10.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if request.request_id in self._cancelled:
                            raise asyncio.CancelledError
                        if not line:
                            continue
                        try:
                            item = json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise ProviderError("Ollama returned invalid streaming JSON", code="invalid_stream") from exc
                        if item.get("error"):
                            raise ProviderError(str(item["error"]), code="provider_response_error")
                        message = item.get("message", {})
                        reasoning = message.get("thinking", "") or ""
                        if reasoning:
                            yield ModelStreamEvent(type="reasoning_delta", delta=reasoning)
                        delta = message.get("content", "")
                        if delta:
                            yield ModelStreamEvent(type="text_delta", delta=delta)
                        for index, tool_call in enumerate(message.get("tool_calls", [])):
                            function = tool_call.get("function", {})
                            arguments = function.get("arguments", {})
                            if isinstance(arguments, str):
                                try:
                                    arguments = json.loads(arguments)
                                except json.JSONDecodeError as exc:
                                    raise ProviderError(
                                        "Ollama returned invalid tool arguments",
                                        code="invalid_tool_arguments",
                                    ) from exc
                            yield ModelStreamEvent(
                                type="tool_call",
                                tool_call=ToolCall(
                                    id=tool_call.get("id") or f"{request.request_id}-tool-{index}",
                                    name=str(function.get("name", "")),
                                    arguments=arguments,
                                ),
                            )
                        if item.get("done"):
                            yield ModelStreamEvent(
                                type="usage",
                                usage=TokenUsage(
                                    input_tokens=int(item.get("prompt_eval_count") or 0),
                                    output_tokens=int(item.get("eval_count") or 0),
                                ),
                            )
                            break
        except asyncio.CancelledError:
            raise
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise ProviderError(
                f"Ollama returned HTTP {exc.response.status_code}: {detail}",
                code="http_error",
            ) from exc
        except httpx.ReadTimeout as exc:
            raise ProviderError(
                f"Ollama did not send data for {self.request_timeout:g} seconds. The model may be overloaded; retry the turn.",
                code="timeout",
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"Cannot connect to Ollama at {self.base_url}. Check that Ollama is running.",
                code="unavailable",
            ) from exc
        except (httpx.HTTPError, OSError) as exc:
            detail = str(exc).strip() or exc.__class__.__name__
            raise ProviderError(f"Ollama connection failed at {self.base_url}: {detail}", code="unavailable") from exc
        finally:
            self._cancelled.discard(request.request_id)

    async def cancel(self, request_id: str) -> None:
        self._cancelled.add(request_id)

    async def health(self) -> tuple[bool, str]:
        try:
            models = await self.list_models()
        except ProviderError as exc:
            return False, str(exc)
        if not models:
            return True, "Ollama is running, but no models are installed"
        return True, f"{len(models)} model(s) available"
