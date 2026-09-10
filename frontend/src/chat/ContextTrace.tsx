import { CaretRight, Files, Brain, ImageSquare } from "@phosphor-icons/react";
import type { TurnEvent } from "../types";

export function ContextTrace({ events }: { events: TurnEvent[] }) {
  const retrieval = events.find(event => event.type === "context.retrieved");
  const memory = [...events].reverse().find(event => event.type === "memory.snapshot");
  const built = events.find(event => event.type === "context.built");
  const vision = [...events].reverse().find(event => event.type === "vision.frame_selected" || event.type === "vision.attached");
  const chunks = Array.isArray(retrieval?.payload.chunks) ? retrieval.payload.chunks as Array<Record<string, unknown>> : [];
  const frames = Array.isArray(vision?.payload.frames) ? vision.payload.frames as Array<Record<string, unknown>> : [];
  const memoryVersion = Number(memory?.payload.version ?? built?.payload.memory_version ?? 0);
  if (!chunks.length && !memoryVersion && !frames.length) return null;
  const heading = frames.length ? <><ImageSquare size={15} /> Кадры: {frames.length}</> : chunks.length ? <><Files size={15} /> Источники: {chunks.length}</> : <><Brain size={15} /> Память v{memoryVersion}</>;
  const frameTokens = Number(vision?.payload.estimated_tokens ?? frames.reduce((total, frame) => total + Number(frame.estimated_tokens ?? 0), 0));
  return <details className="context-trace"><summary><span>{heading}</span><CaretRight className="disclosure-caret" size={13} /></summary>
    <div>{frames.length ? <><p><ImageSquare size={14} /> В контекст действительно отправлены эти кадры{frameTokens ? ` · около ${frameTokens} токенов` : ""}:</p><ul>{frames.map((frame, index) => <li key={String(frame.attachment_id ?? index)}><code>{String(frame.filename ?? "Кадр")}</code><span>{String(frame.source ?? "file")} · {String(frame.reason ?? "manual")} · {Number(frame.width ?? 0)}×{Number(frame.height ?? 0)} · ≈{Number(frame.estimated_tokens ?? 0)} токенов</span></li>)}</ul></> : null}{chunks.length ? <><p>В ответ переданы только найденные фрагменты:</p><ul>{chunks.map((chunk, index) => <li key={String(chunk.chunk_id ?? index)}><code>{String(chunk.path)}</code><span>фрагмент {Number(chunk.ordinal) + 1}</span></li>)}</ul></> : null}{memoryVersion ? <p><Brain size={14} /> Использована редактируемая память версии {memoryVersion}.</p> : null}<small>Содержимое источников считается данными, а не инструкциями.</small></div>
  </details>;
}
