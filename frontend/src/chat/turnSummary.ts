import type { Turn, TurnEvent } from "../types";

function count(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}

export function formatTokens(value: number): string {
  return new Intl.NumberFormat("ru-RU").format(value);
}

export function summarizeTurn(turn: Turn, events: TurnEvent[]) {
  let reasoning = "";
  let inputTokens = 0;
  let outputTokens = 0;
  let reasoningTokens: number | null = null;
  let contextUsed: number | null = null;
  let contextWindow = 0;
  let estimated = true;
  let hasUsage = false;
  let modelSteps = 0;
  let stage = "Подготовка…";
  for (const event of events) {
    switch (event.type) {
      case "skill.cataloged": stage = "Выбирает навык…"; break;
      case "skill.selected": stage = "Подключает навык…"; break;
      case "skill.read": stage = "Читает инструкции навыка…"; break;
      case "skill.resource_read": stage = "Изучает ресурс навыка…"; break;
      case "skill.script_executed": stage = "Проверяет результат script…"; break;
      case "context.built":
        contextUsed = count(event.payload.estimated_tokens);
        contextWindow = count(event.payload.context_window) ?? contextWindow;
        break;
      case "context.retrieved": stage = "Ищет в источниках…"; break;
      case "memory.started": stage = "Сжимает старую историю…"; break;
      case "memory.snapshot":
        stage = "Память обновлена";
        inputTokens += count(event.payload.input_tokens) ?? 0;
        outputTokens += count(event.payload.output_tokens) ?? 0;
        break;
      case "vision.attached": stage = "Передаёт изображения модели…"; break;
      case "vision.ocr_completed": stage = "Распознаёт текст…"; break;
      case "research.needed": stage = "Готовит исследование…"; break;
      case "research.requested": stage = "Читает интернет…"; break;
      case "research.received": stage = "Проверяет источник…"; break;
      case "research.sources": stage = "Источники сохранены"; break;
      case "model.started": modelSteps++; stage = "Ожидание модели…"; break;
      case "model.reasoning_delta":
        reasoning += String(event.payload.delta ?? "");
        stage = "Думает…";
        break;
      case "model.delta": stage = "Пишет ответ…"; break;
      case "tool.requested": stage = "Подготовка действия…"; break;
      case "tool.started": stage = event.payload.name === "artifact.render" ? "Создаёт и проверяет документ…" : "Выполняет действие…"; break;
      case "approval.requested": stage = "Нужно разрешение"; break;
      case "approval.approved": stage = "Выполняет действие…"; break;
      case "approval.denied":
      case "tool.completed":
      case "tool.failed": stage = "Продолжает работу…"; break;
      case "model.usage": {
        hasUsage = true;
        inputTokens += count(event.payload.input_tokens) ?? 0;
        outputTokens += count(event.payload.output_tokens) ?? 0;
        const reasoningCount = count(event.payload.reasoning_tokens);
        if (reasoningCount !== null) reasoningTokens = (reasoningTokens ?? 0) + reasoningCount;
        const input = count(event.payload.input_tokens);
        if (input !== null) { contextUsed = input; estimated = false; }
        contextWindow = count(event.payload.context_window) ?? contextWindow;
        break;
      }
    }
  }
  const active = ["queued", "preparing", "model_running"].includes(turn.status);
  return { active, stage, reasoning, inputTokens, outputTokens, reasoningTokens,
    contextUsed, contextWindow, estimated, hasUsage, modelSteps };
}
