import { ArrowBendUpRight, CaretRight, CheckCircle, CircleNotch, Pulse, Stop, TreeStructure, WarningCircle } from "@phosphor-icons/react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { AgentCompletionReceipt, AgentHeartbeatEvent, AgentHeartbeatWatch, AgentTask } from "../types";
import "./agents.css";

const terminal = new Set(["completed", "failed", "cancelled", "interrupted"]);
const receiptLabel: Record<AgentCompletionReceipt["status"], string> = {
  completed: "завершена", failed: "завершилась с ошибкой", cancelled: "остановлена", interrupted: "прервана",
};
const heartbeatLabel: Record<AgentHeartbeatEvent["type"], string> = {
  stalled: "давно не сообщает об активности",
  resumed: "снова сообщает об активности",
  completed: "завершена",
  failed: "завершилась с ошибкой",
  cancelled: "остановлена",
  interrupted: "прервана",
};

const phaseLabel: Record<string, string> = {
  queued: "в очереди", starting: "запускается", waiting_for_resources: "ожидает ресурсы",
  model: "работает модель", tool: "выполняет инструмент", finished: "завершён",
};
const roleLabel: Record<AgentTask["role"], string> = {
  worker: "исполнитель", orchestrator: "оркестратор", code: "код", research: "поиск",
  vision: "зрение", media: "медиа", review: "проверка",
};

function activityText(task: AgentTask) {
  const phase = phaseLabel[task.activity_phase] ?? task.activity_phase;
  if (!task.last_activity_at) return phase;
  const seconds = Math.max(0, Math.round((Date.now() - new Date(task.last_activity_at).getTime()) / 1000));
  return `${phase} · активность ${seconds < 60 ? `${seconds} сек.` : `${Math.floor(seconds / 60)} мин.`} назад`;
}

function TaskNode({ task, children, refresh }: { task: AgentTask; children: Map<string | null, AgentTask[]>; refresh: () => Promise<void> }) {
  const [open, setOpen] = useState(task.status !== "completed");
  const [steering, setSteering] = useState(false);
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const descendants = children.get(task.id) ?? [];
  const active = !terminal.has(task.status);
  const icon = task.status === "completed" ? <CheckCircle weight="fill" />
    : task.status === "failed" ? <WarningCircle weight="fill" />
      : terminal.has(task.status) ? <Stop weight="fill" /> : <CircleNotch className="agent-spinner" />;
  return <li><div className={`agent-task agent-${task.status}`}>
    <button className="agent-disclosure" onClick={() => setOpen(value => !value)} aria-expanded={open}>
      <CaretRight className="agent-caret" size={13} /><span className="agent-state-icon">{icon}</span>
      <span><strong>{task.goal}</strong><small>{roleLabel[task.role]} · {task.execution_mode === "background" ? "фон · " : ""}{task.model} · {activityText(task)}</small></span>
    </button>
    {active ? <button className="agent-cancel" title="Остановить этого субагента" aria-label={`Остановить только субагента: ${task.goal}`}
      disabled={pending} onClick={async () => { setPending(true); setError(null); try { await api.commandAgentTask(task.id, { type: "stop", subtree: false }); await refresh(); } catch (value) { setError(String(value)); } finally { setPending(false); } }}><Stop size={13} weight="fill" /></button> : null}
  </div>
  {open && task.stalled_at ? <p className="agent-stalled" role="status"><WarningCircle size={15} /> Давно нет активности. Задача не остановлена.</p> : null}
  {open && active ? <div className="agent-controls">
    <button className="text-button" onClick={() => setSteering(value => !value)} aria-expanded={steering}><ArrowBendUpRight size={15} /> Направить</button>
    {descendants.length ? <button className="text-button agent-stop-tree" disabled={pending} onClick={async () => { setPending(true); setError(null); try { await api.commandAgentTask(task.id, { type: "stop", subtree: true }); await refresh(); } catch (value) { setError(String(value)); } finally { setPending(false); } }}><Stop size={14} /> Остановить ветку</button> : null}
  </div> : null}
  {open && steering && active ? <form className="agent-steer" onSubmit={async event => { event.preventDefault(); const value = message.trim(); if (!value) return; setPending(true); setError(null); try { await api.commandAgentTask(task.id, { type: "steer", message: value }); setMessage(""); setSteering(false); await refresh(); } catch (reason) { setError(String(reason)); } finally { setPending(false); } }}>
    <label htmlFor={`agent-steer-${task.id}`}>Уточнение для субагента</label><textarea id={`agent-steer-${task.id}`} value={message} maxLength={8000} disabled={pending} onChange={event => setMessage(event.target.value)} placeholder="Например: не изменяй базу данных" />
    <div><small>{message.length}/8000</small><button className="primary-button" disabled={pending || !message.trim()} type="submit">Передать</button></div>
  </form> : null}
  {open && error ? <p className="agent-control-error" role="alert">Не удалось выполнить действие. {error}</p> : null}
  {open && task.result?.summary ? <div className="agent-result"><p>{task.result.summary}</p>
    {task.result.changed_files?.length ? <small>Файлы: {task.result.changed_files.join(", ")}</small> : null}</div> : null}
  {descendants.length ? <ul>{descendants.map(child => <TaskNode key={child.id} task={child} children={children} refresh={refresh} />)}</ul> : null}</li>;
}

