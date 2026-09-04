import {
  ChatCircle,
  ChatsCircle,
  Plus,
  PaperPlaneRight,
  Stop,
  WarningCircle,
  X,
  ArrowDown,
  SidebarSimple, ListBullets, Trash, Monitor, ArrowCounterClockwise, Code, Gear,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { EventLedger } from "./activity/EventLedger";
import { api, subscribeToTurn } from "./api";
import { applyTurnEvent, isFinalEvent } from "./chat/eventState";
import { MessageList } from "./chat/MessageList";
import { useConversationScroll } from "./chat/useConversationScroll";
import { ModelPicker } from "./settings/ModelPicker";
import { SettingsPage } from "./settings/SettingsPage";
import { CustomSelect } from "./ui/CustomSelect";
import { Dialog } from "./ui/Dialog";
import { WorkspacePanel } from "./workspace/WorkspacePanel";
import { UploadButton } from "./artifacts/UploadButton";
import { AttachmentTray } from "./chat/AttachmentTray";
import { ImageMode } from "./chat/ImageMode";
import type { OpenWorkspace } from "./workspace/state";
import { previewPath } from "./chat/preview";
import { desktopInvoke, listenNativeDrops, uploadDroppedBatch, type NativeFile } from "./desktop";
import type {
  Message,
  ModelProfile,
  Session,
  SessionSummary,
  Turn,
  TurnEvent,
  Attachment,
} from "./types";

const ACTIVE_STATUSES = new Set(["queued", "preparing", "model_running"]);

interface ConversationState {
  messages: Message[];
  turns: Turn[];
}

function summaryFromSession(session: Session): SessionSummary {
  const lastMessage = session.messages.at(-1);
  return {
    id: session.id,
    title: session.title,
    provider: session.provider,
    model: session.model,
    created_at: session.created_at,
    updated_at: session.updated_at,
    last_message_preview: lastMessage?.content.slice(0, 90) ?? "",
    active_turn: session.turns.some((turn) => ACTIVE_STATUSES.has(turn.status)),
  };
}

export default function App() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [session, setSession] = useState<Session | null>(null);
  const [conversation, setConversation] = useState<ConversationState>({ messages: [], turns: [] });
  const [events, setEvents] = useState<TurnEvent[]>([]);
  const [profiles, setProfiles] = useState<ModelProfile[]>([]);
  const [draft, setDraft] = useState("");
  const [pendingAttachments, setPendingAttachments] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const [imageMode, setImageMode] = useState<"vision" | "ocr">("vision");
  const [initializing, setInitializing] = useState(true);
  const [sending, setSending] = useState(false);
  const [retryingTurnId, setRetryingTurnId] = useState<string | null>(null);
  const [decidingApprovalId, setDecidingApprovalId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [chatsOpen, setChatsOpen] = useState(() => localStorage.getItem("symphony.chatsOpen") !== null ? localStorage.getItem("symphony.chatsOpen") === "true" : window.innerWidth > 720);
  const [eventsOpen, setEventsOpen] = useState(() => localStorage.getItem("symphony.eventsOpen") !== null ? localStorage.getItem("symphony.eventsOpen") === "true" : window.innerWidth > 1120);
  const [workspaceOpen, setWorkspaceOpen] = useState(() => localStorage.getItem("symphony.workspaceOpen") === "true");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [workspaceRequest, setWorkspaceRequest] = useState<OpenWorkspace | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<SessionSummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deletedChat, setDeletedChat] = useState<SessionSummary | null>(null);
  const [trash, setTrash] = useState<Array<{ id: string; title: string; deleted_at: string }> | null>(null);
  const [emptyTrashConfirm, setEmptyTrashConfirm] = useState(false);
  const [emptyingTrash, setEmptyingTrash] = useState(false);
  useEffect(() => { localStorage.setItem("symphony.chatsOpen", String(chatsOpen)); }, [chatsOpen]);
  useEffect(() => { localStorage.setItem("symphony.eventsOpen", String(eventsOpen)); }, [eventsOpen]);
  useEffect(() => { localStorage.setItem("symphony.workspaceOpen", String(workspaceOpen)); }, [workspaceOpen]);
  const subscriptions = useRef(new Map<string, EventSource>());
  const currentSessionId = useRef<string | null>(null);
  const knownEventIds = useRef(new Set<number>());
  const onIncomingEvent = useRef<(event: TurnEvent) => void>(() => undefined);
  const scroll = useConversationScroll(!initializing, session?.id);
  const composerInput = useRef<HTMLTextAreaElement>(null);
  const desktopDropBusy = useRef(false);
  const { followNext } = scroll;
  const activeTurn = useMemo(
    () => conversation.turns.find((turn) => ACTIVE_STATUSES.has(turn.status)),
    [conversation.turns],
  );
  const dropContext = useRef({ blocked: false, count: 0 });
  dropContext.current = { blocked: Boolean(activeTurn) || sending || uploading || settingsOpen, count: pendingAttachments.length };

  useEffect(() => {
    let cancelled = false;
    let unlisten: (() => void) | undefined;
    void listenNativeDrops(async dropped => {
      if (cancelled || !dropped.length) return;
      const sessionId = currentSessionId.current;
      if (!sessionId || dropContext.current.blocked || desktopDropBusy.current) { setError("Вернитесь в чат и дождитесь завершения текущего действия перед перетаскиванием файлов"); return; }
      const available = 8 - dropContext.current.count;
      if (dropped.length > available) { setError(`Можно добавить ещё ${available} файлов. В одном сообщении — не больше восьми.`); return; }
      desktopDropBusy.current = true; setUploading(true);
      try {
        await uploadDroppedBatch(dropped, {
          isCurrent: () => !cancelled && currentSessionId.current === sessionId,
          consume: token => desktopInvoke<NativeFile>("consume_dropped_file", { token }),
          upload: file => api.uploadInput(sessionId, file.filename, file.content_base64),
          append: uploaded => setPendingAttachments(current => [...current, uploaded]),
        });
        if (currentSessionId.current === sessionId) composerInput.current?.focus();
      } catch (cause) {
        if (!cancelled && currentSessionId.current === sessionId) setError(cause instanceof Error ? cause.message : "Не удалось прикрепить перетащенный файл");
      } finally {
        desktopDropBusy.current = false; if (!cancelled) setUploading(false);
      }
    }, message => { if (!cancelled) setError(message); }).then(value => { if (cancelled) value(); else unlisten = value; }).catch(cause => { if (!cancelled) setError(cause instanceof Error ? cause.message : "Desktop drag-and-drop недоступен"); });
    return () => { cancelled = true; unlisten?.(); };
  }, []);

  useLayoutEffect(() => {
    const input = composerInput.current;
    if (!input) return;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
  }, [draft, initializing]);

  const latestPreview = [...events].reverse().find(event => event.type === "preview.ready")?.payload.preview_url;

  function openPreview(url: string) {
    if (!session) return;
    const safe = previewPath(url, session.id, window.location.origin);
    if (safe) openWorkspace("preview", safe);
    else setError("Этот preview не принадлежит текущему чату");
  }

  function openWorkspace(kind: OpenWorkspace["kind"], path?: string) {
    setWorkspaceRequest({ nonce: Date.now(), kind, path });
    setWorkspaceOpen(true);
    setEventsOpen(false);
  }

  const closeSubscriptions = useCallback(() => {
    subscriptions.current.forEach((source) => source.close());
    subscriptions.current.clear();
  }, []);

  const refreshSessionSnapshot = useCallback(async (sessionId: string) => {
    try {
      const [freshSession, freshSessions] = await Promise.all([
        api.getSession(sessionId),
        api.listSessions(),
      ]);
      if (currentSessionId.current !== sessionId) return;
      setSession(freshSession);
      setConversation({ messages: freshSession.messages, turns: freshSession.turns });
      setSessions(freshSessions);
    } catch (cause) {
      if (currentSessionId.current === sessionId) {
        setError(cause instanceof Error ? cause.message : "Не удалось обновить чат");
      }
    }
  }, []);

  const attachStream = useCallback((turnId: string, after: number) => {
    subscriptions.current.get(turnId)?.close();
    const source = subscribeToTurn(
      turnId,
      after,
      (event) => onIncomingEvent.current(event),
      () => {
        if (source.readyState === EventSource.CLOSED) {
          subscriptions.current.delete(turnId);
          const currentId = currentSessionId.current;
          if (currentId) {
            window.setTimeout(() => void refreshSessionSnapshot(currentId), 250);
          }
        }
      },
    );
    subscriptions.current.set(turnId, source);
  }, [refreshSessionSnapshot]);

  onIncomingEvent.current = (event: TurnEvent) => {
    if (event.session_id !== currentSessionId.current || knownEventIds.current.has(event.id)) return;
    knownEventIds.current.add(event.id);
    setEvents((current) => [...current, event].sort((a, b) => a.id - b.id));
    setConversation((current) => applyTurnEvent(current.messages, current.turns, event));
    if (isFinalEvent(event)) {
      subscriptions.current.get(event.turn_id)?.close();
      subscriptions.current.delete(event.turn_id);
      window.setTimeout(() => void refreshSessionSnapshot(event.session_id), 80);
    }
  };

  const openSession = useCallback(
    async (sessionId: string) => {
      closeSubscriptions();
      currentSessionId.current = sessionId;
      setSession(null);
      setConversation({ messages: [], turns: [] });
      setEvents([]);
      setDraft("");
      setPendingAttachments([]);
      setUploading(false);
      setImageMode(localStorage.getItem(`symphony.imageMode.${sessionId}`) === "ocr" ? "ocr" : "vision");
      setWorkspaceRequest(null);
      if (window.innerWidth <= 720) setChatsOpen(false);
      localStorage.setItem("symphony.session", sessionId);
      knownEventIds.current = new Set();
      setError(null);
      try {
        const [loaded, pending] = await Promise.all([api.getSession(sessionId), api.listPendingInputs(sessionId)]);
        const eventGroups = await Promise.all(
          loaded.turns.map(async (turn) => ({
            turn,
            events: await api.getTurnEvents(turn.id),
          })),
        );
        if (currentSessionId.current !== sessionId) return;
        const allEvents = eventGroups.flatMap((group) => group.events).sort((a, b) => a.id - b.id);
        knownEventIds.current = new Set(allEvents.map((event) => event.id));
        let hydrated: ConversationState = { messages: loaded.messages, turns: loaded.turns };
        for (const group of eventGroups) {
          for (const event of group.events) {
            if (event.sequence > group.turn.last_event_sequence) {
              hydrated = applyTurnEvent(hydrated.messages, hydrated.turns, event);
            }
          }
        }
        setSession(loaded);
        setPendingAttachments(pending);
        setConversation(hydrated);
        setEvents(allEvents);
        for (const group of eventGroups) {
          if (ACTIVE_STATUSES.has(group.turn.status)) {
            const after = Math.max(
              group.turn.last_event_sequence,
              ...group.events.map((event) => event.sequence),
            );
            attachStream(group.turn.id, after);
          }
        }
      } catch (cause) {
        if (currentSessionId.current === sessionId) setError(cause instanceof Error ? cause.message : "Не удалось открыть чат");
      }
    },
    [attachStream, closeSubscriptions],
  );

  useEffect(() => {
    let cancelled = false;
    async function initialize() {
      try {
        const [availableSessions, availableProfiles] = await Promise.all([
          api.listSessions(),
          api.listModels(),
        ]);
        if (cancelled) return;
        setProfiles(availableProfiles);
        let target = localStorage.getItem("symphony.session");
        if (!target || !availableSessions.some((item) => item.id === target)) {
          target = availableSessions[0]?.id ?? null;
        }
        let nextSessions = availableSessions;
        if (!target) {
          const created = await api.createSession();
          if (cancelled) return;
          target = created.id;
          nextSessions = [summaryFromSession(created)];
        }
        setSessions(nextSessions);
        await openSession(target);
      } catch (cause) {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : "Symphony не запустилась");
        }
      } finally {
        if (!cancelled) setInitializing(false);
      }
    }
    void initialize();
    return () => {
      cancelled = true;
      closeSubscriptions();
    };
  }, [closeSubscriptions, openSession]);

  async function createNewSession() {
    setError(null);
    try {
      const created = await api.createSession();
      setSessions((current) => [summaryFromSession(created), ...current]);
      await openSession(created.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось создать чат");
    }
  }

  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      const modifier = event.metaKey || event.ctrlKey;
      if (modifier && event.key === ",") {
        event.preventDefault();
        setSettingsOpen(true);
      } else if (modifier && event.key.toLowerCase() === "n" && !event.shiftKey && !event.altKey) {
        event.preventDefault();
        void createNewSession();
      } else if (event.key === "Escape" && settingsOpen) {
        setSettingsOpen(false);
      }
    }
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, [openSession, settingsOpen]);

  async function deleteChat() {
    if (!deleteTarget || deleting) return;
    setDeleting(true);
    const target = deleteTarget;
    try {
      await api.deleteSession(target.id);
      setDeleteTarget(null);
      setDeletedChat(target);
      const remaining = await api.listSessions();
      setSessions(remaining);
      if (currentSessionId.current === target.id) {
        if (remaining[0]) await openSession(remaining[0].id);
        else await createNewSession();
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось удалить чат"); }
    finally { setDeleting(false); }
  }

  async function restoreChat(id: string) {
    try {
      await api.restoreSession(id);
      setDeletedChat(null);
      setSessions(await api.listSessions());
      setTrash(null);
      await openSession(id);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось восстановить чат"); }
  }

  async function showTrash() {
    try { setEmptyTrashConfirm(false); setTrash(await api.listTrash()); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось открыть корзину"); }
  }

  async function emptyTrash() {
    if (!trash?.length || emptyingTrash) return;
    setEmptyingTrash(true);
    try {
      const result = await api.emptyTrash();
      setTrash([]);
      setDeletedChat(null);
      setEmptyTrashConfirm(false);
      if (result.storage_warnings.length) {
        setError(`Чаты удалены, но не удалось очистить ${result.storage_warnings.length} папок на диске`);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось очистить корзину");
    } finally {
      setEmptyingTrash(false);
    }
  }

  async function sendMessage() {
    const content = draft.trim() || (pendingAttachments.length ? imageMode === "ocr" ? "Извлеки текст из прикреплённых файлов" : "Рассмотри прикреплённые файлы" : "");
    if (!session || !content || activeTurn || sending || uploading) return;
    setSending(true);
    setError(null);
    setDraft("");
    try {
      const created = await api.createTurn(session.id, content, pendingAttachments.map(item => item.id), imageMode);
      if (currentSessionId.current !== session.id) { setSessions(await api.listSessions()); return; }
      followNext();
      setConversation((current) => ({
        messages: [...current.messages, created.user_message, created.assistant_message],
        turns: [...current.turns, created.turn],
      }));
      setPendingAttachments([]);
      attachStream(created.turn.id, 0);
      const freshSessions = await api.listSessions();
      setSessions(freshSessions);
      setSession((current) =>
        current ? { ...current, title: freshSessions.find((item) => item.id === current.id)?.title ?? current.title } : current,
      );
    } catch (cause) {
      if (currentSessionId.current === session.id) {
        setDraft(content);
        setError(cause instanceof Error ? cause.message : "Сообщение не отправлено");
      }
    } finally {
      setSending(false);
    }
  }

  async function removeAttachment(id: string) {
    if (!session || sending || activeTurn) return;
    try {
      await api.deleteInput(session.id, id);
      if (currentSessionId.current === session.id) setPendingAttachments(current => current.filter(item => item.id !== id));
    } catch (cause) {
      if (currentSessionId.current === session.id) setError(cause instanceof Error ? cause.message : "Не удалось убрать вложение");
    }
  }

  async function stopTurn() {
    if (!activeTurn) return;
    setError(null);
    try {
      await api.cancelTurn(activeTurn.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось остановить ответ");
    } finally {
      if (session) void refreshSessionSnapshot(session.id);
    }
  }

  async function retryTurn(turnId: string) {
    if (!session || activeTurn || retryingTurnId) return;
    setRetryingTurnId(turnId);
    setError(null);
    try {
      const created = await api.retryTurn(turnId);
      if (currentSessionId.current !== session.id) { setSessions(await api.listSessions()); return; }
      followNext();
      setConversation((current) => ({
        messages: [...current.messages, created.user_message, created.assistant_message],
        turns: [...current.turns, created.turn],
      }));
      attachStream(created.turn.id, 0);
      setSessions(await api.listSessions());
    } catch (cause) {
      if (currentSessionId.current === session.id) setError(cause instanceof Error ? cause.message : "Не удалось повторить turn");
    } finally {
      setRetryingTurnId(null);
    }
  }

  async function changeModel(provider: "ollama" | "openai", model: string) {
    if (!session || activeTurn) return;
    try {
      const updated = await api.updateSession(session.id, { provider, model });
      if (currentSessionId.current !== session.id) return;
      setSession(updated);
      setConversation({ messages: updated.messages, turns: updated.turns });
      setSessions((current) =>
        current.map((item) => (item.id === updated.id ? summaryFromSession(updated) : item)),
      );
    } catch (cause) {
      if (currentSessionId.current === session.id) setError(cause instanceof Error ? cause.message : "Модель не переключена");
    }
  }

  async function changePolicy(policy_profile: Session["policy_profile"]) {
    if (!session || activeTurn) return;
    try {
      const updated = await api.updateSession(session.id, { policy_profile });
      if (currentSessionId.current !== session.id) return;
      setSession(updated);
      setConversation({ messages: updated.messages, turns: updated.turns });
      setSessions((current) =>
        current.map((item) => (item.id === updated.id ? summaryFromSession(updated) : item)),
      );
    } catch (cause) {
      if (currentSessionId.current === session.id) setError(cause instanceof Error ? cause.message : "Профиль доступа не переключён");
    }
  }

  async function decideApproval(approvalId: string, approved: boolean) {
    if (decidingApprovalId) return;
    setDecidingApprovalId(approvalId);
    setError(null);
    try {
      await api.decideApproval(approvalId, approved);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Решение не сохранено");
    } finally {
      setDecidingApprovalId(null);
    }
  }

  if (initializing) {
    return (
      <main className="boot-screen">
        <div className="boot-mark">S2</div>
        <p>Восстанавливаем чаты</p>
        <div className="boot-line" />
      </main>
    );
  }

  if (settingsOpen) {
    return <SettingsPage
      session={session}
      profiles={profiles}
      active={Boolean(activeTurn)}
      onPolicy={(value) => void changePolicy(value)}
      onModel={(provider, model) => void changeModel(provider, model)}
      onClose={() => setSettingsOpen(false)}
      onSessionSaved={updated => { if (currentSessionId.current === updated.id) setSession(updated); }}
    />;
  }

  return (
    <main className="app-shell" data-chats-open={chatsOpen} data-events-open={eventsOpen && !workspaceOpen} data-workspace-open={workspaceOpen}>
      {(chatsOpen || eventsOpen) ? <button className="panel-scrim" aria-label="Закрыть боковые панели" onClick={() => { setChatsOpen(false); setEventsOpen(false); }} /> : null}
      {chatsOpen ? <aside className="session-rail" aria-label="Чаты">
        <div className="brand-row">
          <div className="brand-mark" aria-hidden="true">S2</div>
          <div>
            <strong>Symphony</strong>
            <span>Chat runtime</span>
          </div>
        </div>
        <button className="new-chat-button" type="button" onClick={() => void createNewSession()}>
          <Plus size={17} weight="bold" aria-hidden="true" />
          Новый чат
        </button>
        <div className="session-heading">Чаты</div>
        <nav className="session-list">
          {sessions.map((item) => (
            <div className="session-row" key={item.id}>
            <button
              type="button"
              className={item.id === session?.id ? "session-item selected" : "session-item"}
              onClick={() => void openSession(item.id)}
            >
              <ChatCircle size={18} weight={item.id === session?.id ? "fill" : "regular"} aria-hidden="true" />
              <span>
                <strong>{item.title}</strong>
                <small>{item.last_message_preview || `${item.provider} / ${item.model}`}</small>
              </span>
              {item.active_turn ? <i aria-label="Есть активный ответ">ответ</i> : null}
            </button>
            <button type="button" className="icon-button session-delete" aria-label={`Удалить чат: ${item.title}`} title="Удалить чат"
              onClick={() => setDeleteTarget(item)}><Trash size={18} weight="bold" /></button>
            </div>
          ))}
        </nav>
        <div className="rail-footer">
          <button className="text-button" onClick={() => void showTrash()}><Trash size={18} weight="bold" /> Корзина</button>
          <span>Этап 6 · Контекст и память</span>
          <strong>Документы и инструменты</strong>
        </div>
      </aside> : null}

      <section className="conversation-pane">
        <div className="workspace-toolbar" aria-label="Панели и действия чата">
          <button className="icon-button" aria-label={chatsOpen ? "Скрыть чаты" : "Показать чаты"} title="Чаты" aria-pressed={chatsOpen}
            onClick={() => setChatsOpen(value => !value)}><SidebarSimple size={19} /></button>
          <button className="icon-button" aria-label="Создать новый чат" title="Новый чат" onClick={() => void createNewSession()}><Plus size={19} /></button>
          <button className="icon-button" aria-label="Открыть настройки" title="Настройки" onClick={() => setSettingsOpen(true)}><Gear size={19} /></button>
          <span className="toolbar-spacer" />
          {typeof latestPreview === "string" ? <button className="text-button" onClick={() => openPreview(latestPreview)}><Monitor size={17} /> Preview</button> : null}
          <button className="icon-button" aria-label="Открыть файлы проекта" title="Файлы проекта" disabled={!session}
            onClick={() => openWorkspace("files")}><Code size={19} /></button>
          <button className="icon-button" aria-label={eventsOpen ? "Скрыть события" : "Показать события"} title="События" aria-pressed={eventsOpen}
            onClick={() => { setEventsOpen(value => !value); setWorkspaceOpen(false); }}><ListBullets size={19} /></button>
        </div>
        <header className="conversation-header">
          <div className="conversation-title">
            <ChatsCircle size={20} weight="fill" aria-hidden="true" />
            <div>
              <h1>{session?.title ?? "Чат"}</h1>
              <span>{activeTurn ? "Модель отвечает" : "Готов к сообщению"}</span>
            </div>
          </div>
          {session ? (
            <div className="runtime-selects">
              <ModelPicker
                session={session}
                profiles={profiles}
                disabled={Boolean(activeTurn)}
                onChange={(provider, model) => void changeModel(provider, model)}
              />
            </div>
          ) : null}
          <CustomSelect
            className="mobile-session-select"
            ariaLabel="Выберите чат"
            value={session?.id ?? ""}
            options={sessions.map((item) => ({
              value: item.id,
              label: item.title,
              description: item.active_turn ? "Модель отвечает" : `${item.provider} · ${item.model}`,
            }))}
            onChange={(sessionId) => void openSession(sessionId)}
          />
        </header>

        {error ? (
          <div className="error-banner" role="alert">
            <WarningCircle size={18} weight="fill" aria-hidden="true" />
            <span>{error}</span>
            <button type="button" onClick={() => setError(null)} aria-label="Закрыть сообщение">
              <X size={16} weight="bold" aria-hidden="true" />
            </button>
          </div>
        ) : null}

        {deletedChat ? <div className="undo-banner" role="status">
          <span>Чат перемещён в корзину</span>
          <button className="text-button" onClick={() => void restoreChat(deletedChat.id)}>Отменить</button>
          <button className="icon-button" aria-label="Закрыть уведомление" onClick={() => setDeletedChat(null)}><X size={16} /></button>
        </div> : null}

        <div className="conversation-viewport">
          <div
            className="conversation-scroll"
            ref={scroll.scrollRef}
            role="region"
            tabIndex={0}
            aria-label="История чата"
            onScroll={scroll.onScroll}
            onWheel={(event) => { if (event.deltaY < 0) scroll.pause(); }}
            onTouchStart={scroll.pause}
            onKeyDown={(event) => {
              if (event.target !== event.currentTarget) return;
              const element = event.currentTarget;
              const page = element.clientHeight * 0.85;
              const deltas: Record<string, number> = {
                ArrowUp: -48, ArrowDown: 48, PageUp: -page, PageDown: page,
              };
              if (event.key === "End") { event.preventDefault(); scroll.toBottom(); }
              else if (event.key === "Home") {
                event.preventDefault(); scroll.pause(); element.scrollTop = 0;
              } else if (event.key in deltas) {
                event.preventDefault();
                if (deltas[event.key] < 0) scroll.pause();
                element.scrollTop += deltas[event.key];
              }
            }}
            onClickCapture={(event) => {
              const link = (event.target as Element).closest<HTMLAnchorElement>("a[href]");
              if (link && session && previewPath(link.href, session.id, window.location.origin)) {
                event.preventDefault(); event.stopPropagation(); openPreview(link.href);
              }
              // Keep an expanded disclosure in view instead of jumping to the end.
              if ((event.target as Element).closest("summary, .reasoning-toggle")) scroll.pause();
            }}
          >
            <div className="conversation-content" ref={scroll.contentRef}>
              <MessageList
                messages={conversation.messages}
                turns={conversation.turns}
                events={events}
                retryingTurnId={retryingTurnId}
                onRetry={(turnId) => void retryTurn(turnId)}
                decidingApprovalId={decidingApprovalId}
                onApproval={(approvalId, approved) => void decideApproval(approvalId, approved)}
                onPreview={openPreview}
                onFile={path => openWorkspace("file", path)}
                onChanges={() => openWorkspace("changes")}
                onArtifact={id => openWorkspace("artifact", id)}
              />
            </div>
          </div>

          {scroll.showJump ? (
            <button
              className="scroll-to-bottom"
              type="button"
              onClick={scroll.toBottom}
              aria-label="К последнему сообщению"
              title="К последнему сообщению"
            >
              <ArrowDown size={16} weight="bold" aria-hidden="true" />
            </button>
          ) : null}
        </div>

        <div className="composer-zone">
          {session ? <AttachmentTray sessionId={session.id} items={pendingAttachments} disabled={Boolean(activeTurn) || sending} onRemove={id => void removeAttachment(id)} /> : null}
          {session && pendingAttachments.some(item => item.mime_type.startsWith("image/")) ? <ImageMode session={session} value={imageMode} disabled={Boolean(activeTurn) || sending || uploading} onChange={value => { setImageMode(value); localStorage.setItem(`symphony.imageMode.${session.id}`, value); }} /> : null}
          <div className="composer" data-busy={Boolean(activeTurn)}>
            {session ? <UploadButton key={session.id} sessionId={session.id} disabled={Boolean(activeTurn) || sending || uploading || pendingAttachments.length >= 8}
              remaining={8 - pendingAttachments.length} onBusyChange={value => { if (currentSessionId.current === session.id) setUploading(value); }}
              onUploaded={value => { if (currentSessionId.current === session.id) {
                  if (value.id) setPendingAttachments(current => [...current, value]);
                else setDraft(current => `${current}${current ? "\n" : ""}Используй файл ${value.path}`);
                composerInput.current?.focus();
              } }}
              onError={message => { if (currentSessionId.current === session.id) setError(message); }} /> : null}
            <textarea
              ref={composerInput}
              value={draft}
              rows={1}
              placeholder={activeTurn ? "Дождитесь ответа или остановите его" : "Напишите сообщение"}
              disabled={!session || Boolean(activeTurn)}
              onChange={(event) => {
                setDraft(event.target.value);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void sendMessage();
                }
              }}
            />
            {activeTurn ? (
              <button className="stop-button" type="button" onClick={() => void stopTurn()}>
                <Stop size={16} weight="fill" aria-hidden="true" />
                Остановить
              </button>
            ) : (
              <button
                className="send-button"
                type="button"
                disabled={!session || (!draft.trim() && !pendingAttachments.length) || sending || uploading}
                onClick={() => void sendMessage()}
                aria-label="Отправить сообщение"
              >
                <PaperPlaneRight size={18} weight="fill" aria-hidden="true" />
              </button>
            )}
          </div>
          <p>Enter отправляет, Shift + Enter добавляет строку. Контекст этого чата изолирован.</p>
        </div>
      </section>

      {eventsOpen && !workspaceOpen ? <EventLedger events={events} onClose={() => setEventsOpen(false)} /> : null}
      {session ? <WorkspacePanel key={session.id} sessionId={session.id} events={events} request={workspaceRequest} visible={workspaceOpen} onClose={() => setWorkspaceOpen(false)} /> : null}
      {deleteTarget ? <Dialog title="Удалить чат?" onClose={() => { if (!deleting) setDeleteTarget(null); }}>
        <h2>Удалить чат?</h2><p>«{deleteTarget.title}» будет перемещён в корзину. История и файлы сохранятся — чат можно восстановить.</p>
        {deleteTarget.active_turn ? <p>Текущий ответ и его команды будут остановлены.</p> : null}
        <div className="dialog-actions">
          <button className="text-button" disabled={deleting} onClick={() => setDeleteTarget(null)}>Оставить</button>
          <button className="danger-button" disabled={deleting} onClick={() => void deleteChat()}>{deleting ? "Удаляем…" : "Удалить чат"}</button>
        </div>
      </Dialog> : null}
      {trash ? <Dialog title="Корзина чатов" onClose={() => { if (!emptyingTrash) { setTrash(null); setEmptyTrashConfirm(false); } }}>
        <header className="dialog-toolbar"><h2>{emptyTrashConfirm ? "Очистить корзину?" : "Корзина чатов"}</h2><button className="icon-button" disabled={emptyingTrash} aria-label="Закрыть корзину" onClick={() => { setTrash(null); setEmptyTrashConfirm(false); }}><X size={18} /></button></header>
        {emptyTrashConfirm ? <>
          <p>Все {trash.length} {trash.length === 1 ? "удалённый чат" : "удалённых чата"} и связанные файлы будут удалены навсегда. Это действие нельзя отменить.</p>
          <div className="dialog-actions"><button className="text-button" disabled={emptyingTrash} onClick={() => setEmptyTrashConfirm(false)}>Назад</button><button className="danger-button" disabled={emptyingTrash} onClick={() => void emptyTrash()}>{emptyingTrash ? "Очищаем…" : "Удалить навсегда"}</button></div>
        </> : <>
          {trash.length ? <ul className="trash-list">{trash.map(item => <li key={item.id}><span>{item.title}</span>
            <button className="text-button" onClick={() => void restoreChat(item.id)}><ArrowCounterClockwise size={16} /> Восстановить</button></li>)}</ul> : <p>Корзина пуста.</p>}
          {trash.length ? <footer className="trash-actions"><button className="text-button trash-empty-button" onClick={() => setEmptyTrashConfirm(true)}><Trash size={17} /> Очистить корзину</button></footer> : null}
        </>}
      </Dialog> : null}
    </main>
  );
}
