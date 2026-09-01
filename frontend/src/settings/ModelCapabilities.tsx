import { useEffect, useState } from "react";
import { api } from "../api";
import type { Session } from "../types";

export function ModelCapabilities({ session, active, onSaved }: { session: Session; active: boolean; onSaved: () => void }) {
  const [vision, setVision] = useState(false);
  const [maximum, setMaximum] = useState(16384);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    let disposed = false;
    api.modelCapabilities(session.id).then(value => { if (!disposed) { setVision(value.vision); setMaximum(value.max_context); setLoading(false); } })
      .catch(error => { if (!disposed) setNotice(error.message); });
    return () => { disposed = true; };
  }, [session.id]);
  async function save(reset = false) {
    setBusy(true); setNotice("");
    try {
      const next = await api.updateCapabilities(session.id, reset ? {} : { vision, max_context: maximum });
      setVision(next.vision); setMaximum(next.max_context); onSaved(); setNotice(reset ? "Восстановлено определение провайдером" : "Возможности модели сохранены");
    } catch (error) { setNotice(error instanceof Error ? error.message : "Настройки не сохранены"); }
    finally { setBusy(false); }
  }
  return <details className="context-budget-footer">
    <summary>Возможности {session.model}</summary>
    <p>Ollama сообщает поддержку изображений автоматически. Для API подтвердите её по документации провайдера. Переопределение действует во всех чатах с этой моделью.</p>
    <div className="settings-card">
      <label className="settings-row"><span>Модель поддерживает изображения (vision)</span><input type="checkbox" checked={vision} disabled={active || busy || loading} onChange={event => setVision(event.target.checked)} /></label>
      <label className="settings-row"><span>Предел контекста провайдера, токенов</span><input type="number" min={1024} max={262144} value={maximum} disabled={active || busy || loading} onChange={event => setMaximum(Number(event.target.value))} /></label>
    </div>
    <p>Настройка не добавляет модели новые способности. Для текстовой модели используйте OCR: изображение останется локальным.</p>
    <button className="settings-primary" disabled={active || busy || loading || !Number.isInteger(maximum) || maximum < 1024 || maximum > 262144} onClick={() => void save()}>Сохранить возможности</button>
    <button className="text-button" disabled={active || busy || loading} onClick={() => void save(true)}>Определять автоматически</button>
    {notice ? <p role="status">{notice}</p> : null}
  </details>;
}
