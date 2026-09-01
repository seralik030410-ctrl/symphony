import { ArrowClockwise, FileText, WarningCircle } from "@phosphor-icons/react";

import type { Message, Turn, TurnEvent } from "../types";
import { MarkdownMessage } from "./MarkdownMessage";
import { ToolActivity } from "./ToolActivity";
import { TurnProgress, TurnUsage } from "./TurnProgress";
import { SkillTrace } from "./SkillTrace";
import { ArtifactCards } from "../artifacts/ArtifactView";
import { ContextTrace } from "./ContextTrace";
import { ResearchTrace } from "./ResearchTrace";

interface MessageListProps {
  messages: Message[];
  turns: Turn[];
  events: TurnEvent[];
  retryingTurnId: string | null;
  onRetry: (turnId: string) => void;
  decidingApprovalId: string | null;
  onApproval: (approvalId: string, approved: boolean) => void;
  onPreview: (url: string) => void;
  onFile: (path: string) => void;
  onChanges: () => void;
  onArtifact: (id: string) => void;
}

function statusText(message: Message): string | null {
  if (message.status === "cancelled") return "Ответ остановлен";
  if (message.status === "failed") return "Ответ завершился ошибкой";
  return null;
}

export function MessageList({
  messages,
  turns,
  events,
  retryingTurnId,
  onRetry,
  decidingApprovalId,
  onApproval,
  onPreview,
  onFile,
  onChanges,
  onArtifact,
}: MessageListProps) {
  if (messages.length === 0) {
    return (
      <section className="empty-conversation" aria-labelledby="empty-title">
        <div className="empty-mark" aria-hidden="true">
          S2
        </div>
        <h1 id="empty-title">Начните разговор</h1>
        <p>
          Обычный запрос отправляется напрямую выбранной модели. Для файловых задач Symphony
          показывает файловые действия и команды sandbox. Навык подключается только явно или по
          совпадению с запросом; document router в обычном чате не участвует.
        </p>
      </section>
    );
  }

  return (
    <div className="message-list" aria-live="polite">
      {messages.map((message) => {
        const turn = message.turn_id ? turns.find((item) => item.id === message.turn_id) : undefined;
        const turnEvents = events.filter((event) => event.turn_id === message.turn_id);
        const label = statusText(message);
        return (
          <article className={`message message-${message.role}`} key={message.id}>
            <div className="message-label">
              {message.role === "user" ? "Вы" : "Symphony"}
            </div>
            {message.role === "assistant" && turn ? <TurnProgress turn={turn} events={turnEvents} /> : null}
            {message.content ? (
              <MarkdownMessage content={message.content} />
            ) : message.status === "streaming" && !turn ? (
              <div className="response-skeleton" aria-label="Модель готовит ответ">
                <span />
                <span />
                <span />
              </div>
            ) : null}
            {message.role === "user" && message.attachments?.length ? <div className="message-attachments">
              {message.attachments.map(item => item.mime_type.startsWith("image/")
                ? <figure key={item.id}><img src={`/api/sessions/${message.session_id}/inputs/${item.id}`} alt={item.filename} /><figcaption>{item.filename}</figcaption></figure>
                : <a key={item.id} href={`/api/sessions/${message.session_id}/inputs/${item.id}`}><FileText size={17} /><span>{item.filename}</span></a>)}
            </div> : null}
            {message.role === "assistant" && message.turn_id ? (
              <>
                <SkillTrace events={turnEvents} />
                <ContextTrace events={turnEvents} />
                <ResearchTrace events={turnEvents} />
                <ArtifactCards events={turnEvents} onOpen={onArtifact} />
                <ToolActivity
                  events={turnEvents}
                  decidingApprovalId={decidingApprovalId}
                  onApproval={onApproval}
                  onPreview={onPreview}
                  onFile={onFile}
                  onChanges={onChanges}
                />
                {turn ? <TurnUsage turn={turn} events={turnEvents} /> : null}
              </>
            ) : null}
            {label ? (
              <div className="message-state">
                <WarningCircle size={16} weight="fill" aria-hidden="true" />
                <span>{label}{turn?.error ? `: ${turn.error}` : null}</span>
                {turn ? (
                  <button type="button" disabled={retryingTurnId === turn.id} onClick={() => onRetry(turn.id)}>
                    <ArrowClockwise size={14} weight="bold" />
                    {retryingTurnId === turn.id ? "Повторяем" : "Повторить"}
                  </button>
                ) : null}
              </div>
            ) : null}
          </article>
        );
      })}
    </div>
  );
}
