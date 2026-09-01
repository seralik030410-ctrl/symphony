import {
  Broadcast,
  CheckCircle,
  Cpu,
  Database,
  Prohibit,
  WarningCircle,
  Wrench,
  ShieldWarning,
  ArrowSquareOut,
  X,
  Package,
  Brain,
  ImageSquare,
  Globe,
} from "@phosphor-icons/react";
import type { Icon } from "@phosphor-icons/react";

import type { TurnEvent } from "../types";

const labels: Record<string, string> = {
  "turn.started": "Turn начат",
  "turn.cancel_requested": "Остановка запрошена",
  "context.built": "Контекст собран",
  "context.indexed": "Файл проиндексирован",
  "context.retrieved": "Фрагменты найдены",
  "memory.snapshot": "Память обновлена",
  "memory.started": "Сжатие старой истории",
  "vision.attached": "Изображения переданы",
  "vision.ocr_completed": "OCR завершён",
  "research.needed": "Нужна актуальная проверка",
  "research.requested": "Сетевой запрос отправлен",
  "research.received": "Страница получена",
  "research.sources": "Источники сохранены",
  "model.started": "Модель вызвана",
  "model.delta": "Текст получен",
  "model.reasoning_delta": "Модель рассуждает",
  "model.usage": "Токены подсчитаны",
  "model.completed": "Модель завершила ответ",
  "model.failed": "Ошибка модели",
  "tool.requested": "Инструмент запрошен",
  "tool.started": "Инструмент запущен",
  "tool.output": "Результат инструмента",
  "tool.completed": "Инструмент завершён",
  "tool.failed": "Ошибка инструмента",
  "tool.cancelled": "Инструмент остановлен",
  "file.changed": "Файл изменён",
  "approval.requested": "Нужно разрешение",
  "approval.approved": "Действие разрешено",
  "approval.denied": "Действие запрещено",
  "approval.cancelled": "Разрешение отменено",
  "preview.ready": "Preview готов",
  "artifact.created": "Документ сохранён",
  "artifact.validated": "Документ проверен",
  "project.snapshot": "Снимок сохранён",
  "skill.cataloged": "Навыки сопоставлены",
  "skill.selected": "Навык выбран",
  "skill.read": "SKILL.md прочитан",
  "skill.resource_read": "Ресурс навыка прочитан",
  "skill.script_executed": "Script навыка выполнен",
  "turn.completed": "Turn завершён",
  "turn.failed": "Turn завершился ошибкой",
  "turn.cancelled": "Turn остановлен",
  "turn.interrupted": "Turn прерван перезапуском",
};

function EventIcon({ type }: { type: string }) {
  let Glyph: Icon = Broadcast;
  if (type === "context.built") Glyph = Database;
  if (type === "context.retrieved" || type === "context.indexed" || type === "memory.snapshot") Glyph = Brain;
  if (type.startsWith("vision.")) Glyph = ImageSquare;
  if (type.startsWith("research.")) Glyph = Globe;
  if (type.startsWith("model.")) Glyph = Cpu;
  if (type.startsWith("tool.") || type === "file.changed") Glyph = Wrench;
  if (type.startsWith("approval.")) Glyph = ShieldWarning;
  if (type.startsWith("skill.")) Glyph = Package;
  if (type === "preview.ready") Glyph = ArrowSquareOut;
  if (type === "turn.completed") Glyph = CheckCircle;
  if (type === "turn.cancelled" || type === "turn.cancel_requested") Glyph = Prohibit;
  if (type.endsWith("failed") || type === "turn.interrupted") Glyph = WarningCircle;
  return <Glyph size={16} weight="fill" aria-hidden="true" />;
}

