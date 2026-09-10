import { useEffect, useState } from "react";
import { api } from "../api";
import type { Session, VisionMode } from "../types";
import { DEFAULT_VISION_LIMITS } from "./limits";

export function VisionSettings({ session, active }: { session: Session | null; active: boolean }) {
  const [mode, setMode] = useState<VisionMode>("auto");
  const [limits, setLimits] = useState(DEFAULT_VISION_LIMITS);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!session) return;
    setMode((localStorage.getItem(`symphony.visionMode.${session.id}`) as VisionMode | null) ?? "auto");
    void api.modelCapabilities(session.id).then(value => setLimits({
      max_vision_frames: value.max_vision_frames, max_image_bytes: value.max_image_bytes,
      max_image_width: value.max_image_width, max_image_height: value.max_image_height,
      max_image_tokens: value.max_image_tokens, max_vision_tokens: value.max_vision_tokens,
    })).catch(error => setNotice(error instanceof Error ? error.message : "Не удалось прочитать Vision-настройки"));
  }, [session?.id]);
  if (!session) return null;
  const sessionId = session.id;
  async function save() {
    setBusy(true); setNotice("");
    try {
      await api.updateCapabilities(sessionId, limits);
      localStorage.setItem(`symphony.visionMode.${sessionId}`, mode);
      setNotice("Vision-настройки сохранены");
    } catch (error) { setNotice(error instanceof Error ? error.message : "Настройки не сохранены"); }
    finally { setBusy(false); }
  }
  return <section className="general-settings"><header className="settings-content-header"><div><h1>Vision</h1><p>Выбор кадров, локальный OCR и пределы контекста модели.</p></div></header>
    <section className="settings-card"><label className="settings-row"><span>Режим изображений</span><select value={mode} disabled={active || busy} onChange={event => setMode(event.target.value as VisionMode)}><option value="auto">Авто</option><option value="vision">Vision model</option><option value="ocr">Локальный OCR</option></select></label>
      <label className="settings-row"><span>Кадров за turn</span><input type="number" min={1} max={64} value={limits.max_vision_frames} disabled={active || busy} onChange={event => setLimits(current => ({ ...current, max_vision_frames: Number(event.target.value) }))} /></label>
      <label className="settings-row"><span>Максимальная ширина кадра</span><input type="number" min={64} max={32768} value={limits.max_image_width} disabled={active || busy} onChange={event => setLimits(current => ({ ...current, max_image_width: Number(event.target.value) }))} /></label>
      <label className="settings-row"><span>Максимальная высота кадра</span><input type="number" min={64} max={32768} value={limits.max_image_height} disabled={active || busy} onChange={event => setLimits(current => ({ ...current, max_image_height: Number(event.target.value) }))} /></label>
      <label className="settings-row"><span>Лимит размера, МБ</span><input type="number" min={1} max={100} value={Math.round(limits.max_image_bytes / 1_000_000)} disabled={active || busy} onChange={event => setLimits(current => ({ ...current, max_image_bytes: Number(event.target.value) * 1_000_000 }))} /></label>
      <label className="settings-row"><span>Vision-бюджет, токенов</span><input type="number" min={1} max={1000000} value={limits.max_vision_tokens} disabled={active || busy} onChange={event => setLimits(current => ({ ...current, max_vision_tokens: Number(event.target.value) }))} /></label>
    </section><p className="settings-hint">Оценка токенов консервативна; фактический расход сообщает провайдер.</p><button className="settings-primary" disabled={active || busy} onClick={() => void save()}>Сохранить Vision</button>{notice ? <p role="status">{notice}</p> : null}
  </section>;
}
