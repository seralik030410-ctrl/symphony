import { ArrowSquareOut, CaretRight, Globe } from "@phosphor-icons/react";
import type { ResearchSource, TurnEvent } from "../types";
import { hasDesktopBridge, openExternal } from "../desktop";
import { useState } from "react";

function date(value: string | null) {
  if (!value) return "дата публикации не указана";
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? "дата публикации не указана" : `опубликовано ${parsed.toLocaleDateString("ru-RU")}`;
}

function host(value: string) {
  try { return new URL(value).hostname; }
  catch { return "Источник"; }
}

function checkedAt(value: string) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? "время проверки не указано" : `проверено ${parsed.toLocaleString("ru-RU")}`;
}

export function ResearchTrace({ events }: { events: TurnEvent[] }) {
  const [error, setError] = useState("");
  const sources = events.flatMap(event => event.type === "research.sources" && Array.isArray(event.payload.sources) ? event.payload.sources as unknown as ResearchSource[] : []);
  if (!sources.length) return null;
  return <details className="research-trace"><summary><span><Globe size={15} /> Веб-источники: {sources.length}</span><CaretRight className="disclosure-caret" size={13} /></summary><div>
    <p>Сетевые обращения сохранены в журнале. Содержимое страниц считается недоверенными данными.</p>
    <ol>{sources.map(source => <li key={source.id}><a href={source.url.startsWith("https://") ? source.url : undefined} target="_blank" rel="noreferrer" onClick={event => { if (hasDesktopBridge()) { event.preventDefault(); setError(""); void openExternal(source.url).catch(cause => setError(cause instanceof Error ? cause.message : "Не удалось открыть источник")); } }}><span>{source.title || host(source.url)}</span><ArrowSquareOut size={14} /></a><small>{source.kind === "search_result" ? "Только результат поиска; страница не прочитана" : `${date(source.published_at)} · ${checkedAt(source.checked_at)}`}</small></li>)}</ol>
    {error ? <p role="alert">{error}</p> : null}
  </div></details>;
}