function eventDetail(event: TurnEvent): string {
  if (event.type === "context.built") {
    return `${String(event.payload.message_count)} сообщений, около ${String(event.payload.estimated_tokens)} токенов`;
  }
  if (event.type === "context.retrieved") return `${Number(event.payload.chunks instanceof Array ? event.payload.chunks.length : 0)} фрагментов · ${Number(event.payload.characters ?? 0).toLocaleString("ru-RU")} знаков`;
  if (event.type === "context.indexed") return `${String(event.payload.path ?? "Файл")} · ${Number(event.payload.chunks ?? 0)} фрагментов`;
  if (event.type === "memory.snapshot") return `Версия ${Number(event.payload.version ?? 0)}`;
  if (event.type === "vision.attached") return `${Number(event.payload.count ?? 0)} изображений · ${String(event.payload.model ?? "модель")}`;
  if (event.type === "vision.ocr_completed") return `${String(event.payload.path ?? "Изображение")} · ${Number(event.payload.characters ?? 0)} знаков`;
  if (event.type === "research.requested") return String(event.payload.url ?? "Публичный HTTPS запрос");
  if (event.type === "research.received") return `${String(event.payload.url ?? "Страница")} · ${Number(event.payload.bytes ?? 0).toLocaleString("ru-RU")} байт`;
  if (event.type === "research.sources") return `${Array.isArray(event.payload.sources) ? event.payload.sources.length : 0} источников`;
  if (event.type === "model.started") {
    return `${String(event.payload.provider)} / ${String(event.payload.model)}`;
  }
  if (event.type === "model.completed") {
    const input = Number(event.payload.input_tokens ?? 0);
    const output = Number(event.payload.output_tokens ?? 0);
    return input || output
      ? `${input.toLocaleString("ru-RU")} → ${output.toLocaleString("ru-RU")} токенов`
      : `${String(event.payload.output_characters)} символов`;
  }
  if (event.type === "model.failed" || event.type === "turn.failed") {
    return String(event.payload.message ?? "Неизвестная ошибка");
  }
  if (event.type === "model.delta") {
    return `${String(event.payload.delta ?? "").length} символов`;
  }
  if (event.type === "model.reasoning_delta") {
    return `${String(event.payload.delta ?? "").length} знаков reasoning`;
  }
  if (event.type === "model.usage") {
    return `${Number(event.payload.input_tokens ?? 0).toLocaleString("ru-RU")} отправлено · ${Number(event.payload.output_tokens ?? 0).toLocaleString("ru-RU")} получено`;
  }
  if (event.type.startsWith("tool.")) {
    return String(event.payload.title ?? event.payload.name ?? event.payload.message ?? "Действие");
  }
  if (event.type === "file.changed") return String(event.payload.path ?? "Файл");
  if (event.type.startsWith("artifact.")) return `${String(event.payload.title ?? "Документ")} · v${Number(event.payload.version)}`;
  if (event.type.startsWith("approval.")) {
    return String(event.payload.reason ?? event.payload.title ?? event.payload.status ?? "Policy decision");
  }
  if (event.type === "preview.ready") return String(event.payload.path ?? event.payload.preview_url ?? "HTML");
  if (event.type === "skill.cataloged") return `${Array.isArray(event.payload.candidates) ? event.payload.candidates.length : 0} подходящих`;
  if (event.type === "skill.selected") return `${String(event.payload.name ?? event.payload.slug ?? "Навык")} · ${String(event.payload.reason ?? "выбран")}`;
  if (event.type === "skill.read") return `${String(event.payload.path ?? "SKILL.md")} · ${Number(event.payload.characters ?? 0).toLocaleString("ru-RU")} знаков`;
  if (event.type === "skill.resource_read") return String(event.payload.path ?? "Ресурс");
  if (event.type === "skill.script_executed") return `${String(event.payload.path ?? "Script")} · exit ${String(event.payload.exit_code ?? "—")}`;
  return new Date(event.created_at).toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

interface EventLedgerProps {
  events: TurnEvent[];
  onClose: () => void;
}

export function EventLedger({ events, onClose }: EventLedgerProps) {
  const visibleEvents = events
    .filter((event) => !["model.delta", "model.reasoning_delta", "tool.output_delta"].includes(event.type))
    .slice(-30)
    .reverse();
  return (
    <aside className="event-ledger" aria-label="Журнал событий">
      <header className="panel-heading">
        <div>
          <h2>События</h2>
          <p>Только сохранённые действия runtime</p>
        </div>
        <span className="event-count" aria-label={`${events.length} событий`}>
          {events.length}
        </span>
        <button className="icon-button" aria-label="Закрыть панель событий" onClick={onClose}><X size={18} /></button>
      </header>
      {visibleEvents.length ? (
        <ol className="event-list">
          {visibleEvents.map((event) => (
            <li className={`event-row event-${event.type.replaceAll(".", "-")}`} key={event.id}>
              <span className="event-icon">
                <EventIcon type={event.type} />
              </span>
              <div>
                <strong>{labels[event.type] ?? event.type}</strong>
                <span>{eventDetail(event)}</span>
              </div>
              <code>{event.sequence}</code>
            </li>
          ))}
        </ol>
      ) : (
        <div className="empty-events">
          <Broadcast size={22} weight="duotone" aria-hidden="true" />
          <p>События появятся после отправки сообщения.</p>
        </div>
      )}
    </aside>
  );
}
