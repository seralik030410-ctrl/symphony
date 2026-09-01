import {
  CheckCircle,
  CircleNotch,
  FileText,
  WarningCircle,
  Wrench,
  ShieldWarning,
  ArrowSquareOut,
} from "@phosphor-icons/react";

import type { TurnEvent } from "../types";

interface ToolCallView {
  id: string;
  name: string;
  title: string;
  status: "requested" | "running" | "completed" | "failed" | "cancelled";
  arguments?: unknown;
  output?: unknown;
  diff?: string;
  changedFiles: string[];
  duration?: number;
  error?: string;
  previewUrl?: string;
  snapshotId?: string;
  liveOutput?: string;
  approval?: {
    id?: string;
    status: "pending" | "approved" | "denied" | "cancelled";
    reason?: string;
    risk?: string;
  };
}

function callsFromEvents(events: TurnEvent[]): ToolCallView[] {
  const calls = new Map<string, ToolCallView>();
  for (const event of events) {
    if (
      !event.type.startsWith("tool.") &&
      !event.type.startsWith("approval.") &&
      event.type !== "file.changed" &&
      event.type !== "preview.ready" && event.type !== "project.snapshot"
    ) continue;
    const id = String(event.payload.tool_call_id ?? "");
    if (!id) continue;
    const call = calls.get(id) ?? {
      id,
      name: String(event.payload.name ?? "tool"),
      title: String(event.payload.title ?? event.payload.name ?? "Действие"),
      status: "requested" as const,
      changedFiles: [],
    };
    if (event.type === "tool.requested") {
      call.arguments = event.payload.arguments;
      call.name = String(event.payload.name ?? call.name);
      call.title = String(event.payload.title ?? call.title);
    } else if (event.type === "tool.started") {
      call.status = "running";
    } else if (event.type === "tool.output") {
      call.output = event.payload.output;
      call.diff = typeof event.payload.diff === "string" ? event.payload.diff : undefined;
      call.changedFiles = Array.isArray(event.payload.changed_files)
        ? event.payload.changed_files.map(String)
        : call.changedFiles;
      call.duration = Number(event.payload.duration_ms ?? 0);
    } else if (event.type === "tool.output_delta") {
      call.liveOutput = (call.liveOutput ?? "") + String(event.payload.delta ?? "");
    } else if (event.type === "tool.completed") {
      call.status = "completed";
      call.duration = Number(event.payload.duration_ms ?? call.duration ?? 0);
    } else if (event.type === "tool.failed") {
      call.status = "failed";
      call.error = String(event.payload.message ?? "Инструмент завершился ошибкой");
      call.duration = Number(event.payload.duration_ms ?? 0);
      call.output = event.payload.details;
    } else if (event.type === "project.snapshot") {
      call.snapshotId = String(event.payload.id ?? "");
    } else if (event.type === "tool.cancelled") {
      call.status = "cancelled";
      call.error = "Действие остановлено";
    } else if (event.type === "file.changed") {
      const path = String(event.payload.path ?? "");
      if (path && !call.changedFiles.includes(path)) call.changedFiles.push(path);
    } else if (event.type === "approval.requested") {
      call.approval = {
        id: String(event.payload.approval_id ?? ""),
        status: "pending",
        reason: String(event.payload.reason ?? "Требуется подтверждение"),
        risk: String(event.payload.risk_level ?? "medium"),
      };
    } else if (event.type === "approval.approved") {
      call.approval = { ...call.approval, status: "approved" };
    } else if (event.type === "approval.denied") {
      call.approval = {
        ...call.approval,
        status: "denied",
        reason: String(event.payload.reason ?? call.approval?.reason ?? "Действие отклонено"),
      };
    } else if (event.type === "approval.cancelled") {
      call.approval = { ...call.approval, status: "cancelled" };
    } else if (event.type === "preview.ready") {
      call.previewUrl = String(event.payload.preview_url ?? "");
    }
    calls.set(id, call);
  }
  return [...calls.values()];
}

function statusLabel(status: ToolCallView["status"]): string {
  if (status === "completed") return "Готово";
  if (status === "failed") return "Ошибка";
  if (status === "cancelled") return "Остановлено";
  if (status === "running") return "Выполняется";
  return "Запрошено";
}

