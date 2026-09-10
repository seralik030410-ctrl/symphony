import { ArrowClockwise, CheckCircle, DownloadSimple, FileArrowDown, FileArrowUp, FilmStrip, ImageSquare, Plug, Trash, X } from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Session } from "../types";
import "./workspace.css";

type Tab = "generate" | "workflow" | "queue" | "gallery";
type Kind = "image" | "video";
type JobStatus = "queued" | "preparing" | "running" | "paused" | "completed" | "failed" | "cancelled";
type Asset = { id: string; filename: string; kind: string; size: number; preview_url: string | null; download_url: string; provenance: Record<string, unknown> };
type Job = { id: string; kind: string; status: JobStatus; progress: number; input: Record<string, unknown>; result_asset_id: string | null; error_message: string | null; cancel_requested: boolean };
type Binding = { name: string; type: "string" | "integer" | "number" | "boolean"; required: boolean; minimum: number | null; maximum: number | null; choices: string[] };
type Template = { id: string; title: string; kind: Kind; version: number; bindings: Binding[] };
type Connection = { configured: boolean; origin: string | null; studio_url: string | null; managed_process_running: boolean };
type Recent = { title: string; workflow: Record<string, unknown>; savedAt: string };

const API = "/api";
const ACTIVE = new Set<JobStatus>(["queued", "preparing", "running", "paused"]);
const TAB_KEY = "fincctrl.media.workspace.tab";
const RECENTS_KEY = "fincctrl.media.workspace.recents";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, { ...init, headers: { "Content-Type": "application/json", ...init?.headers } });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail ?? `HTTP ${response.status}`);
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

function getRecents(): Recent[] {
  try { const value = JSON.parse(localStorage.getItem(RECENTS_KEY) ?? "[]"); return Array.isArray(value) ? value.slice(0, 12) : []; }
  catch { return []; }
}

function saveRecents(value: Recent[]) { localStorage.setItem(RECENTS_KEY, JSON.stringify(value.slice(0, 12))); }
function bytes(size: number) { return size > 999_999 ? `${(size / 1_000_000).toFixed(1)} МБ` : `${Math.ceil(size / 1_000)} КБ`; }
const labels: Record<JobStatus, string> = { queued: "В очереди", preparing: "Подготовка", running: "Выполняется", paused: "Приостановлено", completed: "Готово", failed: "Ошибка", cancelled: "Отменено" };

export function ComfyConnectionPanel({ origin, allowPrivate, busy, onOriginChange, onAllowPrivateChange, onConnect }: {
  origin: string;
  allowPrivate: boolean;
  busy: boolean;
  onOriginChange: (value: string) => void;
  onAllowPrivateChange: (value: boolean) => void;
  onConnect: () => void;
}) {
  return <section className="workspace-connect" aria-labelledby="comfy-connect-title">
    <div className="workspace-connect-heading">
      <span className="workspace-connect-icon"><Plug size={20} aria-hidden="true" /></span>
      <div><h2 id="comfy-connect-title">Подключить ComfyUI</h2><p>FinCtrl подключается к уже запущенному ComfyUI на этом компьютере.</p></div>
    </div>
    <ol className="workspace-connect-steps">
      <li><strong>Запустите ComfyUI</strong><span>Дождитесь, пока в его окне появится адрес сервера.</span></li>
      <li><strong>Проверьте адрес</strong><span>Обычно менять значение ниже не нужно.</span></li>
    </ol>
    <label className="workspace-url-field"><span>Адрес ComfyUI</span><input value={origin} onChange={event => onOriginChange(event.target.value)} placeholder="http://127.0.0.1:8188" spellCheck={false} /></label>
    <details className="workspace-connect-advanced">
      <summary>Дополнительные настройки</summary>
      <label><input type="checkbox" checked={allowPrivate} onChange={event => onAllowPrivateChange(event.target.checked)} /> Разрешить подключение к локальному адресу</label>
    </details>
    <footer><button className="workspace-connect-action" disabled={busy || !origin.trim()} onClick={onConnect}>{busy ? "Проверяем…" : "Проверить и подключить"}</button><small>FinCtrl проверит соединение перед первой генерацией.</small></footer>
  </section>;
}

