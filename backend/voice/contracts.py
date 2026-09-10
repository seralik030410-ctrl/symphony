from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, AsyncIterator, Literal


class VoiceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class VoiceState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"
    ERROR = "error"


VOICE_TRANSITIONS: dict[VoiceState, set[VoiceState]] = {
    VoiceState.IDLE: {VoiceState.LISTENING, VoiceState.CANCELLED},
    VoiceState.LISTENING: {VoiceState.TRANSCRIBING, VoiceState.INTERRUPTED, VoiceState.CANCELLED, VoiceState.ERROR},
    VoiceState.TRANSCRIBING: {VoiceState.THINKING, VoiceState.INTERRUPTED, VoiceState.CANCELLED, VoiceState.ERROR},
    VoiceState.THINKING: {VoiceState.SPEAKING, VoiceState.IDLE, VoiceState.INTERRUPTED, VoiceState.CANCELLED, VoiceState.ERROR},
    VoiceState.SPEAKING: {VoiceState.IDLE, VoiceState.INTERRUPTED, VoiceState.CANCELLED, VoiceState.ERROR},
    VoiceState.INTERRUPTED: {VoiceState.LISTENING, VoiceState.IDLE, VoiceState.CANCELLED},
    VoiceState.ERROR: {VoiceState.IDLE, VoiceState.LISTENING, VoiceState.CANCELLED},
    VoiceState.CANCELLED: set(),
}


@dataclass(slots=True)
class TranscriptChunk:
    text: str
    final: bool = False


@dataclass(slots=True)
class AudioChunk:
    data: bytes
    mime_type: str
    sample_rate: int | None = None


@dataclass(slots=True, frozen=True)
class RealtimeCapabilities:
    input_codecs: tuple[str, ...] = ("pcm16",)
    output_codecs: tuple[str, ...] = ("pcm16",)
    sample_rates: tuple[int, ...] = (24_000,)
    server_vad: bool = True
    tools: bool = True


@dataclass(slots=True, frozen=True)
class RealtimeConfig:
    model: str
    voice: str
    language: str
    input_codec: str
    output_codec: str
    sample_rate: int
    server_vad: bool
    tools: bool
    instructions: str = ""


@dataclass(slots=True)
class RealtimeEvent:
    type: Literal[
        "session_ready", "speech_started", "transcript_delta", "transcript_final",
        "text_delta", "audio_delta", "usage", "completed", "error", "disconnected",
    ]
    sequence: int
    text: str = ""
    audio: bytes = b""
    mime_type: str = "audio/pcm"
    sample_rate: int | None = None
    provider_session_id: str | None = None
    usage: dict[str, Any] | None = None
    error: str | None = None


class RealtimeConnection(ABC):
    @abstractmethod
    async def send_audio(self, sequence: int, audio: bytes) -> None: ...

    @abstractmethod
    async def commit(self) -> None: ...

    @abstractmethod
    async def cancel(self) -> None: ...

    @abstractmethod
    async def events(self) -> AsyncIterator[RealtimeEvent]: ...

    @abstractmethod
    async def close(self) -> None: ...


class RealtimeAdapter(ABC):
    @property
    @abstractmethod
    def capabilities(self) -> RealtimeCapabilities: ...

    @abstractmethod
    async def connect(self, config: RealtimeConfig) -> RealtimeConnection: ...


class STTAdapter(ABC):
    @abstractmethod
    async def transcribe(self, audio: bytes, *, mime_type: str, language: str, model: str) -> AsyncIterator[TranscriptChunk]:
        raise NotImplementedError


class TTSAdapter(ABC):
    @abstractmethod
    async def synthesize(self, text: str, *, voice: str, model: str) -> AudioChunk:
        raise NotImplementedError


class SentenceChunker:
    """Incrementally releases speakable sentences without waiting for the full answer."""

    def __init__(self, max_chars: int = 280) -> None:
        self.max_chars = max_chars
        self._buffer = ""

    def push(self, delta: str) -> list[str]:
        self._buffer += delta
        ready: list[str] = []
        while self._buffer:
            boundary = next((index + 1 for index, char in enumerate(self._buffer) if char in ".!?…\n"), None)
            if boundary is None and len(self._buffer) < self.max_chars:
                break
            if boundary is None:
                boundary = self._buffer.rfind(" ", 0, self.max_chars) or self.max_chars
            sentence, self._buffer = self._buffer[:boundary].strip(), self._buffer[boundary:].lstrip()
            if sentence:
                ready.append(sentence)
        return ready

    def flush(self) -> str:
        value, self._buffer = self._buffer.strip(), ""
        return value