function Payload({ value }: { value: unknown }) {
  return <pre>{JSON.stringify(value, null, 2)}</pre>;
}

interface ToolActivityProps {
  events: TurnEvent[];
  decidingApprovalId: string | null;
  onApproval: (approvalId: string, approved: boolean) => void;
  onPreview: (url: string) => void;
  onFile: (path: string) => void;
  onChanges: () => void;
}

export function ToolActivity({ events, decidingApprovalId, onApproval, onPreview, onFile, onChanges }: ToolActivityProps) {
  const calls = callsFromEvents(events);
  if (!calls.length) return null;
  return (
    <section className="tool-activity" aria-label="Действия с файлами">
      {calls.map((call) => {
        const StateIcon =
          call.status === "completed"
            ? CheckCircle
            : call.status === "failed" || call.status === "cancelled"
              ? WarningCircle
              : CircleNotch;
        return (
          <details
            className={`tool-card tool-${call.status}`}
            key={call.id}
            open={call.approval?.status === "pending" || undefined}
          >
            <summary>
              <span className="tool-glyph"><Wrench size={15} weight="bold" /></span>
              <span className="tool-title">
                <strong>{call.title}</strong>
                <code>{call.name}</code>
              </span>
              <span className="tool-status">
                <StateIcon size={15} weight="fill" />
                {statusLabel(call.status)}
                {call.duration !== undefined ? ` · ${call.duration} мс` : ""}
              </span>
            </summary>
            <div className="tool-details">
              {call.approval ? (
                <div className={`approval-panel approval-${call.approval.status}`}>
                  <ShieldWarning size={18} weight="fill" aria-hidden="true" />
                  <div>
                    <strong>
                      {call.approval.status === "pending"
                        ? "Нужно ваше разрешение"
                        : call.approval.status === "approved"
                          ? "Разрешено"
                          : "Не разрешено"}
                    </strong>
                    <p>{call.approval.reason}</p>
                    {call.approval.status === "pending" && call.approval.id ? (
                      <span className="approval-actions">
                        <button
                          type="button"
                          disabled={decidingApprovalId === call.approval.id}
                          onClick={() => onApproval(call.approval!.id!, false)}
                        >
                          Запретить
                        </button>
                        <button
                          className="approval-allow"
                          type="button"
                          disabled={decidingApprovalId === call.approval.id}
                          onClick={() => onApproval(call.approval!.id!, true)}
                        >
                          Разрешить один раз
                        </button>
                      </span>
                    ) : null}
                  </div>
                </div>
              ) : null}
              {call.error ? <p className="tool-error">{call.error}</p> : null}
              {call.liveOutput ? <details><summary>Вывод команды</summary><pre>{call.liveOutput}</pre></details> : null}
              {call.snapshotId ? (
                <details><summary>Снимок до изменения</summary>
                  <p>Для отката попросите восстановить снимок <code>{call.snapshotId}</code>. Потребуется подтверждение.</p>
                </details>
              ) : null}
              {call.previewUrl ? (
                <button type="button" className="preview-link" onClick={() => onPreview(call.previewUrl!)}>
                  <ArrowSquareOut size={16} weight="bold" aria-hidden="true" />
                  Открыть в Symphony
                </button>
              ) : null}
              {call.changedFiles.length ? (
                <div className="changed-files">
                  <h4>Изменённые файлы</h4>
                  {call.changedFiles.map((path) => (
                    <button type="button" className="text-button" key={path} onClick={() => onFile(path)}><FileText size={14} />{path}</button>
                  ))}
                  <button type="button" className="text-button" onClick={onChanges}>Сравнить изменения</button>
                </div>
              ) : null}
              {call.arguments !== undefined ? (
                <details><summary>Аргументы</summary><Payload value={call.arguments} /></details>
              ) : null}
              {call.output !== undefined ? (
                <details><summary>Результат</summary><Payload value={call.output} /></details>
              ) : null}
              {call.diff ? (
                <details><summary>Diff</summary><pre className="tool-diff">{call.diff}</pre></details>
              ) : null}
            </div>
          </details>
        );
      })}
    </section>
  );
}
