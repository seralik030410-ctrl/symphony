from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field

from backend.storage.repository import ConflictError, NotFoundError
from backend.voice.contracts import VoiceError, VoiceState
from backend.voice.gateway import MAX_AUDIO_BYTES


router = APIRouter(prefix="/api/voice", tags=["voice"])


class VoiceSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["auto", "omni", "modular"] | None = None
    realtime_profile_id: str | None = Field(default=None, max_length=64)
    realtime_model: str | None = Field(default=None, min_length=1, max_length=200)
    input_codec: Literal["pcm16"] | None = None
    output_codec: Literal["pcm16"] | None = None
    sample_rate: int | None = Field(default=None, ge=8000, le=48000)
    server_vad: bool | None = None
    tool_support: bool | None = None
    stt_profile_id: str | None = Field(default=None, max_length=64)
    tts_profile_id: str | None = Field(default=None, max_length=64)
    stt_model: str | None = Field(default=None, min_length=1, max_length=200)
    tts_model: str | None = Field(default=None, min_length=1, max_length=200)
    language: str | None = Field(default=None, min_length=2, max_length=20)
    voice: str | None = Field(default=None, min_length=1, max_length=100)
    input_device_id: str | None = Field(default=None, max_length=500)
    output_device_id: str | None = Field(default=None, max_length=500)
    vad_threshold: float | None = Field(default=None, ge=0.001, le=1)
    vad_silence_ms: int | None = Field(default=None, ge=200, le=5000)
    save_audio: bool | None = None


def _runtime(request: Request, session_id: str) -> Any:
    runtime = request.app.state.runtime
    runtime.repository.get_session(session_id, include_history=False)
    return runtime


def _error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 409 if isinstance(exc, ConflictError) else 422, detail=str(exc))


@router.get("/sessions/{session_id}/settings")
async def get_voice_settings(session_id: str, request: Request) -> dict[str, Any]:
    try: return _runtime(request, session_id).voice.store.settings(session_id)
    except (NotFoundError, VoiceError) as exc: raise _error(exc) from exc


@router.put("/sessions/{session_id}/settings")
async def update_voice_settings(session_id: str, payload: VoiceSettingsUpdate, request: Request) -> dict[str, Any]:
    try:
        return _runtime(request, session_id).voice.store.update_settings(session_id, payload.model_dump(exclude_unset=True))
    except (NotFoundError, ConflictError, VoiceError) as exc: raise _error(exc) from exc


@router.get("/sessions/{session_id}/latest")
async def latest_voice_session(session_id: str, request: Request) -> dict[str, Any] | None:
    try: return _runtime(request, session_id).voice.store.latest(session_id)
    except NotFoundError as exc: raise _error(exc) from exc


@router.get("/sessions/{session_id}/{voice_id}/events")
async def voice_events(session_id: str, voice_id: str, request: Request, after: int = 0) -> list[dict[str, Any]]:
    try: return _runtime(request, session_id).voice.store.events(session_id, voice_id, max(0, after))
    except NotFoundError as exc: raise _error(exc) from exc


