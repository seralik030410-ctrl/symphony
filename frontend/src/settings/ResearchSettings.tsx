import { Globe, ShieldCheck, WarningCircle } from "@phosphor-icons/react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { ResearchSettings as Value, Session } from "../types";

const empty: Value = { enabled: false, allowed_domains: [], search_provider: "DuckDuckGo HTML", search_domain: "html.duckduckgo.com" };

export function ResearchSettings({ session, active }: { session: Session | null; active: boolean }) {
  const [saved, setSaved] = useState(empty);
  const [enabled, setEnabled] = useState(false);
  const [domains, setDomains] = useState("");
  const [state, setState] = useState<"loading" | "idle" | "saving" | "error">("loading");
  const [message, setMessage] = useState("");
  const sessionId = session?.id ?? null;
  const list = useMemo(() => [...new Set(domains.split(/[,\n]/).map(item => item.trim()).filter(Boolean))], [domains]);

  useEffect(() => {
    if (!sessionId) { setState("idle"); return; }
    let cancelled = false;
    setState("loading");
    api.researchSettings(sessionId).then(value => {
      if (cancelled) return;
      setSaved(value); setEnabled(value.enabled); setDomains(value.allowed_domains.join("\n")); setState("idle");
    }).catch(error => { if (!cancelled) { setMessage(error instanceof Error ? error.message : "Настройки интернета недоступны"); setState("error"); } });
    return () => { cancelled = true; };
  }, [sessionId]);

  async function save(nextEnabled = enabled, emergency = false) {
    if (!sessionId || state === "saving") return;
    setState("saving"); setMessage(nextEnabled ? "Сохраняем сетевые границы…" : "Отключаем интернет…");
    try {
      const value = await api.updateResearchSettings(sessionId, { enabled: nextEnabled, allowed_domains: emergency ? saved.allowed_domains : list });
      setSaved(value); setEnabled(value.enabled); setDomains(value.allowed_domains.join("\n")); setMessage(value.enabled ? "Интернет включён для этого чата" : "Интернет выключен"); setState("idle");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Настройки не сохранены"); setState("error"); }
  }

  const grantsChanged = enabled || list.join("\n") !== saved.allowed_domains.join("\n");
  return <section className="general-settings research-settings">
    <header className="settings-content-header"><div><h1>Интернет</h1><p>Сеть принадлежит host-приложению, а не модели или sandbox. Настройки действуют только в текущем чате.</p></div></header>
    {!session ? <p className="settings-empty">Выберите чат, чтобы настроить исследование.</p> : <>
      {message ? <p className={state === "error" ? "settings-alert" : "context-settings-message"} role={state === "error" ? "alert" : "status"}>{state === "error" ? <WarningCircle size={16} /> : null}{message}</p> : null}
      <h2>Доступ</h2><section className="settings-card research-access">
        <label className="settings-row"><div><strong>Интернет для этого чата</strong><small>По умолчанию выключен. Поиск всё равно отдельно покажет очищенную фразу и попросит подтверждение.</small></div><input type="checkbox" checked={enabled} disabled={state === "loading" || state === "saving" || (active && !saved.enabled)} onChange={event => setEnabled(event.target.checked)} /></label>
        <div className="settings-row"><div><strong>Поисковик</strong><small>Получает только подтверждённые публичные ключевые слова, не историю и не файлы.</small></div><span><Globe size={17} /> {saved.search_provider}</span></div>
      </section>
      <h2>Разрешённые сайты</h2><section className="settings-card research-domains">
        <label><strong>Точные домены</strong><small>По одному в строке: <code>docs.python.org</code>. Без `https://`, путей, портов и `*`. Неизвестный домен можно разово подтвердить прямо в чате.</small><textarea value={domains} disabled={active || state === "loading" || state === "saving"} onChange={event => setDomains(event.target.value)} spellCheck={false} placeholder={"docs.python.org\nexample.org"} /></label>
        <p><ShieldCheck size={17} /> HTTPS, DNS и каждая переадресация проверяются. Localhost, локальная сеть, metadata IP, cookies, proxy-переменные и URL с возможным секретом запрещены.</p>
      </section>
      <footer className="research-actions">
        {active && saved.enabled ? <button className="danger-text" disabled={state === "saving"} onClick={() => void save(false, true)}>Выключить сейчас</button> : null}
        <button className="settings-primary" disabled={state === "loading" || state === "saving" || (active && grantsChanged)} onClick={() => void save()}>{state === "saving" ? "Сохраняем…" : "Сохранить интернет"}</button>
      </footer>
      <p className="settings-empty research-note">Выключение доступно во время ответа и не ждёт следующего turn. Оно останавливает чтение на ближайшей проверке; Stop по-прежнему отменяет весь turn.</p>
    </>}
  </section>;
}
