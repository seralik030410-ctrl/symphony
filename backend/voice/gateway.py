from __future__ import annotations

import io
import math
import struct
import wave
from collections.abc import AsyncIterator
from typing import Any

import httpx

from backend.models.base import Capability
from backend.providers.registry import ProviderRegistry
from backend.voice.contracts import AudioChunk, RealtimeAdapter, STTAdapter, TTSAdapter, TranscriptChunk, VoiceError
from backend.voice.realtime import OpenAICompatibleRealtimeAdapter


MAX_AUDIO_BYTES = 25_000_000


class MockSTTAdapter(STTAdapter):
    async def transcribe(self, audio: bytes, *, mime_type: str, language: str, model: str) -> AsyncIterator[TranscriptChunk]:
        try:
            text = audio.decode("utf-8") if audio.startswith(b"mock:") else ""
            text = text.removeprefix("mock:").strip() or "Проверка голосового режима"
        except UnicodeDecodeError:
            text = "Проверка голосового режима"
        words = text.split()
        for index in range(1, len(words)):
            yield TranscriptChunk(" ".join(words[:index]), final=False)
        yield TranscriptChunk(text, final=True)


class MockTTSAdapter(TTSAdapter):
    async def synthesize(self, text: str, *, voice: str, model: str) -> AudioChunk:
        rate = 16_000
        duration = min(1.2, max(0.12, len(text) * 0.012))
        output = io.BytesIO()
        with wave.open(output, "wb") as target:
            target.setnchannels(1); target.setsampwidth(2); target.setframerate(rate)
            frames = bytearray()
            for index in range(int(rate * duration)):
                envelope = max(0.0, 1.0 - index / (rate * duration))
                frames.extend(struct.pack("<h", int(2200 * envelope * math.sin(2 * math.pi * 330 * index / rate))))
            target.writeframes(bytes(frames))
        return AudioChunk(output.getvalue(), "audio/wav", rate)


class OpenAICompatibleSTTAdapter(STTAdapter):
    def __init__(self, endpoint: dict[str, Any]) -> None:
        self.endpoint = endpoint

    async def transcribe(self, audio: bytes, *, mime_type: str, language: str, model: str) -> AsyncIterator[TranscriptChunk]:
        if not audio or len(audio) > MAX_AUDIO_BYTES:
            raise VoiceError("invalid_audio", "Voice input must contain between 1 byte and 25 MB")
        extension = {"audio/webm": "webm", "audio/wav": "wav", "audio/mpeg": "mp3", "audio/ogg": "ogg", "audio/mp4": "m4a"}.get(mime_type, "webm")
        headers = {"Authorization": f"Bearer {self.endpoint['api_key']}"} if self.endpoint["api_key"] else {}
        try:
            async with httpx.AsyncClient(timeout=self.endpoint["timeout"], headers=headers, trust_env=False) as client:
                response = await client.post(
                    f"{self.endpoint['base_url']}/audio/transcriptions",
                    data={"model": model or self.endpoint["model"], "language": language, "response_format": "json"},
                    files={"file": (f"voice.{extension}", audio, mime_type)},
                )
                response.raise_for_status()
                text = str(response.json().get("text", "")).strip()
        except (httpx.HTTPError, OSError, ValueError) as exc:
            raise VoiceError("stt_unavailable", f"Speech transcription failed: {exc}") from exc
        if not text:
            raise VoiceError("empty_transcript", "Speech service returned an empty transcript")
        yield TranscriptChunk(text, final=True)


class LocalCompatibleSTTAdapter(OpenAICompatibleSTTAdapter):
    pass


class OpenAICompatibleTTSAdapter(TTSAdapter):
    def __init__(self, endpoint: dict[str, Any]) -> None:
        self.endpoint = endpoint

    async def synthesize(self, text: str, *, voice: str, model: str) -> AudioChunk:
        headers = {"Authorization": f"Bearer {self.endpoint['api_key']}"} if self.endpoint["api_key"] else {}
        try:
            async with httpx.AsyncClient(timeout=self.endpoint["timeout"], headers=headers, trust_env=False) as client:
                response = await client.post(
                    f"{self.endpoint['base_url']}/audio/speech",
                    json={"model": model or self.endpoint["model"], "voice": voice, "input": text, "response_format": "mp3"},
                )
                response.raise_for_status()
                if len(response.content) > MAX_AUDIO_BYTES:
                    raise VoiceError("tts_too_large", "Speech audio exceeded 25 MB")
        except VoiceError:
            raise
        except (httpx.HTTPError, OSError) as exc:
            raise VoiceError("tts_unavailable", f"Speech synthesis failed: {exc}") from exc
        return AudioChunk(response.content, response.headers.get("content-type", "audio/mpeg").split(";", 1)[0])


class LocalCompatibleTTSAdapter(OpenAICompatibleTTSAdapter):
    pass


class VoiceGateway:
    def __init__(self, providers: ProviderRegistry) -> None:
        self.providers = providers
        self._realtime_overrides: dict[str, RealtimeAdapter] = {}

    def register_realtime(self, profile_id: str, adapter: RealtimeAdapter) -> None:
        """Register a vendor adapter without adding provider branches to VoiceService."""
        self._realtime_overrides[profile_id] = adapter

    def realtime(self, profile_id: str) -> RealtimeAdapter:
        override = self._realtime_overrides.get(profile_id)
        if override is not None:
            return override
        return OpenAICompatibleRealtimeAdapter(self.providers.realtime_endpoint(profile_id))

    def stt(self, profile_id: str | None) -> STTAdapter:
        if not profile_id:
            return MockSTTAdapter()
        endpoint = self.providers.speech_endpoint(profile_id, Capability.AUDIO_TRANSCRIPTION)
        return LocalCompatibleSTTAdapter(endpoint) if endpoint["is_local"] else OpenAICompatibleSTTAdapter(endpoint)

    def tts(self, profile_id: str | None) -> TTSAdapter:
        if not profile_id:
            return MockTTSAdapter()
        endpoint = self.providers.speech_endpoint(profile_id, Capability.AUDIO_SYNTHESIS)
        return LocalCompatibleTTSAdapter(endpoint) if endpoint["is_local"] else OpenAICompatibleTTSAdapter(endpoint)
