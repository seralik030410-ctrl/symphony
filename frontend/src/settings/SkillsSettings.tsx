import { ArrowCounterClockwise, CheckCircle, DownloadSimple, File as FileIcon, FolderOpen, GitBranch, MagnifyingGlass, Package, Plus, Trash, UploadSimple, WarningCircle, X } from "@phosphor-icons/react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { SkillDetail, SkillMatch, SkillMode, SkillSummary } from "../types";
import { CustomSelect } from "../ui/CustomSelect";
import { Dialog } from "../ui/Dialog";

function bytesToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer); let result = "";
  for (let offset = 0; offset < bytes.length; offset += 32_768) {
    result += String.fromCharCode(...bytes.subarray(offset, offset + 32_768));
  }
  return btoa(result);
}

const modeOptions = [
  { value: "off", label: "Выключен", description: "Не выбирается даже по явному имени" },
  { value: "explicit", label: "Только явно", description: "Активируется через $имя-навыка" },
  { value: "auto", label: "Автоматически", description: "Сопоставляется с description запроса" },
  { value: "always", label: "Всегда", description: "Загружается в каждый новый turn" },
];

export function SkillsSettings() {
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<SkillDetail | null>(null);
  const [editor, setEditor] = useState("");
  const [priority, setPriority] = useState(50);
  const [dirty, setDirty] = useState(false);
  const [filter, setFilter] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [installOpen, setInstallOpen] = useState(false);
  const [trash, setTrash] = useState<SkillSummary[] | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [resource, setResource] = useState<{ path: string; content: string; truncated: boolean } | null>(null);
  const [testPrompt, setTestPrompt] = useState("");
  const [match, setMatch] = useState<SkillMatch | null>(null);

  async function refresh(preferred?: string) {
    const items = await api.listSkills(); setSkills(items);
    const id = preferred ?? selectedId ?? items[0]?.id ?? null;
    setSelectedId(items.some(item => item.id === id) ? id : items[0]?.id ?? null);
  }
  useEffect(() => { refresh().catch(cause => setError(String(cause.message))); }, []);
  useEffect(() => {
    if (!selectedId) { setDetail(null); return; }
    let stale = false; setResource(null); setError("");
    api.getSkill(selectedId).then(value => { if (!stale) { setDetail(value); setEditor(value.skill_md); setPriority(value.priority); setDirty(false); } })
      .catch(cause => { if (!stale) setError(String(cause.message)); });
    return () => { stale = true; };
  }, [selectedId]);
  const visible = useMemo(() => skills.filter(skill => `${skill.name} ${skill.description} ${skill.slug}`.toLowerCase().includes(filter.toLowerCase())), [skills, filter]);

  function select(id: string) {
    if (dirty) { setNotice("Сохраните или отмените изменения SKILL.md перед переключением."); return; }
    setNotice(""); setMatch(null); setSelectedId(id);
  }
  async function changeMode(mode: SkillMode) {
    if (!detail) return;
    try { const value = await api.updateSkill(detail.id, { mode }); setDetail(value); await refresh(value.id); }
    catch (cause) { setError(String((cause as Error).message)); }
  }
  async function validate() {
    try { const result = await api.validateSkill(editor); setNotice(`Manifest корректен: ${result.name} · $${result.slug}`); setError(""); }
    catch (cause) { setError(String((cause as Error).message)); }
  }
  async function save() {
    if (!detail || busy) return; setBusy(true);
    try { const value = await api.updateSkill(detail.id, { skill_md: editor, priority }); setDetail(value); setDirty(false); setNotice("Изменения сохранены. Новые turn используют обновлённую версию."); await refresh(value.id); }
    catch (cause) { setError(String((cause as Error).message)); } finally { setBusy(false); }
  }
  async function openResource(path: string) {
    if (!detail) return;
    try { setResource(await api.skillResource(detail.id, path)); }
    catch (cause) { setError(String((cause as Error).message)); }
  }
  async function runTest() {
    if (!testPrompt.trim()) return;
    try { setMatch(await api.testSkillPrompt(testPrompt)); }
    catch (cause) { setError(String((cause as Error).message)); }
  }
  async function remove() {
    if (!detail) return;
    try { await api.trashSkill(detail.id); setDeleteOpen(false); setDetail(null); setSelectedId(null); await refresh(); setNotice("Навык перемещён в корзину и больше не активируется."); }
    catch (cause) { setError(String((cause as Error).message)); }
  }
  async function showTrash() { try { setTrash(await api.listSkillTrash()); } catch (cause) { setError(String((cause as Error).message)); } }
  async function restore(id: string) { try { const value = await api.restoreSkill(id); setTrash(await api.listSkillTrash()); await refresh(value.id); } catch (cause) { setError(String((cause as Error).message)); } }

  return <section className="skills-settings" aria-labelledby="skills-title">
    <header className="settings-content-header"><div><h1 id="skills-title">Навыки</h1><p>Локальные workflow-инструкции с progressive disclosure.</p></div>
      <button className="text-button" onClick={() => setInstallOpen(true)}><Plus size={17} /> Установить</button>
      <button className="icon-button" aria-label="Корзина навыков" title="Корзина" onClick={() => void showTrash()}><Trash size={18} /></button></header>
    {error ? <div className="settings-alert" role="alert"><WarningCircle size={17} /><span>{error}</span><button aria-label="Закрыть ошибку" onClick={() => setError("")}><X size={15} /></button></div> : null}
    {notice ? <div className="settings-alert settings-success" role="status"><CheckCircle size={17} /><span>{notice}</span><button aria-label="Закрыть сообщение" onClick={() => setNotice("")}><X size={15} /></button></div> : null}
    <div className="skills-layout">
      <aside className="skills-index" aria-label="Установленные навыки">
        <label className="settings-search"><MagnifyingGlass size={16} /><input aria-label="Найти навык" placeholder="Найти навык…" value={filter} onChange={event => setFilter(event.target.value)} /></label>
        <div className="skills-count">{visible.length} установлено</div>
        <nav>{visible.map(skill => <button key={skill.id} className={skill.id === selectedId ? "selected" : ""} onClick={() => select(skill.id)} aria-current={skill.id === selectedId ? "page" : undefined}>
          <Package size={17} /><span><strong>{skill.name}</strong><small>{skill.mode === "off" ? "Выключен" : skill.mode === "explicit" ? `$${skill.slug}` : skill.mode === "always" ? "Всегда" : "Авто"}</small></span></button>)}</nav>
        {!visible.length ? <p className="settings-empty">Навыков по этому запросу нет.</p> : null}
      </aside>
      <div className="skill-editor">
        {!detail ? <div className="settings-first-use"><Package size={28} /><h2>Установите первый навык</h2><p>ZIP, локальная папка или HTTPS Git URL. Навык не получает разрешений сам по себе.</p><button className="text-button" onClick={() => setInstallOpen(true)}>Установить навык</button></div> : <>
          <header className="skill-title"><div><h2>{detail.name}</h2><p>{detail.description}</p><code>${detail.slug}</code></div>
            <a className="icon-button" aria-label="Экспортировать навык" title="Экспорт ZIP" href={`/api/skills/${detail.id}/export`}><DownloadSimple size={18} /></a>
            <button className="icon-button" aria-label="Удалить навык" title="В корзину" onClick={() => setDeleteOpen(true)}><Trash size={18} /></button></header>
          <section className="settings-card"><h3>Активация</h3><div className="settings-row"><div><strong>Режим</strong><small>Определяет, когда host загрузит полный SKILL.md.</small></div><CustomSelect ariaLabel="Режим активации навыка" value={detail.mode} options={modeOptions} onChange={value => void changeMode(value as SkillMode)} /></div>
            <div className="settings-row"><label htmlFor="skill-priority"><strong>Priority</strong><small>Дополнительный сигнал, не разрешение и не гарантия выбора.</small></label><input id="skill-priority" type="number" min={0} max={100} value={priority} onChange={event => { setPriority(Number(event.target.value)); setDirty(true); }} /></div>
            <dl className="skill-metadata"><div><dt>Источник</dt><dd>{detail.source_type}</dd></div><div><dt>Ресурсы</dt><dd>{detail.resources.length}</dd></div><div><dt>Зависимости</dt><dd>{Array.isArray(detail.manifest.dependencies) ? detail.manifest.dependencies.join(", ") || "Нет" : "Нет"}</dd></div></dl>
          </section>
          <section className="settings-card skill-md-section"><div className="section-heading"><div><h3>SKILL.md</h3><p>Полный текст читается только после активации.</p></div><button className="text-button" onClick={() => { setEditor(detail.skill_md); setPriority(detail.priority); setDirty(false); }}>Отменить</button><button className="text-button" onClick={() => void validate()}>Проверить</button><button className="settings-primary" disabled={!dirty || busy} onClick={() => void save()}>{busy ? "Сохраняем…" : "Сохранить"}</button></div>
            <textarea aria-label="Редактор SKILL.md" spellCheck={false} value={editor} onChange={event => { setEditor(event.target.value); setDirty(true); }} /></section>
          <section className="settings-card"><h3>Ресурсы</h3><p>References и scripts не загружаются в prompt заранее.</p><ul className="skill-resources">{detail.resources.filter(item => item.path !== "SKILL.md").map(item => <li key={item.path}><button onClick={() => void openResource(item.path)}><FileIcon size={16} /><span>{item.path}</span><small>{item.size.toLocaleString()} Б</small></button></li>)}</ul>
            {resource ? <div className="resource-reader"><header><strong>{resource.path}</strong><button className="icon-button" aria-label="Закрыть ресурс" onClick={() => setResource(null)}><X size={16} /></button></header>{resource.truncated ? <p>Показаны первые 256 КБ.</p> : null}<pre>{resource.content}</pre></div> : null}</section>
          <section className="settings-card"><h3>Test prompt</h3><p>Показывает deterministic matching без вызова модели и без чтения полного навыка.</p><div className="skill-test"><textarea rows={3} placeholder={`Например: $${detail.slug} проверь проект`} value={testPrompt} onChange={event => setTestPrompt(event.target.value)} /><button className="text-button" onClick={() => void runTest()}>Проверить активацию</button></div>
            {match ? <div className="match-result"><strong>{match.selected.length ? `Активируются: ${match.selected.map(item => item.name).join(", ")}` : "Ни один навык не активируется"}</strong>{match.candidates.map(item => <span key={item.id}>{item.name}: {item.reason}, score {item.score.toFixed(1)}{item.matched_terms.length ? ` · ${item.matched_terms.join(", ")}` : ""}</span>)}</div> : null}</section>
        </>}
      </div>
    </div>
    {installOpen ? <SkillInstallDialog onClose={() => setInstallOpen(false)} onInstalled={async id => { setInstallOpen(false); await refresh(id); }} /> : null}
    {deleteOpen && detail ? <Dialog title="Удалить навык?" onClose={() => setDeleteOpen(false)}><h2>Удалить навык?</h2><p>«{detail.name}» переместится в корзину. Он перестанет активироваться, но файлы можно восстановить.</p><div className="dialog-actions"><button className="text-button" onClick={() => setDeleteOpen(false)}>Оставить</button><button className="danger-button" onClick={() => void remove()}>В корзину</button></div></Dialog> : null}
    {trash ? <Dialog title="Корзина навыков" onClose={() => setTrash(null)}><header className="dialog-toolbar"><h2>Корзина навыков</h2><button className="icon-button" aria-label="Закрыть корзину навыков" onClick={() => setTrash(null)}><X size={18} /></button></header>{trash.length ? <ul className="trash-list">{trash.map(item => <li key={item.id}><span>{item.name}</span><button className="text-button" onClick={() => void restore(item.id)}><ArrowCounterClockwise size={16} /> Восстановить</button></li>)}</ul> : <p>Удалённых навыков нет.</p>}</Dialog> : null}
  </section>;
}

