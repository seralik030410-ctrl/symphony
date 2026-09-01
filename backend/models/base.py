from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, code: str = "provider_error") -> None:
        super().__init__(message)
        self.code = code


@dataclass(slots=True)
class ModelCapabilities:
    text: bool = True
    vision: bool = False
    native_tools: bool = False
    json_schema: bool = False
    reasoning_stream: bool = False
    max_context: int = 16_384
    max_output: int = 2_048


@dataclass(slots=True)
class ChatRequest:
    request_id: str
    model: str
    messages: list[dict[str, Any]]
    max_output: int
    temperature: float = 0.7
    tools: list[dict[str, Any]] | None = None
    context_window: int = 16_384
    response_json: bool = False
    thinking: bool | None = None


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(slots=True)
class ModelStreamEvent:
    type: Literal["text_delta", "reasoning_delta", "tool_call", "usage"]
    delta: str = ""
    tool_call: ToolCall | None = None
    usage: TokenUsage | None = None


class ModelAdapter(ABC):
    name: str
    title: str
    base_url: str
    default_model: str

    @abstractmethod
    async def list_models(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def get_capabilities(self, model: str) -> ModelCapabilities:
        raise NotImplementedError

    @abstractmethod
    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[ModelStreamEvent]:
        raise NotImplementedError

    @abstractmethod
    async def cancel(self, request_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> tuple[bool, str]:
        raise NotImplementedError

    async def context_window(self, model: str) -> int:
        return self.get_capabilities(model).max_context

    async def resolve_capabilities(self, model: str) -> ModelCapabilities:
        return self.get_capabilities(model)

    def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        from backend.models.tokens import estimate_tokens
        return estimate_tokens(messages)
