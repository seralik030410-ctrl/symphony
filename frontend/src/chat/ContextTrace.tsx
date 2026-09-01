import { CaretRight, Files, Brain } from "@phosphor-icons/react";
import type { TurnEvent } from "../types";

export function ContextTrace({ events }: { events: TurnEvent[] }) {
  const retrieval = events.find(event => event.type === "context.retrieved");
  const memory = [...events].reverse().find(event => event.type === "memory.snapshot");
  const built = events.find(event => event.type === "context.built");
  const chunks = Array.isArray(retrieval?.payload.chunks) ? retrieval.payload.chunks as Array<Record<string, unknown>> : [];
  const memoryVersion = Number(memory?.payload.version ?? built?.payload.memory_version ?? 0);
  if (!chunks.length && !memoryVersion) return null;
  return <details className="context-trace"><summary><span>{chunks.length ? <Files size={15} /> : <Brain size={15} />} {chunks.length ? `Источники: ${chunks.length}` : `Память v${memoryVersion}`}</span><CaretRight className="disclosure-caret" size={13} /></summary>
    <div>{chunks.length ? <><p>В ответ переданы только найденные фрагменты:</p><ul>{chunks.map((chunk, index) => <li key={String(chunk.chunk_id ?? index)}><code>{String(chunk.path)}</code><span>фрагмент {Number(chunk.ordinal) + 1}</span></li>)}</ul></> : null}{memoryVersion ? <p><Brain size={14} /> Использована редактируемая память версии {memoryVersion}.</p> : null}<small>Содержимое источников считается данными, а не инструкциями.</small></div>
  </details>;
}
