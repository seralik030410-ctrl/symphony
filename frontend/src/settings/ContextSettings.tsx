import { FileText, FloppyDisk, Trash } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { IndexedSource, MemorySnapshot, Session } from "../types";
import { ContextBudget } from "./ContextBudget";
import { ModelCapabilities } from "./ModelCapabilities";

const empty: MemorySnapshot = { id: null, session_id: "", version: 0, facts: [], decisions: [], open_tasks: [], artifact_index: [], source_message_ids: [], created_at: null, updated_at: null };
const lines = (value: string) => value.split("\n").map(item => item.trim()).filter(Boolean);

export function ContextSettings({ session, active, onSessionSaved }: { session: Session | null; active: boolean; onSessionSaved: (session: Session) => void }) {
  const sessionId = session?.id ?? null;
  const [memory, setMemory] = useState<MemorySnapshot>(empty);
  const [sources, setSources] = useState<IndexedSource[]>([]);
  const [draft, setDraft] = useState({ facts: "", decisions: "", open_tasks: "", artifact_index: "" });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [versions, setVersions] = useState<MemorySnapshot[]>([]);
  const [budgetRevision, setBudgetRevision] = useState(0);
  function showMemory(next: MemorySnapshot) {
    setMemory(next); setDraft({ facts: next.facts.join("\n"), decisions: next.decisions.join("\n"), open_tasks: next.open_tasks.join("\n"), artifact_index: next.artifact_index.join("\n") });
    setVersions([]);
  }
  async function snapshot() {
    if (!sessionId || busy || active) return;
    setBusy(true); setMessage("Сжимаем старую часть разговора выбранной моделью…");
    try { const next = await api.createMemorySnapshot(sessionId); showMemory(next); setMessage(next.version === memory.version ? "Пока нечего сжимать: последние десять сообщений остаются дословными." : "Структурированная память обновлена"); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Не удалось сжать память"); }
    finally { setBusy(false); }
  }
  async function loadVersions() {
    if (!sessionId) return;
    try { setVersions(await api.memoryVersions(sessionId)); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Версии недоступны"); }
  }

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    Promise.all([api.getMemory(sessionId), api.listSources(sessionId)]).then(([nextMemory, nextSources]) => {
      if (cancelled) return;
      setMemory(nextMemory); setSources(nextSources.files);
      setDraft({ facts: nextMemory.facts.join("\n"), decisions: nextMemory.decisions.join("\n"), open_tasks: nextMemory.open_tasks.join("\n"), artifact_index: nextMemory.artifact_index.join("\n") });
    }).catch(error => { if (!cancelled) setMessage(error instanceof Error ? error.message : "Не удалось загрузить контекст"); });
    return () => { cancelled = true; };
  }, [sessionId]);

  async function save() {
    if (!sessionId || busy || active) return;
    setBusy(true); setMessage(null);
    try {
      const next = await api.updateMemory(sessionId, { facts: lines(draft.facts), decisions: lines(draft.decisions), open_tasks: lines(draft.open_tasks), artifact_index: lines(draft.artifact_index) });
      setMemory(next); setMessage("Память сохранена");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Память не сохранена"); }
    finally { setBusy(false); }
  }


  async function clear() {
    if (!sessionId || busy || active) return;
    setBusy(true); setMessage(null);
    try { await api.clearMemory(sessionId); showMemory(await api.getMemory(sessionId)); setMessage("Память очищена. История сохранена; при заполнении окна может быть создан новый снимок."); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Память не очищена"); }
    finally { setBusy(false); }
  }

  async function removeSource(path: string) {
    if (!sessionId || active || busy) return;
    try { await api.removeSource(sessionId, path); setSources(current => current.filter(item => item.path !== path)); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Источник не отключён"); }
  }

  async function reindex(path: string) {
    if (!sessionId || active || busy) return;
    setBusy(true); setMessage("Обновляем индекс файла…");
    try { await api.indexSource(sessionId, path); setSources((await api.listSources(sessionId)).files); setMessage("Индекс обновлён"); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Не удалось обновить индекс"); }
    finally { setBusy(false); }
  }

  return <section className="general-settings context-settings">
    <header className="settings-content-header"><div><h1>Контекст и память</h1><p>Только для текущего чата. Большие файлы попадают в prompt найденными фрагментами, а не целиком.</p></div></header>
    {session ? <><ContextBudget key={budgetRevision} session={session} active={active || busy} onSaved={onSessionSaved} /><ModelCapabilities session={session} active={active || busy} onSaved={() => setBudgetRevision(value => value + 1)} /></> : <p>Выберите чат, чтобы настроить контекст.</p>}
    {message ? <p className="context-settings-message" role="status">{message}</p> : null}
    <div className="context-heading"><div><h2>Память чата</h2><small>{memory.version ? `Версия ${memory.version} · ${memory.kind === "automatic" ? "сжато моделью" : memory.kind === "cleared" ? "очищено" : "изменено вручную"}` : "Снимков пока нет"}</small></div><button className="settings-primary" disabled={!sessionId || busy || active} onClick={() => void snapshot()}>{busy ? "Обрабатываем…" : "Сжать сейчас"}</button></div>
    <p className="settings-empty">При заполнении окна примерно на 72% старые сообщения сжимаются в факты, решения и задачи. Последние десять остаются дословными. Исходная история не удаляется.</p>
    <details className="context-budget-footer"><summary>Просмотреть и изменить память · {memory.source_message_ids.length} исходных сообщений</summary><section className="settings-card memory-editor">
      {[{ key: "facts", label: "Факты", hint: "Подтверждённые сведения и пути" }, { key: "decisions", label: "Решения", hint: "Принятые ограничения и выбор" }, { key: "open_tasks", label: "Открытые задачи", hint: "Что осталось сделать" }, { key: "artifact_index", label: "Артефакты", hint: "Созданные файлы и версии" }].map(field => <label key={field.key}><span><strong>{field.label}</strong><small>{field.hint}; один пункт на строку</small></span><textarea disabled={!sessionId || busy || active} value={draft[field.key as keyof typeof draft]} onChange={event => setDraft(current => ({ ...current, [field.key]: event.target.value }))} rows={4} /></label>)}
      <footer><button className="settings-primary" disabled={!sessionId || busy || active} onClick={() => void save()}><FloppyDisk size={16} /> Сохранить правки</button><button className="danger-text" disabled={!memory.id || busy || active} onClick={() => void clear()}><Trash size={16} /> Очистить память</button></footer>
    </section><button className="text-button" onClick={() => void loadVersions()}>История версий</button>{versions.map(version => <details key={version.id}><summary>Версия {version.version} · {version.source_message_ids.length} сообщений</summary><p>{version.facts.join(" · ") || "Нет фактов"}</p><p>{version.decisions.join(" · ")}</p><p>{version.open_tasks.join(" · ")}</p><p>{version.artifact_index.join(" · ")}</p><small>Исходные message IDs: {version.source_message_ids.join(", ") || "ручные записи"}</small></details>)}</details>
    <div className="context-heading"><div><h2>Индекс файлов</h2><small>{sources.length ? `${sources.length} файлов · ${sources.reduce((sum, item) => sum + item.chunk_count, 0)} фрагментов` : "Прикреплённые документы появятся здесь"}</small></div></div>
    <section className="settings-card source-list">{sources.length ? sources.map(source => <div className="source-row" key={source.id}><FileText size={18} /><span><strong title={source.path}>{source.path}</strong><small>{source.status === "failed" ? source.error : `${source.characters.toLocaleString("ru-RU")} знаков · ${source.chunk_count} фрагментов`}</small>{source.status === "failed" ? <button className="text-button" disabled={active || busy} onClick={() => void reindex(source.path)}>Обновить индекс</button> : null}</span><button className="icon-button" disabled={active || busy} aria-label={`Отключить ${source.path} от retrieval`} title="Не использовать в будущих ответах" onClick={() => void removeSource(source.path)}><Trash size={16} /></button></div>) : <p className="settings-empty">Прикрепите TXT, Markdown, PDF, DOCX, PPTX, XLSX, CSV или JSON. Индекс изолирован от других чатов.</p>}</section>
  </section>;
}
