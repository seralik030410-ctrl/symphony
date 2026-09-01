import { ArrowClockwise, ArrowsHorizontal, Code, FileText, Folder, GitDiff, Globe, Plus, SidebarSimple, X } from "@phosphor-icons/react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { api, type ProjectChanges, type ProjectFile, type ProjectSnapshot } from "../api";
import { CustomSelect } from "../ui/CustomSelect";
import type { TurnEvent } from "../types";
import { closeTab, diffRows, openTab, restoreWorkspace, type OpenWorkspace } from "./state";
import { ArtifactView } from "../artifacts/ArtifactView";
import type { ArtifactSummary } from "../api";

function SyntaxLine({ text }: { text: string }) {
  // Plain React text nodes: generated code is never injected as HTML or evaluated.
  return <>{text.split(/("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|\/\/.*$|\b(?:const|let|var|function|return|import|from|export|if|else|for|class|def|async|await|true|false|null|None)\b|\b\d+(?:\.\d+)?\b)/g).map((part, i) =>
    <span key={i} className={/^["']/.test(part) ? "syntax-string" : part.startsWith("//") ? "syntax-comment" : /^(const|let|var|function|return|import|from|export|if|else|for|class|def|async|await|true|false|null|None)$/.test(part) ? "syntax-keyword" : /^\d/.test(part) ? "syntax-number" : undefined}>{part}</span>)}</>;
}

function FileView({ sessionId, path, revision }: { sessionId: string; path: string; revision: number }) {
  const [file, setFile] = useState<ProjectFile | null>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    let stale = false;
    setFile(null); setError(""); setCopied(false);
    api.projectFile(sessionId, path).then(result => { if (!stale) setFile(result); }).catch(cause => { if (!stale) setError(String(cause.message)); });
    return () => { stale = true; };
  }, [sessionId, path, revision]);
  if (error) return <p className="workspace-notice" role="alert">{error}</p>;
  if (!file) return <p className="workspace-notice" role="status">Загружаем файл…</p>;
  if (file.binary) return <p className="workspace-notice">Двоичный файл · {file.size.toLocaleString()} байт. Текстовый просмотр недоступен.</p>;
  return <>
    <div className="file-meta"><span>Только чтение · {file.size.toLocaleString()} байт</span>
      <button className="text-button" onClick={async () => { try { await navigator.clipboard.writeText(file.content); setCopied(true); } catch { setError("Буфер обмена недоступен. Выделите код и скопируйте вручную."); } }}>{copied ? "Скопировано" : "Копировать"}</button></div>
    {file.truncated ? <p className="workspace-notice">Показаны первые 256 КБ файла.</p> : null}
    <div className="code-scroll" tabIndex={0} aria-label={`Код ${path}`}>
      <pre className="source-code">{file.content.split("\n").map((line, index) => <div className="code-line" key={index}><span className="line-number" aria-hidden="true">{index + 1}</span><code><SyntaxLine text={line || " "} /></code></div>)}</pre>
    </div>
  </>;
}

function ChangesView({ sessionId, revision, onFile }: { sessionId: string; revision: number; onFile: (path: string) => void }) {
  const [changes, setChanges] = useState<ProjectChanges | null>(null);
  const [snapshots, setSnapshots] = useState<ProjectSnapshot[]>([]);
  const [snapshot, setSnapshot] = useState("");
  const [error, setError] = useState("");
  const [split, setSplit] = useState(false);
  useEffect(() => {
    let stale = false;
    setChanges(null); setError("");
    Promise.all([api.projectChanges(sessionId, snapshot || undefined), api.projectSnapshots(sessionId)])
      .then(([result, items]) => { if (!stale) { setChanges(result); setSnapshots(items); } })
      .catch(cause => { if (!stale) setError(String(cause.message)); });
    return () => { stale = true; };
  }, [sessionId, snapshot, revision]);
  return <>
    <div className="changes-toolbar">
      <CustomSelect ariaLabel="Сравнить со снимком" value={snapshot} onChange={setSnapshot}
        options={[{ value: "", label: "До последнего изменения проекта", description: "Начало последнего turn со снимками" },
          ...snapshots.map(item => ({ value: item.id, label: `${item.operation} · ${new Date(item.created_at).toLocaleTimeString()}`, description: item.id.slice(0, 8) }))]} />
      <button className="icon-button" aria-label="Сравнение в две колонки" aria-pressed={split} title="Две колонки" onClick={() => setSplit(value => !value)}><ArrowsHorizontal size={19} /></button>
    </div>
    {error ? <p className="workspace-notice" role="alert">{error}</p> : !changes ? <p className="workspace-notice" role="status">Сравниваем файлы…</p> : <div className="changes-scroll" tabIndex={0} aria-label="Изменения проекта">
      {!changes.snapshot ? <p className="workspace-notice">Пока нет снимков. Они сохраняются перед каждой правкой или командой.</p>
        : !changes.files.length ? <p className="workspace-notice">Файлы не отличаются от выбранного снимка.</p> : null}
      {changes.files.map(file => <details className="diff-file" key={file.path} open>
        <summary><FileText size={16} /><span>{file.path}</span><small className="diff-added">+{file.additions}</small><small className="diff-removed">−{file.deletions}</small></summary>
        <div className="diff-caption"><span>{({ added: "Создан", deleted: "Удалён", modified: "Изменён", uncompared: "Не сравнивался" } as Record<string, string>)[file.status]}</span>{file.status !== "deleted" ? <button className="text-button" onClick={() => onFile(file.path)}>Открыть код</button> : null}</div>
        {file.binary ? <p className="workspace-notice">Двоичный файл изменён.</p> : null}
        {file.truncated ? <p className="workspace-notice">Сравнение ограничено размером; полное содержимое не показано.</p> : null}
        {file.diff ? <div className={`diff-code${split ? " diff-split" : ""}`}>
          {split ? <div className="diff-split-label"><span>До</span><span>Сейчас</span></div> : null}
          {diffRows(file.diff).map((row, index) => <div key={index} className={`diff-row diff-${row.kind}`}>
            {split && row.kind !== "hunk" ? <><div className={row.kind === "add" ? "diff-blank" : ""}><i>{row.old}</i><code>{row.kind !== "add" ? row.text : ""}</code></div><div className={row.kind === "remove" ? "diff-blank" : ""}><i>{row.next}</i><code>{row.kind !== "remove" ? row.text : ""}</code></div></>
              : <><i>{row.old}</i><i>{row.next}</i><code>{row.kind === "add" ? "+" : row.kind === "remove" ? "−" : " "} {row.text}</code></>}
          </div>)}
        </div> : null}
      </details>)}
      {changes.truncated ? <p className="workspace-notice">Показана часть изменений (лимит 200 файлов / 500 КБ diff).</p> : null}
      {changes.snapshot ? <p className="workspace-footnote">Текущие файлы ↔ снимок {changes.snapshot.id.slice(0, 8)}. Зависимости и кэши не сравниваются. Просмотр ничего не меняет.</p> : null}
    </div>}
  </>;
}

export function WorkspacePanel({ sessionId, events, request, visible, onClose }: {
  sessionId: string; events: TurnEvent[]; request: OpenWorkspace | null; visible: boolean; onClose: () => void;
}) {
  const storageKey = `symphony.workspace.${sessionId}`;
  const [state, setState] = useState(() => restoreWorkspace(localStorage.getItem(storageKey), sessionId, window.location.origin));
  const [revision, setRevision] = useState(0);
  const [files, setFiles] = useState<string[]>([]);
  const [artifacts, setArtifacts] = useState<ArtifactSummary[]>([]);
  const [treeError, setTreeError] = useState("");
  const [filter, setFilter] = useState("");
  const [width, setWidth] = useState(48);
  const dragging = useRef(false);
  const tabsRef = useRef<HTMLDivElement>(null);
  const active = state.tabs.find(tab => tab.id === state.activeId) ?? state.tabs[0];
  const changeId = [...events].reverse().find(event => ["file.changed", "tool.completed", "turn.completed"].includes(event.type))?.id ?? 0;
  const previews = useMemo(() => [...new Set(events.filter(event => event.type === "preview.ready").map(event => String(event.payload.preview_url)))], [events]);
  useEffect(() => { try { localStorage.setItem(storageKey, JSON.stringify(state)); } catch { /* Storage quota does not prevent inspection. */ } }, [state, storageKey]);
  useEffect(() => { if (request) setState(current => openTab(current, request)); }, [request]);
  useLayoutEffect(() => {
    const list = tabsRef.current;
    if (!list || !visible) return;
    const revealActive = () => {
      const tab = list.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]')?.parentElement;
      if (!tab) return;
      const outer = list.getBoundingClientRect(), inner = tab.getBoundingClientRect();
      if (inner.left < outer.left) list.scrollLeft -= outer.left - inner.left;
      else if (inner.right > outer.right) list.scrollLeft += inner.right - outer.right;
    };
    revealActive();
    const observer = new ResizeObserver(revealActive);
    observer.observe(list);
    return () => observer.disconnect();
  }, [state.activeId, visible]);
  useEffect(() => {
    if (!visible) return;
    let stale = false;
    Promise.all([api.projectTree(sessionId), api.listArtifacts(sessionId)]).then(([result, docs]) => { if (!stale) { setFiles(result.entries.filter(entry => entry.type === "file").map(entry => entry.path)); setArtifacts(docs.filter((doc, i) => docs.findIndex(item => item.id === doc.id) === i)); setTreeError(""); } })
      .catch(cause => { if (!stale) setTreeError(String(cause.message)); });
    return () => { stale = true; };
  }, [sessionId, revision, visible, changeId]);
  function open(kind: OpenWorkspace["kind"], path?: string) { setState(current => openTab(current, { nonce: Date.now(), kind, path })); }
  function selectTab(id: string) { setState(current => ({ ...current, activeId: id })); }
  return <aside className="workspace-panel" style={{ width: `${width}vw` }} hidden={!visible} aria-label="Рабочая панель проекта">
    <div className="workspace-resizer" role="separator" aria-label="Ширина рабочей панели" aria-orientation="vertical" aria-valuemin={32} aria-valuemax={65} aria-valuenow={width} tabIndex={0}
      onPointerDown={event => { dragging.current = true; event.currentTarget.setPointerCapture(event.pointerId); }}
      onPointerMove={event => { if (dragging.current) setWidth(Math.max(32, Math.min(65, Math.round((window.innerWidth - event.clientX) / window.innerWidth * 100)))); }}
      onPointerUp={() => { dragging.current = false; }} onPointerCancel={() => { dragging.current = false; }}
      onKeyDown={event => { if (["ArrowLeft", "ArrowRight"].includes(event.key)) { event.preventDefault(); setWidth(value => Math.max(32, Math.min(65, value + (event.key === "ArrowLeft" ? 2 : -2)))); } }} />
    <header className="workspace-tabs-bar">
      <div className="workspace-tabs" role="tablist" aria-label="Вкладки проекта" ref={tabsRef}>
        {state.tabs.map(tab => {
          const Icon = tab.kind === "preview" ? Globe : tab.kind === "changes" ? GitDiff : tab.kind === "file" ? Code : tab.kind === "artifact" ? FileText : tab.kind === "files" ? Folder : Plus;
          const tabTitle = tab.kind === "artifact" ? artifacts.find(doc => doc.id === tab.path)?.title ?? tab.title : tab.title;
          return <div className="workspace-tab" data-active={tab.id === active.id} key={tab.id}>
            <button role="tab" id={`tab-${tab.id}`} aria-controls="workspace-tab-content" aria-selected={tab.id === active.id} tabIndex={tab.id === active.id ? 0 : -1}
              onClick={() => selectTab(tab.id)} onKeyDown={event => {
                const index = state.tabs.findIndex(item => item.id === tab.id);
                if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
                  event.preventDefault();
                  const next = event.key === "Home" ? 0 : event.key === "End" ? state.tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + state.tabs.length) % state.tabs.length;
                  selectTab(state.tabs[next].id); (tabsRef.current?.querySelectorAll('[role="tab"]')[next] as HTMLElement)?.focus();
                } else if (event.key === "Delete") { event.preventDefault(); setState(current => closeTab(current, tab.id)); }
              }}><Icon size={16} /><span>{tabTitle}</span></button>
            <button className="tab-close" aria-label={`Закрыть вкладку ${tabTitle}`} onClick={() => setState(current => closeTab(current, tab.id))}><X size={14} /></button>
          </div>;
        })}
      </div>
      <button className="icon-button" aria-label="Добавить вкладку" title="Добавить вкладку" onClick={() => open("new")}><Plus size={18} /></button>
      <button className="icon-button" aria-label="Скрыть рабочую панель" title="Скрыть панель" onClick={onClose}><SidebarSimple size={18} /></button>
    </header>
    <div className="workspace-address"><span title={active.path ?? ""}>{active.kind === "artifact" ? "Документ текущего чата · Сохранённые версии" : active.path?.replace(`/api/sessions/${sessionId}/preview/`, "/workspace/") ?? (active.kind === "changes" ? "Сравнение сохранённого проекта" : "Проект текущего чата")}</span>
      <button className="icon-button" aria-label="Обновить содержимое панели" title="Обновить" onClick={() => setRevision(value => value + 1)}><ArrowClockwise size={17} /></button></div>
    <section id="workspace-tab-content" className="workspace-tab-content" role="tabpanel" aria-labelledby={`tab-${active.id}`}>
      {active.kind === "preview" ? <iframe key={`${active.id}:${revision}`} title="Предпросмотр созданного сайта" src={active.path} sandbox="allow-scripts" referrerPolicy="no-referrer" />
        : active.kind === "file" ? <FileView key={active.id} sessionId={sessionId} path={active.path!} revision={revision + changeId} />
        : active.kind === "artifact" ? <ArtifactView key={active.id} sessionId={sessionId} artifactId={active.path!} revision={revision + changeId} />
        : active.kind === "changes" ? <ChangesView sessionId={sessionId} revision={revision + changeId} onFile={path => open("file", path)} />
        : <div className="workspace-launcher">
          <h2>{active.kind === "files" ? "Файлы проекта" : "Новая вкладка"}</h2><p>{active.kind === "files" ? "Файлы текущего чата. Выберите файл, чтобы открыть его код в отдельной вкладке." : "Откройте сборку, исходный файл или сравнение изменений рядом с чатом."}</p>
          {artifacts.length ? <><h3>Документы</h3>{artifacts.map(doc => <button className="workspace-choice" key={doc.id} onClick={() => open("artifact", doc.id)}><FileText size={20} /><span>{doc.title}<small>{doc.format.toUpperCase()} · Версия {doc.version}</small></span></button>)}</> : null}
          {active.kind === "new" ? <>
          <button className="workspace-choice" onClick={() => open("changes")}><GitDiff size={20} /><span>Изменения проекта<small>Сравнить со снимком до правок</small></span></button>
          {previews.map(url => <button className="workspace-choice" key={url} onClick={() => open("preview", url)}><Globe size={20} /><span>Preview<small>{url.split("/preview/")[1]}</small></span></button>)}
          {!previews.length ? <p className="workspace-notice">Готовые сборки появятся здесь после создания preview.</p> : null}
          <h3>Файлы проекта</h3></> : null}<input aria-label="Найти файл проекта" placeholder="Найти файл…" value={filter} onChange={event => setFilter(event.target.value)} />
          {treeError ? <p role="alert">{treeError}</p> : null}
          <ul className="workspace-files">{files.filter(path => path.toLowerCase().includes(filter.toLowerCase())).map(path => <li key={path}><button onClick={() => open("file", path)}><FileText size={16} /><span>{path}</span></button></li>)}</ul>
          {!files.length && !treeError ? <p className="workspace-notice">В этом чате пока нет файлов.</p> : null}
          {files.length >= 450 ? <p className="workspace-notice">Дерево ограничено 500 записями.</p> : null}
        </div>}
    </section>
  </aside>;
}
