from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from backend.agent.turn_service import TurnService
from backend.models.base import ProviderError
from backend.providers.secrets import SecretStore
from backend.runtime.contracts import ResourceClaim, ResourceClass, ResourceRequestStatus
from backend.runtime.resources import ResourceCoordinator
from backend.storage.database import Database, utc_now
from backend.storage.repository import ConflictError, FINAL_TURN_STATUSES, NotFoundError, Repository
from backend.voice.contracts import RealtimeConfig, RealtimeConnection, RealtimeEvent, SentenceChunker, VOICE_TRANSITIONS, VoiceError, VoiceState
from backend.voice.gateway import MAX_AUDIO_BYTES, VoiceGateway
from backend.media.assets import MediaAssetStore


Send = Callable[[dict[str, Any]], Awaitable[None]]
SendAudio = Callable[[bytes], Awaitable[None]]


@dataclass(slots=True)
class OmniController:
    connection: RealtimeConnection
    send: Send
    send_audio: SendAudio
    task: asyncio.Task[None] | None = None
    committed: bool = False
    turn_id: str | None = None
    assistant_message_id: str | None = None
    pending_text: list[str] = field(default_factory=list)
    input_bytes: int = 0
    response_done: bool = False
    finished: bool = False


class VoiceStore:
    def __init__(self, database: Database, repository: Repository) -> None:
        self.database, self.repository = database, repository

    @staticmethod
    def _session(row: Any) -> dict[str, Any]:
        value = dict(row); value["transcript_final"] = bool(value["transcript_final"])
        if value.get("usage_json"):
            value["usage"] = json.loads(value.pop("usage_json"))
        else:
            value.pop("usage_json", None); value["usage"] = None
        return value

    @staticmethod
    def _settings(row: Any) -> dict[str, Any]:
        value = dict(row)
        for key in ("save_audio", "server_vad", "tool_support"):
            if key in value: value[key] = bool(value[key])
        return value

    def settings(self, session_id: str) -> dict[str, Any]:
        self.repository.get_session(session_id, include_history=False)
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO voice_settings(session_id,updated_at) VALUES(?,?)", (session_id, utc_now())
            )
            row = connection.execute("SELECT * FROM voice_settings WHERE session_id=?", (session_id,)).fetchone()
        return self._settings(row)

    def update_settings(self, session_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        self.settings(session_id)
        allowed = {"mode", "realtime_profile_id", "realtime_model", "input_codec", "output_codec", "sample_rate",
                   "server_vad", "tool_support", "stt_profile_id", "tts_profile_id", "stt_model", "tts_model",
                   "language", "voice", "input_device_id", "output_device_id", "vad_threshold", "vad_silence_ms", "save_audio"}
        nullable = {"realtime_profile_id", "stt_profile_id", "tts_profile_id", "input_device_id", "output_device_id"}
        if any(value is None and key in allowed - nullable for key, value in changes.items()):
            raise VoiceError("invalid_settings", "This voice setting cannot be null")
        values = {key: int(value) if key in {"save_audio", "server_vad", "tool_support"} else value for key, value in changes.items() if key in allowed}
        if not values: return self.settings(session_id)
        values["updated_at"] = utc_now()
        with self.database.transaction() as connection:
            for key in ("realtime_profile_id", "stt_profile_id", "tts_profile_id"):
                profile_id = values.get(key)
                if profile_id and not connection.execute("SELECT 1 FROM provider_profiles WHERE id=?", (profile_id,)).fetchone():
                    raise NotFoundError("Provider profile not found")
            connection.execute(
                f"UPDATE voice_settings SET {','.join(f'{key}=?' for key in values)} WHERE session_id=?",
                (*values.values(), session_id),
            )
        return self.settings(session_id)

    def configure_runtime(self, session_id: str, voice_id: str, *, requested_mode: str, resolved_mode: str,
                          profile_id: str | None = None, provider_session_id: str | None = None) -> dict[str, Any]:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE voice_sessions SET requested_mode=?,resolved_mode=?,provider_profile_id=?,provider_session_id=COALESCE(?,provider_session_id),updated_at=? WHERE id=? AND session_id=?",
                (requested_mode, resolved_mode, profile_id, provider_session_id, utc_now(), voice_id, session_id),
            )
            if cursor.rowcount != 1: raise NotFoundError("Voice session not found in this chat")
        return self.get(session_id, voice_id)

    def audio_sequence(self, session_id: str, voice_id: str, direction: str, sequence: int) -> None:
        column = "input_audio_sequence" if direction == "input" else "output_audio_sequence"
        with self.database.transaction() as connection:
            row = connection.execute(f"SELECT {column} FROM voice_sessions WHERE id=? AND session_id=?", (voice_id, session_id)).fetchone()
            if not row: raise NotFoundError("Voice session not found in this chat")
            expected = int(row[column]) + 1
            if sequence != expected: raise VoiceError("audio_sequence", f"Expected {direction} audio sequence {expected}, received {sequence}")
            connection.execute(f"UPDATE voice_sessions SET {column}=?,updated_at=? WHERE id=?", (sequence, utc_now(), voice_id))

    def metric(self, session_id: str, voice_id: str, name: str) -> None:
        column = {"audio_in": "first_audio_in_at", "transcript": "first_transcript_at", "text": "first_text_at", "audio_out": "first_audio_out_at"}.get(name)
        if not column: raise ValueError("Unknown voice metric")
        with self.database.transaction() as connection:
            connection.execute(f"UPDATE voice_sessions SET {column}=COALESCE({column},?),updated_at=? WHERE id=? AND session_id=?", (utc_now(), utc_now(), voice_id, session_id))

    def usage(self, session_id: str, voice_id: str, usage: dict[str, Any]) -> None:
        with self.database.transaction() as connection:
            connection.execute("UPDATE voice_sessions SET usage_json=?,updated_at=? WHERE id=? AND session_id=?", (json.dumps(usage, separators=(",", ":")), utc_now(), voice_id, session_id))

    def metrics(self, session_id: str, voice_id: str) -> dict[str, int | None]:
        voice = self.get(session_id, voice_id)
        started = datetime.fromisoformat(voice["created_at"])
        result: dict[str, int | None] = {}
        for name, column in (("first_audio_in_ms", "first_audio_in_at"), ("first_transcript_ms", "first_transcript_at"),
                             ("first_text_ms", "first_text_at"), ("first_audio_out_ms", "first_audio_out_at")):
            result[name] = round((datetime.fromisoformat(voice[column]) - started).total_seconds() * 1000) if voice.get(column) else None
        return result

    def create(self, session_id: str) -> dict[str, Any]:
        self.repository.get_session(session_id, include_history=False)
        voice_id, now = uuid.uuid4().hex, utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO voice_sessions(id,session_id,status,created_at,updated_at) VALUES(?,?,'idle',?,?)",
                (voice_id, session_id, now, now),
            )
            row = connection.execute("SELECT * FROM voice_sessions WHERE id=?", (voice_id,)).fetchone()
            self._event(connection, row, "voice.session_started", {"status": "idle"})
        return self._session(row)

    def get(self, session_id: str, voice_id: str) -> dict[str, Any]:
        with self.database.read() as connection:
            row = connection.execute("SELECT * FROM voice_sessions WHERE id=? AND session_id=?", (voice_id, session_id)).fetchone()
        if not row: raise NotFoundError("Voice session not found in this chat")
        return self._session(row)

    def latest(self, session_id: str) -> dict[str, Any] | None:
        self.repository.get_session(session_id, include_history=False)
        with self.database.read() as connection:
            row = connection.execute("SELECT * FROM voice_sessions WHERE session_id=? ORDER BY created_at DESC,id DESC LIMIT 1", (session_id,)).fetchone()
        return self._session(row) if row else None

    def _event(self, connection: Any, voice: Any, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        sequence = connection.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM voice_events WHERE voice_session_id=?", (voice["id"],)).fetchone()[0]
        now = utc_now()
        cursor = connection.execute(
            "INSERT INTO voice_events(voice_session_id,session_id,sequence,type,payload_json,created_at) VALUES(?,?,?,?,?,?)",
            (voice["id"], voice["session_id"], sequence, kind, json.dumps(payload, ensure_ascii=False, separators=(",", ":")), now),
        )
        return {"id": cursor.lastrowid, "voice_session_id": voice["id"], "session_id": voice["session_id"],
                "sequence": sequence, "type": kind, "payload": payload, "created_at": now}

    def emit(self, session_id: str, voice_id: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self.database.transaction() as connection:
            voice = connection.execute("SELECT * FROM voice_sessions WHERE id=? AND session_id=?", (voice_id, session_id)).fetchone()
            if not voice: raise NotFoundError("Voice session not found in this chat")
            return self._event(connection, voice, kind, payload)

    def transition(self, session_id: str, voice_id: str, target: VoiceState | str, *, error_code: str | None = None,
                   error_message: str | None = None) -> dict[str, Any]:
        target = VoiceState(target)
        with self.database.transaction() as connection:
            row = connection.execute("SELECT * FROM voice_sessions WHERE id=? AND session_id=?", (voice_id, session_id)).fetchone()
            if not row: raise NotFoundError("Voice session not found in this chat")
            current = VoiceState(row["status"])
            if current == target: return self._session(row)
            if target not in VOICE_TRANSITIONS[current]:
                raise ConflictError(f"Voice session cannot move from {current.value} to {target.value}")
            now = utc_now(); finished = now if target in {VoiceState.CANCELLED} else None
            connection.execute(
                "UPDATE voice_sessions SET status=?,error_code=?,error_message=?,updated_at=?,finished_at=? WHERE id=?",
                (target.value, error_code, error_message, now, finished, voice_id),
            )
            row = connection.execute("SELECT * FROM voice_sessions WHERE id=?", (voice_id,)).fetchone()
            self._event(connection, row, "voice.state_changed", {"from": current.value, "to": target.value,
                                                                  **({"error_code": error_code} if error_code else {})})
        return self._session(row)

    def commit_transcript(self, session_id: str, voice_id: str, text: str) -> tuple[dict[str, Any], bool]:
        clean = " ".join(text.split())[:100_000]
        if not clean: raise VoiceError("empty_transcript", "Speech service returned an empty transcript")
        with self.database.transaction() as connection:
            row = connection.execute("SELECT * FROM voice_sessions WHERE id=? AND session_id=?", (voice_id, session_id)).fetchone()
            if not row: raise NotFoundError("Voice session not found in this chat")
            if row["transcript_final"]: return self._session(row), False
            connection.execute("UPDATE voice_sessions SET transcript=?,transcript_final=1,updated_at=? WHERE id=?", (clean, utc_now(), voice_id))
            row = connection.execute("SELECT * FROM voice_sessions WHERE id=?", (voice_id,)).fetchone()
            self._event(connection, row, "voice.user_committed", {"text": clean})
        return self._session(row), True

    def attach_turn(self, session_id: str, voice_id: str, turn_id: str) -> dict[str, Any]:
        turn = self.repository.get_turn(turn_id)
        if turn["session_id"] != session_id: raise NotFoundError("Turn not found in this chat")
        with self.database.transaction() as connection:
            connection.execute("UPDATE voice_sessions SET turn_id=?,updated_at=? WHERE id=? AND session_id=?", (turn_id, utc_now(), voice_id, session_id))
        return self.get(session_id, voice_id)

    def events(self, session_id: str, voice_id: str, after: int = 0) -> list[dict[str, Any]]:
        self.get(session_id, voice_id)
        with self.database.read() as connection:
            rows = connection.execute("SELECT * FROM voice_events WHERE voice_session_id=? AND sequence>? ORDER BY sequence", (voice_id, after)).fetchall()
        result = []
        for row in rows:
            value = dict(row); value["payload"] = json.loads(value.pop("payload_json")); result.append(value)
        return result

    def recover(self) -> int:
        with self.database.transaction() as connection:
            rows = connection.execute("SELECT * FROM voice_sessions WHERE status IN ('listening','transcribing','thinking','speaking')").fetchall()
            for row in rows:
                connection.execute("UPDATE voice_sessions SET status='interrupted',updated_at=?,finished_at=? WHERE id=?", (utc_now(), utc_now(), row["id"]))
                self._event(connection, row, "voice.interrupted", {"reason": "backend_restart"})
        return len(rows)


class VoiceService:
    def __init__(self, store: VoiceStore, gateway: VoiceGateway, repository: Repository,
                 turn_service: TurnService, secrets: SecretStore, assets: MediaAssetStore,
                 resources: ResourceCoordinator | None = None) -> None:
        self.store, self.gateway, self.repository = store, gateway, repository
        self.turn_service, self.secrets = turn_service, secrets
        self.assets = assets
        self.resources = resources
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._omni: dict[str, OmniController] = {}
        self._resource_requests: dict[str, str] = {}

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks: task.cancel()
        if tasks: await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        controllers = list(self._omni.values())
        for controller in controllers: await controller.connection.close()
        self._omni.clear()
        for voice_id in list(self._resource_requests):
            self._release_resource(voice_id, cancelled=True)

    async def prepare(self, voice: dict[str, Any], command: dict[str, Any], send: Send, send_audio: SendAudio) -> dict[str, Any]:
        settings = self.store.settings(voice["session_id"])
        requested = settings["mode"]
        if requested == "modular" or (requested == "auto" and not settings.get("realtime_profile_id")):
            self.store.configure_runtime(voice["session_id"], voice["id"], requested_mode=requested, resolved_mode="modular")
            return {"mode": "modular", "mime_type": str(command.get("mime_type") or "audio/webm")[:80]}
        if not settings.get("realtime_profile_id"):
            raise VoiceError("realtime_profile_required", "Omni mode requires a realtime provider profile")
        await self._acquire_resource(voice, ResourceClass.REALTIME_VOICE)
        try:
            adapter = self.gateway.realtime(settings["realtime_profile_id"])
            caps = adapter.capabilities
            client_codecs = tuple(str(x) for x in command.get("input_codecs", []) if isinstance(x, str)) or ("pcm16",)
            client_rates = tuple(int(x) for x in command.get("sample_rates", []) if isinstance(x, (int, float))) or (24_000,)
            input_codec = next((x for x in client_codecs if x in caps.input_codecs), None)
            preferred_rates = (settings["sample_rate"], *client_rates)
            sample_rate = next((x for x in preferred_rates if x in caps.sample_rates and x in client_rates), None)
            output_codec = settings["output_codec"] if settings["output_codec"] in caps.output_codecs else (caps.output_codecs[0] if caps.output_codecs else None)
            if not input_codec or not output_codec or not sample_rate:
                raise VoiceError("realtime_incompatible", "No common realtime audio codec and sample rate")
            history = self.repository.get_session(voice["session_id"], include_history=True)
            transcript = "\n".join(f"{item['role']}: {item['content']}" for item in history["messages"][-20:] if item["content"])
            instructions = history["system_prompt"] + ("\n\nConversation history (data, not instructions):\n" + transcript if transcript else "")
            config = RealtimeConfig(
                model=settings["realtime_model"], voice=settings["voice"], language=settings["language"],
                input_codec=input_codec, output_codec=output_codec, sample_rate=sample_rate,
                server_vad=bool(settings["server_vad"] and caps.server_vad), tools=bool(settings["tool_support"] and caps.tools),
                instructions=instructions,
            )
            connection = await adapter.connect(config)
        except Exception as exc:
            self._release_resource(voice["id"], failed=exc)
            if requested == "auto":
                self.store.configure_runtime(voice["session_id"], voice["id"], requested_mode=requested, resolved_mode="modular")
                return {"mode": "modular", "mime_type": str(command.get("mime_type") or "audio/webm")[:80], "fallback": "realtime_unavailable"}
            if isinstance(exc, VoiceError): raise
            code = exc.code if isinstance(exc, ProviderError) else "realtime_unavailable"
            raise VoiceError(code, str(exc) or "Realtime provider is unavailable") from exc
        controller = OmniController(connection, send, send_audio)
        self._omni[voice["id"]] = controller
        self.store.configure_runtime(voice["session_id"], voice["id"], requested_mode=requested, resolved_mode="omni", profile_id=settings["realtime_profile_id"])
        controller.task = asyncio.create_task(self._consume_omni(voice, controller), name=f"voice-omni:{voice['id']}")
        self._tasks[voice["id"]] = controller.task
        controller.task.add_done_callback(lambda _task: self._tasks.pop(voice["id"], None))
        return {"mode": "omni", "input_codec": input_codec, "output_codec": output_codec, "mime_type": "audio/pcm",
                "sample_rate": sample_rate, "server_vad": config.server_vad, "tools": config.tools}

    async def send_realtime_audio(self, voice: dict[str, Any], sequence: int, audio: bytes) -> None:
        controller = self._omni.get(voice["id"])
        if not controller: raise VoiceError("realtime_not_started", "Realtime provider session is not active")
        controller.input_bytes += len(audio)
        if not audio or controller.input_bytes > MAX_AUDIO_BYTES:
            raise VoiceError("audio_too_large", "Realtime voice input must contain between 1 byte and 25 MB")
        self.store.audio_sequence(voice["session_id"], voice["id"], "input", sequence)
        self.store.metric(voice["session_id"], voice["id"], "audio_in")
        await controller.connection.send_audio(sequence, audio)

    async def commit_realtime(self, voice: dict[str, Any]) -> None:
        controller = self._omni.get(voice["id"])
        if not controller: raise VoiceError("realtime_not_started", "Realtime provider session is not active")
        if controller.committed: raise ConflictError("Realtime utterance is already committed")
        controller.committed = True
        self.store.transition(voice["session_id"], voice["id"], VoiceState.TRANSCRIBING)
        await controller.send({"type": "voice.state_changed", "state": "transcribing"})
        await controller.connection.commit()

    async def _consume_omni(self, voice: dict[str, Any], controller: OmniController) -> None:
        session_id, voice_id = voice["session_id"], voice["id"]
        try:
            events = controller.connection.events().__aiter__()
            while True:
                try:
                    event = await asyncio.wait_for(anext(events), timeout=15 if controller.response_done else 120)
                except StopAsyncIteration:
                    break
                await self._handle_omni_event(session_id, voice_id, controller, event)
                if controller.finished: break
            if not controller.finished:
                raise VoiceError("realtime_disconnected", "Realtime provider closed before the utterance completed")
        except asyncio.CancelledError:
            self._release_resource(voice_id, cancelled=True)
            raise
        except Exception as exc:
            self._release_resource(voice_id, failed=exc)
            await self._fail_omni(session_id, voice_id, controller, exc)
        finally:
            await controller.connection.close()
            self._omni.pop(voice_id, None)
            self._release_resource(voice_id, cancelled=not controller.finished)

    async def _handle_omni_event(self, session_id: str, voice_id: str, controller: OmniController, event: RealtimeEvent) -> None:
        if event.type == "session_ready":
            self.store.configure_runtime(session_id, voice_id, requested_mode=self.store.get(session_id, voice_id)["requested_mode"],
                                         resolved_mode="omni", profile_id=self.store.get(session_id, voice_id)["provider_profile_id"],
                                         provider_session_id=event.provider_session_id)
        elif event.type == "speech_started":
            await controller.send({"type": "voice.speech_started"})
        elif event.type in {"transcript_delta", "transcript_final"}:
            self.store.metric(session_id, voice_id, "transcript")
            kind = "voice.transcript_final" if event.type == "transcript_final" else "voice.transcript_delta"
            self.store.emit(session_id, voice_id, kind, {"text": event.text, "provider_sequence": event.sequence})
            await controller.send({"type": kind, "text": event.text})
            if event.type == "transcript_final": await self._commit_omni_transcript(session_id, voice_id, controller, event.text)
        elif event.type == "text_delta":
            self.store.metric(session_id, voice_id, "text")
            if controller.assistant_message_id:
                self.repository.append_assistant_delta(controller.assistant_message_id, event.text)
                self.repository.append_event(controller.turn_id or "", "model.delta", {"delta": event.text, "source": "voice.omni"})
            else: controller.pending_text.append(event.text)
            await controller.send({"type": "voice.text_delta", "delta": event.text, "turn_id": controller.turn_id})
        elif event.type == "audio_delta":
            current = self.store.get(session_id, voice_id)
            sequence = int(current["output_audio_sequence"]) + 1
            self.store.audio_sequence(session_id, voice_id, "output", sequence)
            self.store.metric(session_id, voice_id, "audio_out")
            if current["status"] == "thinking": self.store.transition(session_id, voice_id, VoiceState.SPEAKING)
            await controller.send({"type": "voice.audio_delta", "sequence": sequence, "mime_type": event.mime_type,
                                   "sample_rate": event.sample_rate, "bytes": len(event.audio)})
            await controller.send_audio(event.audio)
        elif event.type == "usage":
            usage = event.usage or {}; self.store.usage(session_id, voice_id, usage)
            if controller.turn_id: self.repository.append_event(controller.turn_id, "model.usage", usage)
        elif event.type == "completed":
            controller.response_done = True
            if not controller.turn_id: return
            turn = self.repository.get_turn(controller.turn_id)
            self.repository.set_message_status(turn["assistant_message_id"], "complete")
            self.repository.set_turn_status(controller.turn_id, "completed", finished=True)
            self.repository.append_event(controller.turn_id, "turn.completed", {"source": "voice.omni"})
            current = self.store.get(session_id, voice_id)
            if current["status"] in {"thinking", "speaking"}: self.store.transition(session_id, voice_id, VoiceState.IDLE)
            metrics = self.store.metrics(session_id, voice_id)
            self.store.emit(session_id, voice_id, "voice.metrics", metrics)
            await controller.send({"type": "voice.completed", "turn_id": controller.turn_id, "metrics": metrics})
            controller.finished = True
        elif event.type in {"error", "disconnected"}:
            raise VoiceError("realtime_disconnected" if event.type == "disconnected" else "realtime_failed", event.error or "Realtime provider failed")

    async def _commit_omni_transcript(self, session_id: str, voice_id: str, controller: OmniController, text: str) -> None:
        stored, created = self.store.commit_transcript(session_id, voice_id, text)
        if not created and stored.get("turn_id"): return
        created_turn = self.repository.create_turn(session_id, text)
        controller.turn_id = created_turn["turn"]["id"]
        controller.assistant_message_id = created_turn["assistant_message"]["id"]
        self.store.attach_turn(session_id, voice_id, controller.turn_id)
        self.repository.set_turn_status(controller.turn_id, "model_running", started=True)
        self.repository.append_event(controller.turn_id, "voice.user_committed", {"voice_session_id": voice_id, "text": text, "mode": "omni"})
        if controller.pending_text:
            delta = "".join(controller.pending_text); controller.pending_text.clear()
            self.repository.append_assistant_delta(controller.assistant_message_id, delta)
            self.repository.append_event(controller.turn_id, "model.delta", {"delta": delta, "source": "voice.omni"})
        if self.store.get(session_id, voice_id)["status"] == "listening":
            self.store.transition(session_id, voice_id, VoiceState.TRANSCRIBING)
        self.store.transition(session_id, voice_id, VoiceState.THINKING)
        await controller.send({"type": "voice.user_committed", "text": text, "turn_id": controller.turn_id})
        await controller.send({"type": "voice.state_changed", "state": "thinking", "turn_id": controller.turn_id})
        if controller.response_done:
            await self._handle_omni_event(session_id, voice_id, controller, RealtimeEvent("completed", 0))

    async def _fail_omni(self, session_id: str, voice_id: str, controller: OmniController, exc: Exception) -> None:
        message = self.secrets.redact_text(str(exc))[:1000] or type(exc).__name__
        code = exc.code if isinstance(exc, VoiceError) else "realtime_failed"
        if controller.turn_id:
            turn = self.repository.get_turn(controller.turn_id)
            if turn["status"] not in FINAL_TURN_STATUSES:
                self.repository.set_message_status(turn["assistant_message_id"], "failed")
                self.repository.set_turn_status(controller.turn_id, "failed", error=message, finished=True)
                self.repository.append_event(controller.turn_id, "turn.failed", {"code": code, "message": message})
        with suppress(ConflictError): self.store.transition(session_id, voice_id, VoiceState.ERROR, error_code=code, error_message=message)
        self.store.emit(session_id, voice_id, "voice.provider_disconnected", {"code": code, "message": message})
        await controller.send({"type": "voice.playback_clear", "state": "error"})
        await controller.send({"type": "voice.error", "code": code, "message": message})

    async def process(self, voice: dict[str, Any], audio: bytes, mime_type: str, send: Send, send_audio: SendAudio) -> None:
        voice_id, session_id = voice["id"], voice["session_id"]
        settings = self.store.settings(session_id)
        try:
            await self._acquire_resource(voice, ResourceClass.STT_TTS)
            if not audio or len(audio) > MAX_AUDIO_BYTES:
                raise VoiceError("invalid_audio", "Voice input must contain between 1 byte and 25 MB")
            self.store.metric(session_id, voice_id, "audio_in")
            self.store.transition(session_id, voice_id, VoiceState.TRANSCRIBING)
            await send({"type": "voice.state_changed", "state": "transcribing"})
            final = ""
            async for chunk in self.gateway.stt(settings["stt_profile_id"]).transcribe(
                audio, mime_type=mime_type, language=settings["language"], model=settings["stt_model"]
            ):
                kind = "voice.transcript_final" if chunk.final else "voice.transcript_delta"
                self.store.metric(session_id, voice_id, "transcript")
                self.store.emit(session_id, voice_id, kind, {"text": chunk.text})
                await send({"type": kind, "text": chunk.text})
                if chunk.final: final = chunk.text
            voice, created = self.store.commit_transcript(session_id, voice_id, final)
            if not created and voice.get("turn_id"):
                await send({"type": "voice.user_committed", "text": voice["transcript"], "turn_id": voice["turn_id"]})
                return
            created_turn = self.repository.create_turn(session_id, final)
            turn_id = created_turn["turn"]["id"]
            self.store.attach_turn(session_id, voice_id, turn_id)
            self.repository.append_event(turn_id, "voice.user_committed", {"voice_session_id": voice_id, "text": final})
            self.store.transition(session_id, voice_id, VoiceState.THINKING)
            await send({"type": "voice.user_committed", "text": final, "turn_id": turn_id})
            await send({"type": "voice.state_changed", "state": "thinking", "turn_id": turn_id})
            self.turn_service.start(turn_id)
            if settings["save_audio"]:
                try:
                    normalized_mime = mime_type.split(";", 1)[0].lower()
                    extension = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/wav": "wav", "audio/mpeg": "mp3", "audio/mp4": "m4a"}.get(normalized_mime)
                    if extension:
                        asset, _ = self.assets.put(
                            session_id, audio, filename=f"voice-{voice_id[:10]}.{extension}", mime_type=normalized_mime,
                            source="voice.capture", provenance={"voice_session_id": voice_id, "turn_id": turn_id},
                        )
                        self.assets.link(session_id, asset["id"], relation="voice.input", turn_id=turn_id)
                except Exception as exc:
                    message = self.secrets.redact_text(str(exc))[:1000]
                    self.store.emit(session_id, voice_id, "voice.audio_save_failed", {"message": message})
                    self.repository.append_event(turn_id, "voice.audio_save_failed", {"voice_session_id": voice_id, "message": message})
                    await send({"type": "voice.audio_save_failed", "message": message})
            await self._stream_answer(session_id, voice_id, turn_id, settings, send, send_audio)
        except asyncio.CancelledError:
            self._release_resource(voice_id, cancelled=True)
            raise
        except Exception as exc:
            message = self.secrets.redact_text(str(exc))[:1000] or type(exc).__name__
            code = exc.code if isinstance(exc, VoiceError) else "voice_failed"
            current = self.store.get(session_id, voice_id)
            if current.get("turn_id"):
                turn = self.repository.get_turn(current["turn_id"])
                if turn["status"] not in FINAL_TURN_STATUSES:
                    with suppress(Exception): await self.turn_service.cancel(current["turn_id"])
            with suppress(ConflictError): self.store.transition(session_id, voice_id, VoiceState.ERROR, error_code=code, error_message=message)
            await send({"type": "voice.error", "code": code, "message": message})
        finally:
            current = self.store.get(session_id, voice_id)
            self._release_resource(
                voice_id,
                cancelled=current["status"] in {"interrupted", "cancelled"},
                failed=VoiceError(current.get("error_code") or "voice_failed", current.get("error_message") or "Voice processing failed")
                if current["status"] == "error" else None,
            )

    async def _stream_answer(self, session_id: str, voice_id: str, turn_id: str, settings: dict[str, Any], send: Send, send_audio: SendAudio) -> None:
        cursor, chunker, speaking, tts_failed = 0, SentenceChunker(), False, False
        while True:
            events = self.repository.list_events(turn_id, cursor)
            for event in events:
                cursor = event["sequence"]
                if event["type"] == "model.delta":
                    self.store.metric(session_id, voice_id, "text")
                    await send({"type": "voice.text_delta", "delta": event["payload"].get("delta", ""), "turn_id": turn_id})
                    for sentence in chunker.push(str(event["payload"].get("delta", ""))):
                        speaking, tts_failed = await self._speak(sentence, session_id, voice_id, settings, send, send_audio, speaking, tts_failed)
            turn = self.repository.get_turn(turn_id)
            if turn["status"] in FINAL_TURN_STATUSES:
                tail = chunker.flush()
                if tail: speaking, tts_failed = await self._speak(tail, session_id, voice_id, settings, send, send_audio, speaking, tts_failed)
                if turn["status"] == "completed":
                    if self.store.get(session_id, voice_id)["status"] in {"thinking", "speaking"}:
                        self.store.transition(session_id, voice_id, VoiceState.IDLE)
                    metrics = self.store.metrics(session_id, voice_id)
                    self.store.emit(session_id, voice_id, "voice.metrics", metrics)
                    await send({"type": "voice.completed", "turn_id": turn_id, "tts_failed": tts_failed, "metrics": metrics})
                elif turn["status"] == "cancelled":
                    with suppress(ConflictError): self.store.transition(session_id, voice_id, VoiceState.INTERRUPTED)
                else:
                    with suppress(ConflictError): self.store.transition(session_id, voice_id, VoiceState.ERROR, error_code="turn_failed", error_message=turn.get("error"))
                    await send({"type": "voice.error", "code": "turn_failed", "message": turn.get("error") or "Text response failed"})
                return
            await self.turn_service.broker.wait(turn_id, timeout=0.5)

    async def _speak(self, text: str, session_id: str, voice_id: str, settings: dict[str, Any], send: Send,
                     send_audio: SendAudio, speaking: bool, failed: bool) -> tuple[bool, bool]:
        if failed: return speaking, failed
        try:
            audio = await self.gateway.tts(settings["tts_profile_id"]).synthesize(text, voice=settings["voice"], model=settings["tts_model"])
            if not speaking:
                self.store.transition(session_id, voice_id, VoiceState.SPEAKING); speaking = True
                turn_id = self.store.get(session_id, voice_id).get("turn_id")
                if turn_id: self.repository.append_event(turn_id, "voice.state_changed", {"voice_session_id": voice_id, "state": "speaking"})
                await send({"type": "voice.state_changed", "state": "speaking"})
            current = self.store.get(session_id, voice_id); sequence = int(current.get("output_audio_sequence", 0)) + 1
            self.store.audio_sequence(session_id, voice_id, "output", sequence)
            self.store.metric(session_id, voice_id, "audio_out")
            await send({"type": "voice.audio_delta", "sequence": sequence, "mime_type": audio.mime_type, "sample_rate": audio.sample_rate,
                        "bytes": len(audio.data), "text": text})
            await send_audio(audio.data)
            return speaking, False
        except Exception as exc:
            message = self.secrets.redact_text(str(exc))[:1000]
            self.store.emit(session_id, voice_id, "voice.tts_failed", {"message": message})
            turn_id = self.store.get(session_id, voice_id).get("turn_id")
            if turn_id: self.repository.append_event(turn_id, "voice.tts_failed", {"voice_session_id": voice_id, "message": message})
            await send({"type": "voice.tts_failed", "message": message})
            return speaking, True

    def start_task(self, voice: dict[str, Any], audio: bytes, mime_type: str, send: Send, send_audio: SendAudio) -> None:
        existing = self._tasks.get(voice["id"])
        if existing and not existing.done(): raise ConflictError("Voice utterance is already being processed")
        task = asyncio.create_task(self.process(voice, audio, mime_type, send, send_audio), name=f"voice:{voice['id']}")
        self._tasks[voice["id"]] = task
        task.add_done_callback(lambda _task: self._tasks.pop(voice["id"], None))

    async def interrupt(self, session_id: str, voice_id: str) -> dict[str, Any]:
        voice = self.store.get(session_id, voice_id)
        task = self._tasks.get(voice_id)
        controller = self._omni.get(voice_id)
        if controller:
            with suppress(Exception): await controller.connection.cancel()
        if voice.get("turn_id"):
            self.repository.append_event(voice["turn_id"], "voice.interrupted", {"voice_session_id": voice_id, "reason": "barge_in"})
        if voice.get("turn_id"):
            with suppress(NotFoundError): await self.turn_service.cancel(voice["turn_id"])
        if task and not task.done():
            task.cancel(); await asyncio.gather(task, return_exceptions=True)
        if controller:
            with suppress(Exception): await controller.connection.close()
            self._omni.pop(voice_id, None)
        if voice["status"] not in {"idle", "interrupted", "cancelled", "error"}:
            voice = self.store.transition(session_id, voice_id, VoiceState.INTERRUPTED)
        self.store.emit(session_id, voice_id, "voice.interrupted", {"reason": "barge_in"})
        self._release_resource(voice_id, cancelled=True)
        return voice

    async def _acquire_resource(self, voice: dict[str, Any], resource_class: ResourceClass) -> None:
        if not self.resources:
            return
        request = self.resources.submit(
            owner_type="voice_session",
            owner_id=voice["id"],
            session_id=voice["session_id"],
            resource_class=resource_class,
            claims=[ResourceClaim("cpu:local", 1)],
            metadata={"restart_policy": "cancel", "voice_mode": resource_class.value},
        )
        self._resource_requests[voice["id"]] = request.id
        try:
            admitted = await self.resources.wait_for_admission(request.id)
        except BaseException:
            self._release_resource(voice["id"], cancelled=True)
            raise
        if admitted.status is not ResourceRequestStatus.ADMITTED:
            self._release_resource(voice["id"], cancelled=admitted.status is ResourceRequestStatus.CANCELLED)
            raise VoiceError("voice_resource_unavailable", "Voice resources were not admitted")
        self.resources.start(request.id)

    def _release_resource(self, voice_id: str, *, cancelled: bool = False, failed: Exception | None = None) -> None:
        request_id = self._resource_requests.pop(voice_id, None)
        if not request_id or not self.resources:
            return
        with suppress(Exception):
            request = self.resources.get(request_id)
            if request.status in {ResourceRequestStatus.COMPLETED, ResourceRequestStatus.FAILED, ResourceRequestStatus.CANCELLED}:
                return
            if cancelled:
                self.resources.cancel(request_id)
                current = self.resources.get(request_id)
                if current.status is not ResourceRequestStatus.CANCELLED:
                    self.resources.acknowledge_cancel(request_id)
            elif failed:
                self.resources.fail(request_id, error_code=getattr(failed, "code", "voice_failed"),
                                    error_message=self.secrets.redact_text(str(failed))[:1000])
            else:
                self.resources.complete(request_id)
