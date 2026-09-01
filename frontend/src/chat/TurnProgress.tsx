import { CaretRight, CircleNotch } from "@phosphor-icons/react";
import { useMemo, useState } from "react";

import type { Turn, TurnEvent } from "../types";
import { summarizeTurn, formatTokens } from "./turnSummary";

interface TurnProgressProps {
  turn: Turn;
  events: TurnEvent[];
}

/** Streaming never overrides the reader's disclosure choice. */
export function TurnProgress({ turn, events }: TurnProgressProps) {
  const summary = useMemo(() => summarizeTurn(turn, events), [turn, events]);
  const [open, setOpen] = useState(false);
  if (!summary.reasoning && !summary.active) return null;
  const label = summary.active ? summary.stage : "Рассуждение";
  return (
    <div className="turn-progress" aria-label="Ход выполнения ответа">
      {summary.reasoning ? (
        <>
          <button type="button" className="reasoning-toggle" aria-expanded={open}
            aria-controls={`reasoning-${turn.id}`} onClick={() => setOpen(value => !value)}>
            {summary.active ? <CircleNotch className="turn-spinner" size={14} aria-hidden="true" /> : null}
            <span>{label}</span>
            <CaretRight className="disclosure-caret" size={13} aria-hidden="true" />
          </button>
          {open ? (
            <div className="reasoning-content" id={`reasoning-${turn.id}`}>
              <p className="reasoning-source">Текст рассуждения, переданный моделью</p>
              <div>{summary.reasoning}</div>
            </div>
          ) : null}
        </>
      ) : (
        <div className="turn-status" role="status">
          <CircleNotch className="turn-spinner" size={14} aria-hidden="true" />
          <span>{summary.stage}</span>
        </div>
      )}
    </div>
  );
}

/** Usage stays secondary to the answer, with details in normal document flow. */
export function TurnUsage({ turn, events }: TurnProgressProps) {
  const summary = useMemo(() => summarizeTurn(turn, events), [turn, events]);
  if (!summary.contextWindow && !summary.hasUsage) return null;
  return (
    <details className="turn-usage">
      <summary>
        <span>{summary.hasUsage
          ? `${formatTokens(summary.inputTokens)} ↑ · ${formatTokens(summary.outputTokens)} ↓ токенов`
          : "Контекст и токены"}</span>
        <CaretRight className="disclosure-caret" size={12} aria-hidden="true" />
      </summary>
      <dl>
        <div><dt>Отправлено за ответ</dt><dd>{summary.hasUsage ? formatTokens(summary.inputTokens) : "Нет данных от модели"}</dd></div>
        <div><dt>Получено за ответ</dt><dd>{summary.hasUsage ? formatTokens(summary.outputTokens) : "Нет данных от модели"}</dd></div>
        {summary.reasoningTokens !== null ? <div><dt>Из них — рассуждение</dt><dd>{formatTokens(summary.reasoningTokens)}</dd></div> : null}
        <div><dt>Контекст последнего вызова</dt><dd>{summary.contextUsed !== null ? `${summary.estimated ? "≈ " : ""}${formatTokens(summary.contextUsed)}` : "Нет данных"}</dd></div>
        <div><dt>Контекстное окно</dt><dd>{summary.contextWindow ? formatTokens(summary.contextWindow) : "Неизвестно"}</dd></div>
        <div><dt>Вызовы модели</dt><dd>{summary.modelSteps}</dd></div>
      </dl>
      <p>{summary.hasUsage ? "Токены по данным провайдера; сумма всех вызовов в этом ответе." : "Оценка контекста приблизительная. Точные токены появятся, если модель их передаст."}</p>
    </details>
  );
}
