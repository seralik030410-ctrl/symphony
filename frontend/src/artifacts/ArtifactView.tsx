import { useEffect, useState } from "react";
import { DownloadSimple, FileText, CheckCircle } from "@phosphor-icons/react";
import { api, type ArtifactDetail, type ArtifactSummary } from "../api";
import { CustomSelect } from "../ui/CustomSelect";
import type { TurnEvent } from "../types";

export function artifactEvents(events: TurnEvent[]) {
  return events.filter(event => event.type === "artifact.created" && typeof event.payload.id === "string" && /^[a-f0-9]{32}$/.test(event.payload.id));
}

export function ArtifactCards({ events, onOpen }: { events: TurnEvent[]; onOpen: (id: string) => void }) {
  return <div className="artifact-cards">{artifactEvents(events).map(event => <button key={event.id} className="artifact-card" onClick={() => onOpen(String(event.payload.id))}>
    <FileText size={24} weight="duotone" aria-hidden="true" /><span><strong>{String(event.payload.title)}</strong><small>{String(event.payload.format).toUpperCase()} · Версия {Number(event.payload.version)} · Открыть документ</small></span>
  </button>)}</div>;
}

export function ArtifactView({ sessionId, artifactId, revision }: { sessionId: string; artifactId: string; revision: number }) {
  const [detail, setDetail] = useState<ArtifactDetail | null>(null);
  const [versions, setVersions] = useState<ArtifactSummary[]>([]);
  const [version, setVersion] = useState("");
  const [sheet, setSheet] = useState("0");
  const [error, setError] = useState("");
  useEffect(() => {
    let stale = false; setDetail(null); setError("");
    Promise.all([api.getArtifact(sessionId, artifactId, version ? Number(version) : undefined), api.listArtifacts(sessionId)])
      .then(([next, all]) => { if (!stale) { setDetail(next); setVersions(all.filter(item => item.id === artifactId)); } })
      .catch(cause => { if (!stale) setError(cause.message); });
    return () => { stale = true; };
  }, [sessionId, artifactId, revision, version]);
  if (error) return <p className="workspace-notice" role="alert">{error}</p>;
  if (!detail) return <p className="workspace-notice" role="status">Открываем документ…</p>;
  const table = detail.tables[Number(sheet)] ?? detail.tables[0];
  return <div className="artifact-view">
    <header className="artifact-toolbar"><div><h2>{detail.title}</h2><span>{detail.format.toUpperCase()} · {(detail.size / 1024).toFixed(1)} КБ</span></div>
      <a className="artifact-download" href={detail.download_url} download><DownloadSimple size={17} />Скачать</a>
    </header>
    <div className="artifact-controls"><CustomSelect ariaLabel="Версия документа" value={version} onChange={setVersion} options={[{ value: "", label: `Последняя · v${versions[0]?.version ?? detail.version}` }, ...versions.map(item => ({ value: String(item.version), label: `Версия ${item.version}`, description: new Date(item.created_at).toLocaleString() }))]} />
      {detail.tables.length ? <CustomSelect ariaLabel="Лист таблицы" value={sheet} onChange={setSheet} options={detail.tables.map((item, i) => ({ value: String(i), label: item.name }))} /> : <span>{detail.pages.length} стр.</span>}
    </div>
    <div className="artifact-scroll" tabIndex={0} aria-label="Просмотр документа" onKeyDown={event => {
      if (event.target !== event.currentTarget) return;
      const viewport = event.currentTarget;
      const positions: Record<string, number> = { Home: 0, End: viewport.scrollHeight, PageDown: viewport.scrollTop + viewport.clientHeight * .85, PageUp: viewport.scrollTop - viewport.clientHeight * .85, ArrowDown: viewport.scrollTop + 48, ArrowUp: viewport.scrollTop - 48 };
      if (event.key in positions) { event.preventDefault(); viewport.scrollTop = positions[event.key]; }
    }}>
      {table ? <><div className="artifact-table-scroll" tabIndex={0} aria-label={`Таблица ${table.name}`}><table className="artifact-table"><thead><tr><th scope="col">#</th>{table.columns.map((col, i) => <th key={i} scope="col">{col.name}</th>)}</tr></thead><tbody>{table.rows.map((row, r) => <tr key={r}><th scope="row">{r + 2}</th>{row.map((value, c) => <td key={c}>{value === null ? "—" : String(value)}</td>)}</tr>)}</tbody></table></div>
        <p className="workspace-footnote">{table.truncated ? `Первые ${table.rows.length} из ${table.total_rows} строк. Полная таблица — в файле.` : `${table.total_rows} строк.`} Значения формул рассчитаны Symphony; Excel пересчитает их при открытии.</p></> : null}
      {detail.pages.map((page, index) => <figure className="artifact-page" key={page.url}><img src={page.url} width={page.width} height={page.height} loading={index ? "lazy" : "eager"} alt={`${detail.title}, страница ${index + 1}`} /><figcaption>{index + 1} / {detail.pages.length}</figcaption></figure>)}
      <details className="artifact-validation"><summary><CheckCircle size={16} />Проверки и исходники</summary>
        <p>Схема и выходной файл проверены. {detail.validation.geometry?.checked ? "Проверены границы текста на страницах." : "Проверены типы, формулы и ссылки."}</p>
        {detail.validation.calculation ? <p>Рассчитано формул: {detail.validation.calculation.formula_count}.</p> : null}
        <p>Автопроверки не заменяют просмотр содержания и оформления.</p>
        <nav aria-label="Исходники документа"><a href={detail.source_url} download>JSON-исходник</a><a href={detail.recipe_url} download>Рецепт</a><a href={detail.validation_url} download>Отчёт проверки</a></nav>
        <small>{detail.validation.renderer} · Версия {detail.version}</small>
      </details>
    </div>
  </div>;
}
