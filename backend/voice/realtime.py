from __future__ import annotations

import base64
import asyncio
import json
from collections import deque
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from backend.voice.contracts import (
    RealtimeAdapter, RealtimeCapabilities, RealtimeConfig, RealtimeConnection, RealtimeEvent, VoiceError,
)


def _realtime_url(base_url: str, model: str) -> str:
    parsed = urlsplit(base_url.rstrip("/"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = parsed.path.rstrip("/")
    if not path.endswith("/realtime"):
        path += "/realtime"
    return urlunsplit((scheme, parsed.netloc, path, urlencode({"model": model}), ""))


class OpenAIRealtimeConnection(RealtimeConnection):
    def __init__(self, socket: ClientConnection, config: RealtimeConfig) -> None:
        self.socket, self.config = socket, config
        self._input_sequence = 0
        self._event_sequence = 0
        self._seen: set[str] = set()
        self._pending: deque[RealtimeEvent] = deque()
        self._closed = False
        self._buffer_committed = False

    async def configure(self) -> None:
        turn_detection: dict[str, Any] | None = {"type": "server_vad", "create_response": True, "interrupt_response": True} if self.config.server_vad else None
        audio_format = {"type": "audio/pcm", "rate": self.config.sample_rate}
        session: dict[str, Any] = {
            "type": "realtime",
            "model": self.config.model,
            "output_modalities": ["audio"],
            "audio": {
                "input": {
                    "format": audio_format,
                    "transcription": {"model": "gpt-4o-mini-transcribe", "language": self.config.language},
                    "turn_detection": turn_detection,
                },
                "output": {"format": audio_format, "voice": "alloy" if self.config.voice == "default" else self.config.voice},
            },
        }
        if self.config.instructions:
            session["instructions"] = self.config.instructions
        await self._send({"type": "session.update", "session": session})
        async with asyncio.timeout(20):
            while True:
                value = json.loads(await self.socket.recv())
                if value.get("type") == "error":
                    raise VoiceError("realtime_configuration", str((value.get("error") or {}).get("message") or "Realtime configuration rejected"))
                if value.get("type") == "session.updated":
                    session_id = str((value.get("session") or {}).get("id") or "") or None
                    self._pending.append(self._event("session_ready", provider_session_id=session_id))
                    break

    async def _send(self, value: dict[str, Any]) -> None:
        if self._closed:
            raise VoiceError("realtime_closed", "Realtime provider session is closed")
        await self.socket.send(json.dumps(value, separators=(",", ":")))

    async def send_audio(self, sequence: int, audio: bytes) -> None:
        if sequence != self._input_sequence + 1:
            raise VoiceError("audio_sequence", f"Expected input audio sequence {self._input_sequence + 1}, received {sequence}")
        self._input_sequence = sequence
        await self._send({"type": "input_audio_buffer.append", "audio": base64.b64encode(audio).decode("ascii")})

    async def commit(self) -> None:
        if not self._buffer_committed:
            await self._send({"type": "input_audio_buffer.commit"})
            self._buffer_committed = True
            await self._send({"type": "response.create"})

    async def cancel(self) -> None:
        if not self._closed:
            try:
                await self._send({"type": "response.cancel"})
            except ConnectionClosed:
                pass

    def _event(self, kind: str, **values: Any) -> RealtimeEvent:
        self._event_sequence += 1
        return RealtimeEvent(type=kind, sequence=self._event_sequence, **values)  # type: ignore[arg-type]

    async def events(self) -> AsyncIterator[RealtimeEvent]:
        while self._pending:
            yield self._pending.popleft()
        try:
            async for raw in self.socket:
                if not isinstance(raw, str):
                    continue
                value = json.loads(raw)
                event_id = str(value.get("event_id") or "")
                if event_id and event_id in self._seen:
                    continue
                if event_id:
                    self._seen.add(event_id)
                kind = value.get("type")
                if kind in {"session.created", "session.updated"}:
                    session = value.get("session") or {}
                    yield self._event("session_ready", provider_session_id=str(session.get("id") or "") or None)
                elif kind == "input_audio_buffer.speech_started":
                    yield self._event("speech_started")
                elif kind == "input_audio_buffer.committed":
                    self._buffer_committed = True
                elif kind == "conversation.item.input_audio_transcription.delta":
                    yield self._event("transcript_delta", text=str(value.get("delta") or ""))
                elif kind == "conversation.item.input_audio_transcription.completed":
                    yield self._event("transcript_final", text=str(value.get("transcript") or ""))
                elif kind in {"response.output_audio_transcript.delta", "response.audio_transcript.delta", "response.output_text.delta"}:
                    yield self._event("text_delta", text=str(value.get("delta") or ""))
                elif kind in {"response.output_audio.delta", "response.audio.delta"}:
                    try:
                        audio = base64.b64decode(value.get("delta") or "", validate=True)
                    except (ValueError, TypeError) as exc:
                        raise VoiceError("invalid_provider_audio", "Realtime provider returned invalid audio") from exc
                    yield self._event("audio_delta", audio=audio, sample_rate=self.config.sample_rate)
                elif kind == "response.done":
                    response = value.get("response") or {}
                    usage = response.get("usage") or {}
                    if usage:
                        yield self._event("usage", usage=usage)
                    if response.get("status") in {"failed", "cancelled", "incomplete"}:
                        details = response.get("status_details") or {}
                        yield self._event("error", error=str(details.get("error", {}).get("message") or details.get("reason") or response.get("status")))
                    else:
                        yield self._event("completed")
                elif kind == "error":
                    error = value.get("error") or {}
                    yield self._event("error", error=str(error.get("message") or "Realtime provider error"))
        except ConnectionClosed as exc:
            if not self._closed:
                yield self._event("disconnected", error=f"Realtime provider disconnected ({exc.code})")
        finally:
            self._closed = True

    async def close(self) -> None:
        self._closed = True
        await self.socket.close()


class OpenAICompatibleRealtimeAdapter(RealtimeAdapter):
    def __init__(self, endpoint: dict[str, Any]) -> None:
        self.endpoint = endpoint
        config = endpoint.get("config") or {}
        self._capabilities = RealtimeCapabilities(
            input_codecs=tuple(config.get("realtime_input_codecs") or ("pcm16",)),
            output_codecs=tuple(config.get("realtime_output_codecs") or ("pcm16",)),
            sample_rates=tuple(int(x) for x in (config.get("realtime_sample_rates") or (24_000,))),
            server_vad=bool(config.get("realtime_server_vad", True)),
            tools=False,
        )

    @property
    def capabilities(self) -> RealtimeCapabilities:
        return self._capabilities

    async def connect(self, config: RealtimeConfig) -> RealtimeConnection:
        headers = {"Authorization": f"Bearer {self.endpoint['api_key']}"} if self.endpoint.get("api_key") else {}
        try:
            socket = await connect(
                _realtime_url(self.endpoint["base_url"], config.model),
                additional_headers=headers,
                open_timeout=min(float(self.endpoint.get("timeout", 20)), 20),
                max_size=4_000_000,
                ping_interval=20,
            )
            connection = OpenAIRealtimeConnection(socket, config)
            try:
                await connection.configure()
            except BaseException:
                await socket.close()
                raise
            return connection
        except (OSError, TimeoutError, ConnectionClosed) as exc:
            raise VoiceError("realtime_unavailable", f"Realtime provider connection failed: {exc}") from exc


class MockRealtimeConnection(RealtimeConnection):
    """Deterministic protocol double used by later ordering and lifecycle tests."""
    def __init__(self, config: RealtimeConfig, transcript: str, answer: str) -> None:
        self.config, self.transcript, self.answer = config, transcript, answer
        self.received: list[bytes] = []; self.cancelled = False; self._last_sequence = 0
        self._events: asyncio.Queue[RealtimeEvent | None] = asyncio.Queue()
        self._events.put_nowait(RealtimeEvent("session_ready", 1, provider_session_id="mock-realtime"))

    async def send_audio(self, sequence: int, audio: bytes) -> None:
        if sequence != self._last_sequence + 1: raise VoiceError("audio_sequence", "Mock realtime input is out of order")
        self._last_sequence = sequence; self.received.append(audio)

    async def commit(self) -> None:
        for event in (
            RealtimeEvent("transcript_final", 2, text=self.transcript),
            RealtimeEvent("text_delta", 3, text=self.answer),
            RealtimeEvent("audio_delta", 4, audio=b"\0\0" * 2400, sample_rate=self.config.sample_rate),
            RealtimeEvent("usage", 5, usage={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}),
            RealtimeEvent("completed", 6), None,
        ): self._events.put_nowait(event)

    async def cancel(self) -> None: self.cancelled = True
    async def events(self) -> AsyncIterator[RealtimeEvent]:
        while (event := await self._events.get()) is not None: yield event
    async def close(self) -> None: self._events.put_nowait(None)


class MockRealtimeAdapter(RealtimeAdapter):
    def __init__(self, transcript: str = "Проверка Omni", answer: str = "Omni работает.") -> None:
        self.transcript, self.answer = transcript, answer
        self.last_connection: MockRealtimeConnection | None = None
    @property
    def capabilities(self) -> RealtimeCapabilities: return RealtimeCapabilities()
    async def connect(self, config: RealtimeConfig) -> RealtimeConnection:
        self.last_connection = MockRealtimeConnection(config, self.transcript, self.answer); return self.last_connection