export function AgentTaskTree({ turnId }: { turnId: string }) {
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [receipts, setReceipts] = useState<AgentCompletionReceipt[]>([]);
  const [watches, setWatches] = useState<AgentHeartbeatWatch[]>([]);
  const [heartbeatEvents, setHeartbeatEvents] = useState<AgentHeartbeatEvent[]>([]);
  const [noticeError, setNoticeError] = useState<string | null>(null);
  const applyBackground = (background: Awaited<ReturnType<typeof api.agentBackground>>, taskList: AgentTask[]) => {
    const taskIds = new Set(taskList.map(task => task.id));
    setReceipts(background.receipts.filter(receipt => receipt.root_turn_id === turnId));
    setWatches((background.watches ?? []).filter(watch => taskIds.has(watch.task_id)));
    setHeartbeatEvents((background.heartbeat_events ?? []).filter(event => taskIds.has(event.task_id)));
  };
  const refresh = async () => {
    const value = await api.agentTaskTree(turnId);
    setTasks(value);
    if (value[0]?.session_id) {
      const background = await api.agentBackground(value[0].session_id);
      applyBackground(background, value);
    }
  };
  const active = tasks.some(task => !terminal.has(task.status));
  const watching = watches.some(watch => watch.status === "active");
  useEffect(() => {
    let disposed = false;
    const load = async () => {
      const value = await api.agentTaskTree(turnId).catch(() => []);
      if (disposed) return;
      setTasks(value);
      if (value[0]?.session_id) {
        const background = await api.agentBackground(value[0].session_id).catch(() => null);
        if (!disposed && background) applyBackground(background, value);
      }
    };
    void load();
    const timer = active || watching ? window.setInterval(() => void load(), 2000) : undefined;
    return () => { disposed = true; if (timer) window.clearInterval(timer); };
  }, [turnId, active, watching]);
  const children = useMemo(() => {
    const value = new Map<string | null, AgentTask[]>();
    tasks.forEach(task => value.set(task.parent_task_id, [...(value.get(task.parent_task_id) ?? []), task]));
    return value;
  }, [tasks]);
  const roots = children.get(null) ?? [];
  if (!roots.length) return null;
  return <details className="agent-tree" open><summary><TreeStructure size={15} aria-hidden="true" /> Субагенты <span aria-label={`${tasks.filter(task => task.status === "completed").length} из ${tasks.length} завершено`}>{tasks.filter(task => task.status === "completed").length}/{tasks.length}</span></summary>
    {watches.some(watch => watch.status === "active") ? <div className="agent-watch-state" role="status"><Pulse size={16} /><span>Наблюдение за фоновыми задачами активно</span><small>{watches.filter(watch => watch.status === "active").length}</small></div> : null}
    {receipts.map(receipt => <div className="agent-receipt" role="status" key={receipt.id}><CheckCircle size={16} /><span>Фоновая задача {receiptLabel[receipt.status]}</span><button className="text-button" onClick={async () => { await api.acknowledgeAgentReceipt(receipt.id); setReceipts(value => value.filter(item => item.id !== receipt.id)); }}>Скрыть</button></div>)}
    {heartbeatEvents.map(event => {
      const goal = tasks.find(task => task.id === event.task_id)?.goal;
      return <div className={`agent-heartbeat-event agent-heartbeat-${event.type}`} role={event.type === "stalled" || event.type === "failed" ? "alert" : "status"} key={event.id}>
        {event.type === "stalled" || event.type === "failed" ? <WarningCircle size={16} weight="fill" /> : event.type === "resumed" ? <Pulse size={16} /> : <CheckCircle size={16} />}
        <span><strong>{goal || "Фоновая задача"}</strong><small>{heartbeatLabel[event.type]}</small></span>
        <button className="text-button" onClick={async () => {
          setNoticeError(null);
          try {
            await api.acknowledgeAgentHeartbeatEvent(event.id);
            setHeartbeatEvents(value => value.filter(item => item.id !== event.id));
          } catch {
            setNoticeError("Не удалось скрыть уведомление наблюдения");
          }
        }}>Скрыть</button>
      </div>;
    })}
    {noticeError ? <p className="agent-control-error" role="alert">{noticeError}</p> : null}
    <ul>{roots.map(task => <TaskNode key={task.id} task={task} children={children} refresh={refresh} />)}</ul></details>;
}
