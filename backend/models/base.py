from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, AsyncIterator, ClassVar, Literal


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, code: str = "provider_error") -> None:
        super().__init__(message)
        self.code = code


class Capability(StrEnum):
    TEXT_CHAT = "text.chat"
    VISION_IMAGES = "vision.images"
    VISION_LIVE_FRAMES = "vision.live_frames"
    AUDIO_TRANSCRIPTION = "audio.transcription"
    AUDIO_SYNTHESIS = "audio.synthesis"
    AUDIO_REALTIME = "audio.realtime"
    MEDIA_IMAGE_GENERATION = "media.image_generation"
    MEDIA_VIDEO_GENERATION = "media.video_generation"


@dataclass(slots=True)
class ModelCapabilities:
    text: bool = True
    vision: bool = False
    native_tools: bool = False
    json_schema: bool = False
    reasoning_stream: bool = False
    vision_live_frames: bool = False
    audio_transcription: bool = False
    audio_synthesis: bool = False
    audio_realtime: bool = False
    media_image_generation: bool = False
    media_video_generation: bool = False
    max_context: int = 16_384
    max_output: int = 2_048
    # Vision limits are model constraints, not client preferences.  Providers
    # may override them through the existing capability override path.
    max_vision_frames: int = 8
    max_image_bytes: int = 10_000_000
    max_image_width: int = 4_096
    max_image_height: int = 4_096
    max_image_tokens: int = 2_048
    max_vision_tokens: int = 8_192

    _FIELDS: ClassVar[dict[Capability, str]] = {
        Capability.TEXT_CHAT: "text",
        Capability.VISION_IMAGES: "vision",
        Capability.VISION_LIVE_FRAMES: "vision_live_frames",
        Capability.AUDIO_TRANSCRIPTION: "audio_transcription",
        Capability.AUDIO_SYNTHESIS: "audio_synthesis",
        Capability.AUDIO_REALTIME: "audio_realtime",
        Capability.MEDIA_IMAGE_GENERATION: "media_image_generation",
        Capability.MEDIA_VIDEO_GENERATION: "media_video_generation",
    }

    def supports(self, capability: Capability | str) -> bool:
        return bool(getattr(self, self._FIELDS[Capability(capability)]))

    def set_support(self, capability: Capability | str, enabled: bool) -> None:
        setattr(self, self._FIELDS[Capability(capability)], bool(enabled))

    def capability_map(self) -> dict[str, bool]:
        return {capability.value: self.supports(capability) for capability in Capability}


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
