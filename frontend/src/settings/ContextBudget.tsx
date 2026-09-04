import { useEffect, useState } from "react";
import { api } from "../api";
import type { Session } from "../types";
import { CustomSelect } from "../ui/CustomSelect";
import { contextOptions, validContextBudget } from "./contextLimits";

export function ContextBudget({ session, active, onSaved }: {
  session: Session; active: boolean; onSaved: (session: Session) => void;
}) {
  const [windowSize, setWindowSize] = useState(session.context_window);
  const [output, setOutput] = useState(String(session.max_output));
  const [maximum, setMaximum] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setMaximum(null);
    setError(""); setNotice("");
    api.getModelLimits(session.id).then(value => { if (!cancelled) setMaximum(value.max_context); })
      .catch(cause => { if (!cancelled) setError(cause instanceof Error ? cause.message : "Не удалось проверить лимит модели"); });
    return () => { cancelled = true; };
  }, [session.id, session.provider, session.model, retry]);
  useEffect(() => {
    setWindowSize(session.context_window); setOutput(String(session.max_output));
  }, [session.context_window, session.max_output, session.id]);
  const values = contextOptions(session.context_window, maximum);
  const outputCount = Number(output);
  const validOutput = Number.isInteger(outputCount) && outputCount >= 64 && outputCount < windowSize;
  const validBudget = validContextBudget(windowSize, output, maximum);
  const dirty = windowSize !== session.context_window || outputCount !== session.max_output;
  async function save() {
    if (!dirty || !validBudget || saving || active) return;
    setSaving(true); setError(""); setNotice("");
    try {
      const updated = await api.updateSession(session.id, { context_window: windowSize, max_output: outputCount });
      onSaved(updated); setNotice("Сохранено для следующих сообщений этого чата");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Лимиты не сохранены"); }
    finally { setSaving(false); }
  }
  return <section className="context-budget" aria-labelledby="context-budget-heading">
    <h2 id="context-budget-heading">Лимиты модели</h2>
    <div className="settings-card">
      <div className="settings-row"><div><strong>Длина контекста</strong><small>Общий бюджет истории, памяти, источников, инструментов и ответа. Сохраняется отдельно для этого чата.</small></div>
        <CustomSelect ariaLabel="Длина контекста" value={String(windowSize)} disabled={active || saving || maximum === null} onChange={value => { setWindowSize(Number(value)); setNotice(""); }} options={values.map(value => ({ value: String(value), label: `${value / 1024}K · ${value.toLocaleString("ru-RU")} токенов`, description: value <= 8192 ? "Компактное окно" : value === 16384 ? "Быстрый стандарт" : value === 32768 ? "Больше истории и источников" : value === 65536 ? "Длинные задачи" : value === 131072 ? "Современный стандарт API" : value <= 524288 ? "Для очень длинных проектов" : "Максимальный контекст", unavailable: maximum !== null && value > maximum }))} />
      </div>
      <div className="settings-row"><div><label htmlFor="context-output-limit"><strong>Максимальная длина ответа</strong></label><small>Резерв внутри выбранного окна; провайдер может завершить ответ раньше.</small></div>
        <input id="context-output-limit" type="number" min={64} max={windowSize - 1} step={1} value={output} disabled={active || saving} aria-invalid={!validOutput} onChange={event => { setOutput(event.target.value); setNotice(""); }} />
      </div>
      <div className="context-budget-footer">
        <p>{maximum === null ? error ? "Не удалось получить предел модели." : "Проверяем лимит модели…" : `Предел для ${session.model}: ${maximum.toLocaleString("ru-RU")} токенов. 16K — стандарт, 32K — для длинных задач.`}</p>
        <details><summary>Как применяются лимиты</summary><p>{session.provider === "ollama" ? "Ollama получает длину контекста в num_ctx и лимит ответа в num_predict." : "Окно ограничивает сборку запроса в Symphony, а лимит ответа передаётся как max_tokens. Окно самого API-сервера задаёт провайдер; если максимум неизвестен, Symphony использует 16K."}</p></details>
        {windowSize >= 65536 ? <p>{windowSize >= 262144 ? "256K+ значительно увеличивает расход памяти. Убедитесь, что модель реально поддерживает такое окно." : "64K+ потребует больше RAM/VRAM и времени на обработку истории."}</p> : null}
        {active ? <p>Остановите текущий ответ, чтобы изменить лимиты.</p> : null}
        {error ? <p role="alert">{error}{maximum === null ? <button className="text-button" onClick={() => setRetry(value => value + 1)}>Повторить проверку</button> : null}</p> : null}
        {!validOutput ? <p role="alert">Лимит ответа — целое число от 64 и меньше окна контекста.</p> : null}
        {notice ? <p role="status">{notice}</p> : null}
        <button className="settings-primary" disabled={!dirty || !validBudget || active || saving} onClick={() => void save()}>{saving ? "Сохраняем…" : "Сохранить лимиты"}</button>
      </div>
    </div>
  </section>;
}