function SkillInstallDialog({ onClose, onInstalled }: { onClose: () => void; onInstalled: (id: string) => void }) {
  const [kind, setKind] = useState<"zip" | "folder" | "git">("zip"); const [source, setSource] = useState(""); const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  async function install() {
    setBusy(true); setError("");
    try {
      const payload: Parameters<typeof api.installSkill>[0] = { source_type: kind, source, mode: "explicit" };
      if (kind === "zip") { if (!file) throw new Error("Выберите ZIP-файл"); payload.filename = file.name; payload.zip_base64 = bytesToBase64(await file.arrayBuffer()); }
      const installed = await api.installSkill(payload); await onInstalled(installed.id);
    } catch (cause) { setError(String((cause as Error).message)); } finally { setBusy(false); }
  }
  return <Dialog title="Установить навык" onClose={() => { if (!busy) onClose(); }}><header className="dialog-toolbar"><div><h2>Установить навык</h2><small>Импортируется в управляемую локальную папку Symphony</small></div><button className="icon-button" aria-label="Закрыть установку" onClick={onClose}><X size={18} /></button></header>
    <div className="install-kinds" role="radiogroup" aria-label="Источник навыка"><button role="radio" aria-checked={kind === "zip"} onClick={() => setKind("zip")}><UploadSimple size={17} /> ZIP</button><button role="radio" aria-checked={kind === "folder"} onClick={() => setKind("folder")}><FolderOpen size={17} /> Папка</button><button role="radio" aria-checked={kind === "git"} onClick={() => setKind("git")}><GitBranch size={17} /> Git URL</button></div>
    {kind === "zip" ? <label className="install-field"><span>ZIP-файл (до 10 МБ)</span><input type="file" accept=".zip,application/zip" onChange={event => setFile(event.target.files?.[0] ?? null)} /></label>
      : <label className="install-field"><span>{kind === "folder" ? "Полный путь к локальной папке" : "HTTPS Git URL (без submodules)"}</span><input value={source} onChange={event => setSource(event.target.value)} placeholder={kind === "folder" ? "C:\\Users\\…\\my-skill" : "https://github.com/owner/repo.git#path/to/skill"} /></label>}
    <p className="install-note">Установка не запускает scripts. Git обращается к указанному URL; scripts позже выполняются только offline в Docker после отдельного подтверждения.</p>{error ? <p className="tool-error" role="alert">{error}</p> : null}<div className="dialog-actions"><button className="text-button" disabled={busy} onClick={onClose}>Отмена</button><button className="settings-primary" disabled={busy} onClick={() => void install()}>{busy ? "Устанавливаем…" : "Установить"}</button></div></Dialog>;
}
