import { Microphone, Stop, Waveform, X } from "@phosphor-icons/react";
import { useEffect, useReducer, useRef } from "react";
import { api } from "../api";
import type { VoiceSettings } from "../types";
import { VoiceCapture } from "./capture";
import { PlaybackQueue } from "./playback";
import { initialVoiceState, voiceReducer } from "./state";
import "./voice.css";

const labels = { idle: "Голос", listening: "Слушаю…", transcribing: "Распознаю…", thinking: "Модель отвечает…", speaking: "Воспроизвожу…", interrupted: "Прервано", cancelled: "Остановлено", error: "Ошибка голоса" } as const;

export function VoiceBar({ sessionId, disabled, onTurnStarted, onError }: {
  sessionId: string; disabled: boolean; onTurnStarted: (turnId: string) => void; onError: (message: string) => void;
}) {
  const [view, dispatch] = useReducer(voiceReducer, initialVoiceState);
  const socket = useRef<WebSocket | null>(null);
  const capture = useRef(new VoiceCapture());
  const playback = useRef(new PlaybackQueue());
  const settings = useRef<VoiceSettings | null>(null);
  const nextAudio = useRef({ mime: "audio/mpeg", sequence: 1, sampleRate: undefined as number | undefined });
  const modeWaiter = useRef<{ resolve: (value: Record<string, unknown>) => void; reject: (error: Error) => void } | null>(null);

  useEffect(() => () => { capture.current.release(); playback.current.clear(); socket.current?.close(); }, []);
  useEffect(() => {
    dispatch({ type: "reset" }); settings.current = null;
    return () => {
      const previous = socket.current; socket.current = null;
      if (previous) { previous.onmessage = null; previous.onclose = null; previous.close(); }
      modeWaiter.current?.reject(new Error("Чат изменён")); modeWaiter.current = null;
      capture.current.release(); playback.current.clear();
    };
  }, [sessionId]);

  async function connect(): Promise<WebSocket> {
    if (socket.current?.readyState === WebSocket.OPEN) return socket.current;
    settings.current = await api.voiceSettings(sessionId);
    playback.current.setOutputDevice(settings.current.output_device_id);
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const value = new WebSocket(`${protocol}//${location.host}/api/voice/sessions/${sessionId}/stream`);
    value.binaryType = "arraybuffer";
    socket.current = value;
    value.onmessage = event => {
      if (event.data instanceof ArrayBuffer) { playback.current.enqueue(event.data, nextAudio.current.mime, nextAudio.current.sequence, nextAudio.current.sampleRate); return; }
      const message = JSON.parse(String(event.data)) as Record<string, unknown>;
      if (message.type === "voice.session_started") { playback.current.clear(); nextAudio.current = { mime: "audio/mpeg", sequence: 1, sampleRate: undefined }; }
      else if (message.type === "voice.state_changed") dispatch({ type: "state", state: message.state as typeof view.state });
      else if (message.type === "voice.transcript_delta" || message.type === "voice.transcript_final") dispatch({ type: "transcript", text: String(message.text ?? "") });
      else if (message.type === "voice.user_committed" && typeof message.turn_id === "string") onTurnStarted(message.turn_id);
      else if (message.type === "voice.mode_resolved") { modeWaiter.current?.resolve(message); modeWaiter.current = null; }
      else if (message.type === "voice.audio_delta") nextAudio.current = { mime: String(message.mime_type ?? "audio/mpeg"), sequence: Number(message.sequence ?? 1), sampleRate: typeof message.sample_rate === "number" ? message.sample_rate : undefined };
      else if (message.type === "voice.playback_clear") { playback.current.clear(); dispatch({ type: "state", state: message.state as typeof view.state }); }
      else if (message.type === "voice.completed") dispatch({ type: "state", state: "idle" });
      else if (message.type === "voice.tts_failed") onError(`Озвучивание недоступно: ${String(message.message ?? "неизвестная ошибка")}. Текст ответа сохранён.`);
      else if (message.type === "voice.error") { const text = String(message.message ?? "Ошибка голоса"); modeWaiter.current?.reject(new Error(text)); modeWaiter.current = null; capture.current.release(); playback.current.clear(); dispatch({ type: "error", message: text }); onError(text); }
    };
    value.onclose = () => { modeWaiter.current?.reject(new Error("Голосовое соединение закрыто")); modeWaiter.current = null; if (socket.current === value) socket.current = null; capture.current.release(); playback.current.clear(); dispatch({ type: "reset" }); };
    return new Promise((resolve, reject) => { value.addEventListener("open", () => resolve(value), { once: true }); value.addEventListener("error", () => reject(new Error("Голосовой WebSocket недоступен")), { once: true }); });
  }

  async function start() {
    if (disabled && !["thinking", "speaking", "transcribing"].includes(view.state)) return;
    try {
      if (["thinking", "speaking", "transcribing"].includes(view.state)) {
        socket.current?.send(JSON.stringify({ type: "voice.interrupt" })); playback.current.clear();
      }
      const ws = await connect();
      playback.current.clear(); nextAudio.current = { mime: "audio/mpeg", sequence: 1, sampleRate: undefined };
      const negotiation = new Promise<Record<string, unknown>>((resolve, reject) => { const waiter = { resolve, reject }; modeWaiter.current = waiter; setTimeout(() => { if (modeWaiter.current === waiter) { modeWaiter.current = null; reject(new Error("Провайдер не подтвердил голосовой режим")); } }, 25_000); });
      ws.send(JSON.stringify({ type: "voice.start", mime_type: "audio/webm", ...VoiceCapture.capabilities() }));
      const mode = await negotiation;
      await capture.current.start(settings.current?.input_device_id ?? null,
        chunk => { if (ws.readyState === WebSocket.OPEN) ws.send(chunk); },
        () => void commit(), { mode: mode.mode === "omni" ? "pcm16" : "compressed", sampleRate: Number(mode.sample_rate ?? 24000), threshold: settings.current?.vad_threshold, silenceMs: settings.current?.vad_silence_ms });
      dispatch({ type: "state", state: "listening" });
    } catch (cause) { capture.current.release(); const text = cause instanceof Error ? cause.message : "Микрофон недоступен"; dispatch({ type: "error", message: text }); onError(text); }
  }

  async function commit() {
    const ws = socket.current; if (!ws) return;
    await capture.current.stop();
    if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "voice.commit" }));
  }

  function stopAll() { capture.current.release(); playback.current.clear(); socket.current?.send(JSON.stringify({ type: "voice.cancel" })); socket.current?.close(); dispatch({ type: "reset" }); }

  const active = view.state !== "idle" && view.state !== "interrupted" && view.state !== "cancelled" && view.state !== "error";
  return <div className="voice-bar" data-state={view.state} role="group" aria-label="Голосовой режим">
    <button className="voice-main" type="button" disabled={disabled && !active} onClick={() => void (view.state === "listening" ? commit() : start())} aria-label={view.state === "listening" ? "Закончить запись" : active ? "Перебить модель" : "Начать голосовой ввод"}>
      {view.state === "listening" ? <Stop size={16} weight="fill" /> : active ? <Waveform size={18} /> : <Microphone size={18} />}
      <span aria-live="polite">{labels[view.state]}</span>
    </button>
    {view.transcript && active ? <span className="voice-transcript" title={view.transcript}>{view.transcript}</span> : null}
    {active ? <button className="voice-close" type="button" onClick={stopAll} aria-label="Закрыть голосовой режим"><X size={16} /></button> : null}
  </div>;
}
