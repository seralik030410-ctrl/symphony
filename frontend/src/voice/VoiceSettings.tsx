import { Microphone, SpeakerHigh, WarningCircle } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { ProviderProfile, Session, VoiceSettings as Settings } from "../types";

export function VoiceSettings({ session }: { session: Session | null }) {
  const [value, setValue] = useState<Settings | null>(null);
  const [profiles, setProfiles] = useState<ProviderProfile[]>([]);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [busy, setBusy] = useState(false); const [message, setMessage] = useState(""); const [error, setError] = useState("");
  useEffect(() => { if (!session) return; Promise.all([api.voiceSettings(session.id), api.listProviderProfiles()]).then(([settings, items]) => { setValue(settings); setProfiles(items.filter(item => item.enabled)); }).catch(cause => setError((cause as Error).message)); navigator.mediaDevices?.enumerateDevices().then(setDevices).catch(() => undefined); }, [session]);
  if (!session) return <section className="voice-settings settings-first-use"><Microphone size={34} /><h2>Сначала создайте чат</h2><p>Голосовые настройки изолированы для каждого чата.</p></section>;
  if (!value) return <section className="voice-settings"><header className="settings-content-header"><div><h1>Голос</h1><p>Загружаем настройки…</p></div></header>{error && <div className="settings-alert"><WarningCircle size={17} />{error}</div>}</section>;
  const set = <K extends keyof Settings>(key: K, next: Settings[K]) => setValue(current => current ? { ...current, [key]: next } : current);
  async function save() { if (!value || !session) return; setBusy(true); setError(""); try { const { session_id: _session, updated_at: _updated, ...changes } = value; setValue(await api.updateVoiceSettings(session.id, changes)); setMessage("Настройки голоса сохранены."); } catch (cause) { setError((cause as Error).message); } finally { setBusy(false); } }
  return <section className="voice-settings"><header className="settings-content-header"><div><h1>Голос</h1><p>Auto выбирает совместимый realtime-контур и безопасно возвращается к STT → модель → TTS.</p></div></header>
    {error && <div className="settings-alert"><WarningCircle size={17} /><span>{error}</span></div>}{message && <div className="settings-alert settings-success" role="status">{message}</div>}
    <h2>Режим разговора</h2><section className="settings-card voice-fields">
      <label><span>Режим</span><select value={value.mode} onChange={e => set("mode", e.target.value as Settings["mode"])}><option value="auto">Auto</option><option value="omni">Omni realtime</option><option value="modular">Modular</option></select></label>
      <label><span>Realtime-провайдер</span><select value={value.realtime_profile_id ?? ""} onChange={e => set("realtime_profile_id", e.target.value || null)}><option value="">Не выбран</option>{profiles.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
      <label><span>Realtime-модель</span><input value={value.realtime_model} onChange={e => set("realtime_model", e.target.value)} /></label>
      <label><span>Частота PCM</span><select value={value.sample_rate} onChange={e => set("sample_rate", Number(e.target.value))}><option value={24000}>24 кГц</option><option value={16000}>16 кГц</option></select></label>
      <label><input type="checkbox" checked={value.server_vad} onChange={e => set("server_vad", e.target.checked)} /> Server VAD</label>
      <label><input type="checkbox" checked={value.tool_support} onChange={e => set("tool_support", e.target.checked)} /> Инструменты провайдера</label>
    </section>
    <h2>Распознавание и озвучивание</h2><section className="settings-card voice-fields">
      <label><span>STT-провайдер</span><select value={value.stt_profile_id ?? ""} onChange={e => set("stt_profile_id", e.target.value || null)}><option value="">Встроенный mock</option>{profiles.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
      <label><span>STT-модель</span><input value={value.stt_model} onChange={e => set("stt_model", e.target.value)} /></label>
      <label><span>TTS-провайдер</span><select value={value.tts_profile_id ?? ""} onChange={e => set("tts_profile_id", e.target.value || null)}><option value="">Встроенный mock</option>{profiles.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
      <label><span>TTS-модель</span><input value={value.tts_model} onChange={e => set("tts_model", e.target.value)} /></label>
      <label><span>Язык</span><input value={value.language} onChange={e => set("language", e.target.value)} /></label><label><span>Голос</span><input value={value.voice} onChange={e => set("voice", e.target.value)} /></label>
    </section>
    <h2>Устройства</h2><section className="settings-card voice-device-list"><label><Microphone size={17} /><span>Микрофон</span><select value={value.input_device_id ?? ""} onChange={e => set("input_device_id", e.target.value || null)}><option value="">Системный</option>{devices.filter(x => x.kind === "audioinput").map((item, i) => <option key={item.deviceId} value={item.deviceId}>{item.label || `Микрофон ${i + 1}`}</option>)}</select></label><label><SpeakerHigh size={17} /><span>Динамик</span><select value={value.output_device_id ?? ""} onChange={e => set("output_device_id", e.target.value || null)}><option value="">Системный</option>{devices.filter(x => x.kind === "audiooutput").map((item, i) => <option key={item.deviceId} value={item.deviceId}>{item.label || `Динамик ${i + 1}`}</option>)}</select></label></section>
    <h2>Определение речи</h2><section className="settings-card voice-fields"><label><span>Порог голоса</span><input type="number" min="0.001" max="1" step="0.005" value={value.vad_threshold} onChange={e => set("vad_threshold", Number(e.target.value))} /></label><label><span>Тишина до отправки, мс</span><input type="number" min="200" max="5000" step="100" value={value.vad_silence_ms} onChange={e => set("vad_silence_ms", Number(e.target.value))} /></label></section>
    <section className="settings-card voice-retention"><div><strong>Хранение аудио</strong><small>Транскрипт сохраняется в чате. Исходная запись микрофона по умолчанию удаляется из памяти сразу после обработки.</small></div><label><input type="checkbox" checked={value.save_audio} onChange={e => set("save_audio", e.target.checked)} /> Сохранять raw audio</label></section>
    <button className="settings-primary" disabled={busy} onClick={() => void save()}>{busy ? "Сохраняем…" : "Сохранить"}</button>
  </section>;
}
