import { BookOpenText, CaretDown, CheckCircle, Package, TerminalWindow } from "@phosphor-icons/react";
import type { TurnEvent } from "../types";

export function SkillTrace({ events }: { events: TurnEvent[] }) {
  const selected = events.filter(event => event.type === "skill.selected");
  if (!selected.length) return null;
  const reads = events.filter(event => event.type === "skill.read");
  const resources = events.filter(event => event.type === "skill.resource_read");
  const scripts = events.filter(event => event.type === "skill.script_executed");
  const names = selected.map(event => String(event.payload.name ?? event.payload.slug ?? "Навык")).join(", ");
  return <details className="skill-trace">
    <summary><Package size={16} weight="fill" /><span>Использован навык: {names}</span><CaretDown size={14} className="skill-trace-caret" /></summary>
    <div className="skill-trace-body">
      {selected.map(event => <div key={event.id}><CheckCircle size={15} /><span><strong>Выбран</strong><small>{String(event.payload.reason ?? "по запросу")}</small></span></div>)}
      {reads.map(event => <div key={event.id}><BookOpenText size={15} /><span><strong>Прочитан {String(event.payload.path ?? "SKILL.md")}</strong><small>{Number(event.payload.characters ?? 0).toLocaleString("ru-RU")} знаков · {String(event.payload.sha256 ?? "").slice(0, 9)}</small></span></div>)}
      {resources.map(event => <div key={event.id}><BookOpenText size={15} /><span><strong>Прочитан ресурс</strong><small>{String(event.payload.path ?? "resource")}</small></span></div>)}
      {scripts.map(event => <div key={event.id}><TerminalWindow size={15} /><span><strong>Script выполнен</strong><small>{String(event.payload.path ?? "script")} · exit {String(event.payload.exit_code ?? "—")}</small></span></div>)}
    </div>
  </details>;
}
