import { ArrowClockwise, ArrowCounterClockwise, DownloadSimple, ImageSquare, Trash, UploadSimple, X } from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { MediaAsset, MediaJob, Session } from "../types";
import "./media.css";

type View = "gallery" | "queue" | "trash";
const ACTIVE = new Set<MediaJob["status"]>(["queued", "preparing", "running", "paused"]);

function bytes(value: number) {
  if (value < 1_000_000) return `${Math.ceil(value / 1_000)} КБ`;
  return `${(value / 1_000_000).toFixed(1)} МБ`;
}

function base64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error ?? new Error("Не удалось прочитать файл"));
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] ?? "");
    reader.readAsDataURL(file);
  });
}

const statusLabel: Record<MediaJob["status"], string> = {
  queued: "В очереди", preparing: "Подготовка", running: "Выполняется", paused: "Приостановлено",
  completed: "Готово", failed: "Ошибка", cancelled: "Отменено",
};

export function MediaLibrary({ session }: { session: Session | null }) {
  const [view, setView] = useState<View>("gallery");
  const [assets, setAssets] = useState<MediaAsset[]>([]);
  const [jobs, setJobs] = useState<MediaJob[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    if (!session) return;
    try {
      const [nextAssets, nextJobs] = await Promise.all([
        api.listMediaAssets(session.id, view === "trash"), api.listMediaJobs(session.id),
      ]);
      setAssets(nextAssets); setJobs(nextJobs); setError("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Не удалось загрузить медиа"); }
  }, [session, view]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (!session || !jobs.some(job => ACTIVE.has(job.status))) return;
    const timer = window.setInterval(() => void refresh(), 1200);
    return () => window.clearInterval(timer);
  }, [jobs, refresh, session]);

  async function upload(files: FileList | null) {
    if (!session || !files?.length) return;
    setBusy(true); setError("");
    try {
      for (const file of Array.from(files)) {
        await api.uploadMediaAsset(session.id, { filename: file.name, mime_type: file.type, content_base64: await base64(file) });
      }
      await refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Загрузка не удалась"); }
    finally { setBusy(false); if (input.current) input.current.value = ""; }
  }

  async function act(action: () => Promise<unknown>) {
    setBusy(true); setError("");
    try { await action(); await refresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Операция не удалась"); }
    finally { setBusy(false); }
  }

  if (!session) return <section className="media-settings settings-first-use"><ImageSquare size={34} /><h2>Сначала создайте чат</h2><p>Галерея и очередь изолированы для каждого чата.</p></section>;

  return <section className="media-settings">
    <header className="settings-content-header media-heading"><div><h1>Медиа</h1><p>Файлы текущего чата, фоновые операции и корзина.</p></div>
      <input ref={input} hidden type="file" multiple accept="image/png,image/jpeg,image/webp,image/gif,video/mp4,video/webm,audio/wav,audio/mpeg,audio/webm,audio/ogg,audio/mp4" onChange={event => void upload(event.target.files)} />
      <button className="text-button primary" disabled={busy} onClick={() => input.current?.click()}><UploadSimple size={16} /> Загрузить</button>
    </header>
    <nav className="media-tabs" aria-label="Медиа-разделы">
      {(["gallery", "queue", "trash"] as View[]).map(item => <button key={item} aria-current={view === item ? "page" : undefined} onClick={() => setView(item)}>{item === "gallery" ? "Галерея" : item === "queue" ? `Очередь${jobs.some(job => ACTIVE.has(job.status)) ? " ·" : ""}` : "Корзина"}</button>)}
    </nav>
    {error && <p className="settings-error">{error}</p>}
    {view === "queue" ? <div className="media-queue">
      {!jobs.length && <p className="media-empty">Фоновых операций пока нет.</p>}
      {jobs.map(job => <article className="media-job" key={job.id}><div className="media-job-top"><div><strong>Создание превью</strong><small>{statusLabel[job.status]} · попытка {job.attempt}</small></div><code>{Math.round(job.progress * 100)}%</code></div>
        <div className="media-progress"><i style={{ width: `${job.progress * 100}%` }} /></div>
        {job.error_message && <p>{job.error_message}</p>}
        <div className="media-actions">{ACTIVE.has(job.status) && <button disabled={busy || job.cancel_requested} onClick={() => void act(() => api.cancelMediaJob(session.id, job.id))}><X size={14} /> Отменить</button>}
          {(job.status === "failed" || job.status === "cancelled") && <button disabled={busy} onClick={() => void act(() => api.retryMediaJob(session.id, job.id))}><ArrowCounterClockwise size={14} /> Повторить</button>}</div>
      </article>)}
    </div> : <div className="media-grid">
      {!assets.length && <p className="media-empty">{view === "trash" ? "Корзина пуста." : "Загрузите изображение, видео или аудио."}</p>}
      {assets.map(asset => <article className="media-card" key={asset.id}><div className="media-preview">{asset.preview_url ? <img src={asset.preview_url} alt="" /> : <ImageSquare size={28} />}</div><div className="media-card-body"><strong title={asset.filename}>{asset.filename}</strong><small>{asset.kind} · {bytes(asset.size)}</small><div className="media-actions">
        {view === "trash" ? <><button disabled={busy} onClick={() => void act(() => api.restoreMediaAsset(session.id, asset.id))}><ArrowCounterClockwise size={14} /> Вернуть</button><button className="danger" disabled={busy} onClick={() => window.confirm(`Удалить «${asset.filename}» навсегда?`) && void act(() => api.purgeMediaAsset(session.id, asset.id))}><Trash size={14} /> Удалить</button></>
          : <><a href={asset.download_url} download><DownloadSimple size={14} /> Скачать</a><button disabled={busy} title="Пересоздать превью в фоне" onClick={() => void act(() => api.createMediaJob(session.id, asset.id))}><ArrowClockwise size={14} /> Превью</button><button disabled={busy} aria-label={`В корзину: ${asset.filename}`} onClick={() => void act(() => api.trashMediaAsset(session.id, asset.id))}><Trash size={14} /></button></>}
      </div></div></article>)}
    </div>}
  </section>;
}