export function MediaWorkspace({ session, onAttachAsset }: { session: Session | null; onAttachAsset?: (assetId: string) => void }) {
  const [tab, setTab] = useState<Tab>(() => (localStorage.getItem(TAB_KEY) as Tab) || "generate");
  const [connection, setConnection] = useState<Connection | null>(null);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selected, setSelected] = useState("image-basic");
  const [values, setValues] = useState<Record<string, string | number>>({ prompt: "", negative_prompt: "", width: 1024, height: 1024, seed: 1, steps: 28, guidance: 7, fps: 8 });
  const [origin, setOrigin] = useState("http://127.0.0.1:8188");
  const [allowPrivate, setAllowPrivate] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [editingConnection, setEditingConnection] = useState(false);
  const [iframeFailed, setIframeFailed] = useState(false);
  const [recents, setRecents] = useState<Recent[]>(getRecents);
  const fileInput = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      const [nextConnection, nextTemplates, nextAssets, nextJobs] = await Promise.all([
        api<Connection>("/comfyui/connection"), api<Template[]>("/comfyui/templates"),
        session ? api<Asset[]>(`/sessions/${session.id}/media/assets`) : Promise.resolve([]),
        session ? api<Job[]>(`/sessions/${session.id}/media/jobs`) : Promise.resolve([]),
      ]);
      setConnection(nextConnection); setTemplates(nextTemplates); setAssets(nextAssets); setJobs(nextJobs); setError("");
      if (nextConnection.origin) setOrigin(nextConnection.origin);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Не удалось загрузить Media Workspace"); }
  }, [session]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { localStorage.setItem(TAB_KEY, tab); }, [tab]);
  useEffect(() => {
    if (!jobs.some(job => ACTIVE.has(job.status))) return;
    const timer = window.setInterval(() => void refresh(), 1300);
    return () => window.clearInterval(timer);
  }, [jobs, refresh]);

  const template = useMemo(() => templates.find(item => item.id === selected) ?? templates[0], [selected, templates]);
  const kind: Kind = template?.kind ?? "image";

  async function action(work: () => Promise<void>) {
    setBusy(true); setError("");
    try { await work(); await refresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Операция не удалась"); }
    finally { setBusy(false); }
  }

  async function connect() {
    await action(async () => {
      await api("/comfyui/connection", { method: "PUT", body: JSON.stringify({ base_url: origin, allow_private_network: allowPrivate }) });
      await api("/comfyui/health", { method: "POST" });
      setIframeFailed(false);
      setEditingConnection(false);
    });
  }

  async function generate() {
    if (!session || !template) return;
    const normalized: Record<string, string | number> = {};
    for (const binding of template.bindings) {
      const value = values[binding.name];
      if (value === "" || value === undefined) continue;
      normalized[binding.name] = binding.type === "integer" || binding.type === "number" ? Number(value) : value;
    }
    await action(async () => {
      await api(`/comfyui/sessions/${session.id}/quick`, { method: "POST", body: JSON.stringify({ kind, template_id: template.id, values: normalized }) });
      setTab("queue");
    });
  }

  function exportRecent(recent: Recent) {
    const blob = new Blob([JSON.stringify(recent.workflow, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob); const anchor = document.createElement("a");
    anchor.href = url; anchor.download = `${recent.title.replace(/[^\w.-]+/g, "-") || "workflow"}.json`; anchor.click(); URL.revokeObjectURL(url);
  }

  async function importWorkflow(file: File | undefined) {
    if (!session || !file) return;
    await action(async () => {
      const workflow = JSON.parse(await file.text()) as Record<string, unknown>;
      const saved = await api<{ title: string; workflow: Record<string, unknown> }>(`/comfyui/sessions/${session.id}/workflows/import`, {
        method: "POST", body: JSON.stringify({ title: file.name.replace(/\.json$/i, ""), workflow }),
      });
      const next = [{ ...saved, savedAt: new Date().toISOString() }, ...recents.filter(item => JSON.stringify(item.workflow) !== JSON.stringify(saved.workflow))];
      setRecents(next); saveRecents(next); setTab("workflow");
    });
  }

  async function runRecent(recent: Recent) {
    if (!session) return;
    await action(async () => {
      await api(`/comfyui/sessions/${session.id}/workflows/run`, { method: "POST", body: JSON.stringify({ title: recent.title, workflow: recent.workflow, kind: "image" }) });
      setTab("queue");
    });
  }

  if (!session) return <section className="media-workspace media-workspace-empty"><FilmStrip size={32} /><h2>Создайте или выберите чат</h2><p>Очередь и результаты генерации остаются изолированными внутри чата.</p></section>;

  return <section className="media-workspace" aria-label="Media Workspace">
    <header className="workspace-header"><div><h1>Медиа</h1><p>Создание изображений и видео в текущем чате</p></div><button className="workspace-refresh" onClick={() => void refresh()} disabled={busy}><ArrowClockwise size={16} /> Обновить</button></header>
    {connection?.configured && !editingConnection ? <div className="workspace-connected" role="status"><CheckCircle size={17} weight="fill" /><span><strong>ComfyUI подключён</strong><small>{connection.origin}</small></span><button onClick={() => setEditingConnection(true)}>Изменить</button></div> : null}
    <nav className="workspace-tabs" aria-label="Разделы медиа">
      {(["generate", "workflow", "queue", "gallery"] as Tab[]).map(item => <button key={item} onClick={() => setTab(item)} aria-current={tab === item ? "page" : undefined}>{({ generate: "Создать", workflow: "Расширенный режим", queue: `Очередь${jobs.some(job => ACTIVE.has(job.status)) ? " ·" : ""}`, gallery: "Галерея" })[item]}</button>)}
    </nav>
    {error && <p className="workspace-error" role="alert">{error}</p>}
    {(!connection?.configured || editingConnection) && <ComfyConnectionPanel origin={origin} allowPrivate={allowPrivate} busy={busy} onOriginChange={setOrigin} onAllowPrivateChange={setAllowPrivate} onConnect={() => void connect()} />}
    {tab === "generate" && <div className="workspace-generate">
      <div className="workspace-template-list">{templates.map(item => <button key={item.id} className={selected === item.id ? "selected" : ""} onClick={() => setSelected(item.id)}><ImageSquare size={18} /><span>{item.title}</span><small>{item.kind === "image" ? "Image" : "Video"}</small></button>)}</div>
      <div className="workspace-form"><h2>{template?.title ?? "Шаблон"}</h2>{template?.bindings.map(binding => <label key={binding.name}>{binding.name === "prompt" ? "Промпт" : binding.name === "negative_prompt" ? "Негативный промпт" : binding.name}
        {binding.type === "string" ? <textarea required={binding.required} value={String(values[binding.name] ?? "")} onChange={event => setValues(current => ({ ...current, [binding.name]: event.target.value }))} /> : <input type="number" min={binding.minimum ?? undefined} max={binding.maximum ?? undefined} value={Number(values[binding.name] ?? binding.minimum ?? 0)} onChange={event => setValues(current => ({ ...current, [binding.name]: event.target.valueAsNumber }))} />}
      </label>)}<button className="text-button primary" disabled={busy || !connection?.configured || !String(values.prompt ?? "").trim()} onClick={() => void generate()}>{kind === "image" ? "Создать изображение" : "Создать видео"}</button></div>
    </div>}
    {tab === "workflow" && <div className="workspace-studio">
      <aside><h2>Workflow Studio</h2><p>Официальный интерфейс ComfyUI открыт внутри приложения через контролируемый same-origin proxy.</p><input ref={fileInput} hidden type="file" accept="application/json,.json" onChange={event => void importWorkflow(event.target.files?.[0])} /><button onClick={() => fileInput.current?.click()}><FileArrowUp size={15} /> Импорт JSON</button><h3>Недавние</h3>{!recents.length && <p className="workspace-muted">Импортированные workflow появятся здесь. Импорт сам ничего не запускает.</p>}{recents.map(recent => <div className="workspace-recent" key={`${recent.title}-${recent.savedAt}`}><span>{recent.title}</span><button title="Экспорт" onClick={() => exportRecent(recent)}><FileArrowDown size={15} /></button><button disabled={busy || !connection?.configured} onClick={() => void runRecent(recent)}>Запустить</button></div>)}</aside>
      <div className="workspace-iframe-wrap">{connection?.configured && !iframeFailed ? <iframe title="ComfyUI Workflow Studio" src={connection.studio_url ?? "/api/comfyui/proxy/"} onError={() => setIframeFailed(true)} sandbox="allow-scripts allow-forms allow-same-origin allow-downloads" /> : <div className="workspace-fallback"><FilmStrip size={30} /><strong>Studio недоступна</strong><p>Установка может использовать custom node UI, несовместимый со встраиванием. Используйте импорт JSON и Quick Generate либо откройте ComfyUI отдельно.</p></div>}</div>
    </div>}
    {tab === "queue" && <div className="workspace-queue">{!jobs.length && <p className="workspace-muted">В очереди пока нет генераций.</p>}{jobs.map(job => <article key={job.id}><div><strong>{job.kind.endsWith("video") ? "Генерация видео" : "Генерация изображения"}</strong><small>{labels[job.status]}</small></div><code>{Math.round(job.progress * 100)}%</code><div className="workspace-progress"><i style={{ width: `${job.progress * 100}%` }} /></div>{job.error_message && <p className="workspace-error">{job.error_message}</p>}<footer>{ACTIVE.has(job.status) && <button disabled={busy || job.cancel_requested} onClick={() => void action(async () => { await api(`/sessions/${session.id}/media/jobs/${job.id}/cancel`, { method: "POST" }); })}><X size={15} /> Отменить</button>}{["failed", "cancelled"].includes(job.status) && <button disabled={busy} onClick={() => void action(async () => { await api(`/sessions/${session.id}/media/jobs/${job.id}/retry`, { method: "POST" }); })}>Повторить</button>}{Boolean(job.input.workflow) && <button onClick={() => setTab("workflow")}>Открыть workflow</button>}</footer></article>)}</div>}
    {tab === "gallery" && <div className="workspace-gallery">{!assets.length && <p className="workspace-muted">Готовые изображения и видео появятся здесь.</p>}{assets.map(asset => <article key={asset.id}><div>{asset.preview_url ? <img src={asset.preview_url} alt="" /> : <ImageSquare size={28} />}</div><strong title={asset.filename}>{asset.filename}</strong><small>{asset.kind} · {bytes(asset.size)}</small><footer><a href={asset.download_url} download><DownloadSimple size={15} /> Скачать</a>{onAttachAsset && <button onClick={() => onAttachAsset(asset.id)}>Прикрепить</button>}<button className="danger" disabled={busy} onClick={() => void action(async () => { await api(`/sessions/${session.id}/media/assets/${asset.id}`, { method: "DELETE" }); })}><Trash size={15} /></button></footer></article>)}</div>}
  </section>;
}