@router.websocket("/sessions/{session_id}/stream")
async def voice_stream(session_id: str, websocket: WebSocket) -> None:
    runtime = websocket.app.state.runtime
    origin, host = websocket.headers.get("origin", ""), websocket.headers.get("host", "")
    allowed_origins = set(runtime.settings.cors_origins) | {f"http://{host}", f"https://{host}"}
    if origin and origin not in allowed_origins:
        await websocket.close(code=4403, reason="Origin is not allowed")
        return
    try:
        runtime.repository.get_session(session_id, include_history=False)
    except NotFoundError:
        await websocket.close(code=4404, reason="Session not found")
        return
    await websocket.accept()
    voice = runtime.voice.store.create(session_id)
    send_lock = asyncio.Lock()

    async def send(payload: dict[str, Any]) -> None:
        async with send_lock: await websocket.send_json(payload)

    async def send_audio(payload: bytes) -> None:
        async with send_lock: await websocket.send_bytes(payload)

    await send({"type": "voice.session_started", "voice_session": voice})
    audio = bytearray(); mime_type = "audio/webm"; resolved_mode: str | None = None; input_sequence = 0
    try:
        while True:
            packet = await websocket.receive()
            if packet.get("type") == "websocket.disconnect": raise WebSocketDisconnect
            if packet.get("bytes") is not None:
                voice = runtime.voice.store.get(session_id, voice["id"])
                if voice["status"] != "listening":
                    await send({"type": "voice.error", "code": "not_listening", "message": "Start listening before sending audio"})
                    continue
                chunk = packet["bytes"]
                if resolved_mode == "omni":
                    input_sequence += 1
                    await runtime.voice.send_realtime_audio(voice, input_sequence, chunk)
                else:
                    if len(audio) + len(chunk) > MAX_AUDIO_BYTES:
                        audio.clear(); raise VoiceError("audio_too_large", "Voice input exceeded 25 MB")
                    audio.extend(chunk)
                continue
            message = packet.get("text")
            if not message: continue
            if len(message) > 4096:
                await websocket.close(code=4400, reason="Voice control message is too large"); return
            try: command = json.loads(message)
            except (ValueError, TypeError):
                await send({"type": "voice.error", "code": "invalid_control", "message": "Voice control must be valid JSON"}); continue
            if not isinstance(command, dict):
                await send({"type": "voice.error", "code": "invalid_control", "message": "Voice control must be an object"}); continue
            kind = command.get("type")
            if kind == "voice.start":
                voice = runtime.voice.store.get(session_id, voice["id"])
                if voice["status"] in {"listening", "transcribing", "thinking", "speaking"}:
                    await send({"type": "voice.error", "code": "invalid_state", "message": "Interrupt the active utterance before starting another"}); continue
                if voice["transcript_final"] or voice["status"] in {"cancelled", "interrupted", "error"}:
                    voice = runtime.voice.store.create(session_id)
                    await send({"type": "voice.session_started", "voice_session": voice})
                if voice["status"] in {"idle", "interrupted", "error"}:
                    voice = runtime.voice.store.transition(session_id, voice["id"], VoiceState.LISTENING)
                audio.clear(); input_sequence = 0
                negotiation = await runtime.voice.prepare(voice, command, send, send_audio)
                resolved_mode = negotiation["mode"]; mime_type = str(negotiation.get("mime_type") or command.get("mime_type") or "audio/webm")[:80]
                normalized_mime = mime_type.split(";", 1)[0].lower()
                if normalized_mime not in {"audio/pcm", "audio/webm", "audio/ogg", "audio/wav", "audio/mpeg", "audio/mp4"}:
                    raise VoiceError("invalid_audio_type", "Unsupported voice audio MIME type")
                await send({"type": "voice.mode_resolved", **negotiation})
                await send({"type": "voice.state_changed", "state": "listening"})
            elif kind == "voice.commit":
                voice = runtime.voice.store.get(session_id, voice["id"])
                if voice["status"] != "listening":
                    await send({"type": "voice.error", "code": "invalid_state", "message": "Voice session is not listening"}); continue
                if resolved_mode == "omni":
                    await runtime.voice.commit_realtime(voice)
                else:
                    payload = bytes(audio); audio.clear()
                    runtime.voice.start_task(voice, payload, mime_type, send, send_audio)
            elif kind == "voice.interrupt":
                voice = await runtime.voice.interrupt(session_id, voice["id"]); audio.clear(); resolved_mode = None
                await send({"type": "voice.playback_clear", "state": voice["status"]})
            elif kind == "voice.cancel":
                voice = await runtime.voice.interrupt(session_id, voice["id"])
                if voice["status"] != "cancelled": voice = runtime.voice.store.transition(session_id, voice["id"], VoiceState.CANCELLED)
                audio.clear(); resolved_mode = None; await send({"type": "voice.playback_clear", "state": "cancelled"})
                await websocket.close(code=1000); return
            elif kind == "voice.ping":
                await send({"type": "voice.pong"})
            else:
                await send({"type": "voice.error", "code": "unknown_control", "message": "Unknown voice control message"})
    except WebSocketDisconnect:
        pass
    except VoiceError as exc:
        with suppress(Exception): await send({"type": "voice.error", "code": exc.code, "message": str(exc)})
    except (ConflictError, NotFoundError) as exc:
        with suppress(Exception): await send({"type": "voice.error", "code": "invalid_state", "message": str(exc)})
    finally:
        audio.clear()
        with suppress(Exception):
            current = runtime.voice.store.get(session_id, voice["id"])
            if current["status"] not in {"idle", "interrupted", "cancelled", "error"}:
                await runtime.voice.interrupt(session_id, voice["id"])
