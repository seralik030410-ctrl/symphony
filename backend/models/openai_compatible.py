from __future__ import annotations

import asyncio
import json
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


class OpenAICompatibleAdapter(ModelAdapter):
    name = "openai"
    title = "OpenAI-compatible API"

    def __init__(
        self,
        base_url: str,
        default_model: str,
        api_key: str = "",
        *,
        profile_title: str = "OpenAI-compatible API",
        request_timeout: float = 120.0,
        discovery_timeout: float = 2.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.api_key = api_key
        self.title = profile_title
        self.request_timeout = request_timeout
        self.discovery_timeout = discovery_timeout
        self._cancelled: set[str] = set()

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=self.discovery_timeout, headers=self.headers) as client:
                response = await client.get(f"{self.base_url}/models")
                response.raise_for_status()
        except (httpx.HTTPError, OSError) as exc:
            raise ProviderError(
                f"OpenAI-compatible API is unavailable at {self.base_url}: {exc}",
                code="unavailable",
            ) from exc
        return sorted({item["id"] for item in response.json().get("data", []) if item.get("id")})

    def get_capabilities(self, model: str) -> ModelCapabilities:
        return ModelCapabilities(
            text=True,
            # Arbitrary compatible servers can alias any model name. Vision
            # stays off until an explicit capability profile is implemented.
            vision=False,
            native_tools=True,
            json_schema=False,
            max_context=131_072,
            max_output=4_096,
        )

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[ModelStreamEvent]:
        self._cancelled.discard(request.request_id)
        payload = {
            "model": request.model,
            "messages": request.messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": request.temperature,
            "max_tokens": request.max_output,
        }
        if request.tools:
            payload["tools"] = request.tools
        if request.response_json:
            payload["response_format"] = {"type": "json_object"}
        timeout = httpx.Timeout(self.request_timeout, connect=10.0)
        try:
            async with httpx.AsyncClient(timeout=timeout, headers=self.headers) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    pending_calls: dict[int, dict[str, str]] = {}
                    async for line in response.aiter_lines():
                        if request.request_id in self._cancelled:
                            raise asyncio.CancelledError
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            item = json.loads(data)
                            usage = item.get("usage") or {}
                            if usage:
                                details = usage.get("completion_tokens_details") or {}
                                yield ModelStreamEvent(
                                    type="usage",
                                    usage=TokenUsage(
                                        input_tokens=int(usage.get("prompt_tokens") or 0),
                                        output_tokens=int(usage.get("completion_tokens") or 0),
                                        reasoning_tokens=int(details.get("reasoning_tokens") or 0),
                                    ),
                                )
                            choices = item.get("choices") or []
                            if not choices:
                                continue
                            choice = choices[0]
                            event_delta = choice.get("delta", {})
                            delta = event_delta.get("content", "") or ""
                        except (json.JSONDecodeError, IndexError, TypeError) as exc:
                            raise ProviderError(
                                "OpenAI-compatible API returned an invalid SSE event",
                                code="invalid_stream",
                            ) from exc
                        if delta:
                            yield ModelStreamEvent(type="text_delta", delta=delta)
                        reasoning = (
                            event_delta.get("reasoning_content")
                            or event_delta.get("reasoning")
                            or event_delta.get("thinking")
                            or ""
                        )
                        if isinstance(reasoning, str) and reasoning:
                            yield ModelStreamEvent(type="reasoning_delta", delta=reasoning)
                        for fragment in event_delta.get("tool_calls", []) or []:
                            index = int(fragment.get("index", 0))
                            pending = pending_calls.setdefault(
                                index,
                                {"id": "", "name": "", "arguments": ""},
                            )
                            pending["id"] += fragment.get("id", "") or ""
                            function = fragment.get("function", {}) or {}
                            pending["name"] += function.get("name", "") or ""
                            pending["arguments"] += function.get("arguments", "") or ""
                    for index, pending in sorted(pending_calls.items()):
                        try:
                            arguments = json.loads(pending["arguments"] or "{}")
                        except json.JSONDecodeError as exc:
                            raise ProviderError(
                                "OpenAI-compatible API returned invalid tool arguments",
                                code="invalid_tool_arguments",
                            ) from exc
                        yield ModelStreamEvent(
                            type="tool_call",
                            tool_call=ToolCall(
                                id=pending["id"] or f"{request.request_id}-tool-{index}",
                                name=pending["name"],
                                arguments=arguments,
                            ),
                        )
        except asyncio.CancelledError:
            raise
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise ProviderError(
                f"OpenAI-compatible API returned HTTP {exc.response.status_code}: {detail}",
                code="http_error",
            ) from exc
        except httpx.ReadTimeout as exc:
            raise ProviderError(
                f"OpenAI-compatible API did not send data for {self.request_timeout:g} seconds. Retry the turn or check the provider.",
                code="timeout",
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"Cannot connect to OpenAI-compatible API at {self.base_url}.",
                code="unavailable",
            ) from exc
        except (httpx.HTTPError, OSError) as exc:
            detail = str(exc).strip() or exc.__class__.__name__
            raise ProviderError(
                f"OpenAI-compatible API connection failed at {self.base_url}: {detail}",
                code="unavailable",
            ) from exc
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
            return True, "API is reachable, but returned no models"
        return True, f"{len(models)} model(s) available"
