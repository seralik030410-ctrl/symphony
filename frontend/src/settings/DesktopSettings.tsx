import { ArrowsClockwise, CheckCircle, DownloadSimple, Key, Trash, WarningCircle } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { desktopInvoke, hasDesktopBridge } from "../desktop";
import { api } from "../api";

export function DesktopSettings() {
  const desktop = hasDesktopBridge();
  const [present, setPresent] = useState<boolean | null>(null);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [updateState, setUpdateState] = useState<"idle" | "checking" | "available" | "installing">("idle");
  const pendingUpdate = useRef<{ version: string; downloadAndInstall: () => Promise<void>; close: () => Promise<void> } | null>(null);

  useEffect(() => {
    if (!desktop) return;
    desktopInvoke<boolean>("has_openai_key").then(setPresent).catch(error => setMessage(error instanceof Error ? error.message : "Keychain недоступен"));
  }, [desktop]);
  useEffect(() => () => { void pendingUpdate.current?.close().catch(() => undefined); }, []);

  if (!desktop) return <><h2>Desktop</h2><section className="settings-card desktop-card"><div className="settings-row"><div><strong>Системное хранилище секретов</strong><small>В браузерном режиме API-ключ задаётся переменной окружения backend. Установленная версия сохраняет его в Keychain.</small></div><span>Веб-режим</span></div></section></>;

  async function save() {
    if (!value.trim() || busy) return;
    setBusy(true); setMessage("");
    try { await desktopInvoke("set_openai_key", { value }); setValue(""); setPresent(true); setMessage("Ключ сохранён. Он применится после перезапуска приложения."); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Ключ не сохранён"); }
    finally { setBusy(false); }
  }

  async function remove() {
    if (busy) return;
    setBusy(true); setMessage("");
    try { await desktopInvoke("delete_openai_key"); setPresent(false); setValue(""); setMessage("Ключ удалён из системного хранилища. Перезапустите приложение, чтобы удалить его и из памяти runtime."); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Ключ не удалён"); }
    finally { setBusy(false); }
  }

  async function checkUpdate() {
    if (updateState !== "idle") return;
    setUpdateState("checking"); setMessage("");
    try {
      const { check } = await import("@tauri-apps/plugin-updater");
      const update = await check();
      if (update) { pendingUpdate.current = update; setUpdateState("available"); setMessage(`Доступна версия ${update.version}. Подпись будет проверена при установке.`); }
      else { setUpdateState("idle"); setMessage("Установлена актуальная версия."); }
    } catch (error) { setUpdateState("idle"); setMessage(error instanceof Error ? `Канал обновлений не настроен или недоступен: ${error.message}` : "Проверка обновлений недоступна"); }
  }

  async function installUpdate() {
    if (!pendingUpdate.current || updateState !== "available") return;
    setUpdateState("installing"); setMessage("Скачиваем и проверяем подпись обновления…");
    try {
      if ((await api.listSessions()).some(session => session.active_turn)) throw new Error("Сначала завершите ответы модели во всех чатах.");
      await pendingUpdate.current.downloadAndInstall();
      if ((await api.listSessions()).some(session => session.active_turn)) {
        setUpdateState("idle"); setMessage("Обновление установлено. Завершите ответы модели, затем перезапустите приложение вручную.");
        await pendingUpdate.current.close(); pendingUpdate.current = null;
        return;
      }
      const { relaunch } = await import("@tauri-apps/plugin-process");
      await relaunch();
    } catch (error) { setUpdateState("available"); setMessage(error instanceof Error ? error.message : "Обновление не установлено"); }
  }

  return <><h2>Desktop</h2><section className="settings-card desktop-card">
    <div className="settings-row"><div><strong>OpenAI-compatible API key</strong><small>Хранится в macOS Keychain или Windows Credential Manager. Symphony никогда не показывает сохранённое значение обратно.</small></div><span>{present ? <CheckCircle size={17} /> : <Key size={17} />} {present === null ? "Проверяем…" : present ? "Сохранён" : "Не задан"}</span></div>
    <div className="desktop-secret-row"><input type="password" autoComplete="off" value={value} disabled={busy} onChange={event => setValue(event.target.value)} placeholder="Новый ключ" aria-label="Новый OpenAI-compatible API key" /><button className="settings-primary" disabled={busy || !value.trim()} onClick={() => void save()}>Сохранить</button>{present ? <button className="danger-text" disabled={busy} onClick={() => void remove()}><Trash size={16} /> Удалить</button> : null}</div>
    <div className="settings-row"><div><strong>Обновления приложения</strong><small>Принимаются только пакеты, подписанные release-ключом Symphony.</small></div>{updateState === "available" ? <button className="settings-primary" onClick={() => void installUpdate()}><DownloadSimple size={16} /> Установить</button> : <button className="text-button" disabled={updateState !== "idle"} onClick={() => void checkUpdate()}><ArrowsClockwise size={16} /> {updateState === "checking" ? "Проверяем…" : updateState === "installing" ? "Устанавливаем…" : "Проверить"}</button>}</div>
    {message ? <p className="desktop-message" role="status"><WarningCircle size={16} /> {message}</p> : null}
  </section></>;
}
