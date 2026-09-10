import { CheckCircle, Cloud, Plus, Pulse, Trash, WarningCircle } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { ProviderCapability, ProviderProfile } from "../types";
import { desktopInvoke, hasDesktopBridge } from "../desktop";

const capabilityLabels: Array<[ProviderCapability, string]> = [
  ["text.chat", "Текстовый чат"], ["vision.images", "Изображения"],
  ["vision.live_frames", "Live Vision"], ["audio.transcription", "Распознавание речи"],
  ["audio.synthesis", "Синтез речи"], ["audio.realtime", "Realtime audio"],
  ["media.image_generation", "Генерация изображений"], ["media.video_generation", "Генерация видео"],
];

type Form = {
  provider_type: ProviderProfile["provider_type"]; title: string; base_url: string; default_model: string;
  enabled: boolean; is_local: boolean; secret: string; secretEnvVar: string; capabilities: Record<ProviderCapability, boolean>;
};

const blank = (): Form => ({
  provider_type: "openai_compatible", title: "", base_url: "http://127.0.0.1:1234/v1", default_model: "",
  enabled: true, is_local: false, secret: "", secretEnvVar: "",
  capabilities: Object.fromEntries(capabilityLabels.map(([name]) => [name, name === "text.chat"])) as Record<ProviderCapability, boolean>,
});

export function ProvidersSettings({ onChanged }: { onChanged?: () => void } = {}) {
  const [profiles, setProfiles] = useState<ProviderProfile[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [form, setForm] = useState<Form>(blank);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function refresh(preferred?: string) {
    const values = await api.listProviderProfiles();
    setProfiles(values);
    setSelected(currentId => preferred ?? (values.some(item => item.id === currentId) ? currentId : values[0]?.id ?? null));
  }
  useEffect(() => { void refresh().catch(cause => setError((cause as Error).message)); }, []);
  useEffect(() => {
    if (creating || !selected) return;
    const profile = profiles.find(item => item.id === selected);
    if (!profile) return;
    setForm(current => ({ ...current, provider_type: profile.provider_type, title: profile.title, base_url: profile.base_url,
      default_model: profile.default_model, enabled: profile.enabled, is_local: profile.is_local, secret: "", secretEnvVar: "" }));
    api.providerCapabilities(profile.id, profile.default_model)
      .then(value => setForm(current => ({ ...current, capabilities: value.capabilities })))
      .catch(cause => setError((cause as Error).message));
  }, [selected, profiles, creating]);

  const current = profiles.find(item => item.id === selected);
  function field<K extends keyof Form>(key: K, value: Form[K]) { setForm(previous => ({ ...previous, [key]: value })); }

  async function save() {
    if (busy || !form.title.trim() || !form.default_model.trim()) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const secretValue = form.secret.trim();
      const { secretEnvVar, ...fields } = form;
      const payload = { ...fields, secret: hasDesktopBridge() ? secretValue || undefined : undefined,
        secret_storage: hasDesktopBridge() ? "desktop" as const : "memory" as const,
        secret_env_var: !hasDesktopBridge() ? secretEnvVar.trim() || undefined : undefined };
      const value = creating
        ? await api.createProviderProfile(payload)
        : await api.updateProviderProfile(selected!, payload);
      if (secretValue && hasDesktopBridge() && value.secret.reference_id) {
        try {
          await desktopInvoke("set_provider_secret", { referenceId: value.secret.reference_id, value: secretValue });
        } catch (cause) {
          await api.updateProviderProfile(value.id, { clear_secret: true }).catch(() => undefined);
          throw cause;
        }
      }
      setCreating(false); setForm(previous => ({ ...previous, secret: "" }));
      await refresh(value.id); setSelected(value.id); setMessage("Профиль провайдера сохранён.");
      onChanged?.();
    } catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }

  async function health() {
    if (!selected || busy) return;
    setBusy(true); setError("");
    try { const value = await api.checkProviderProfile(selected); setMessage(value.message); await refresh(selected); }
    catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }

  async function remove() {
    if (!selected || busy) return;
    setBusy(true); setError("");
    try { const referenceId = current?.secret.reference_id; await api.deleteProviderProfile(selected); if (referenceId && hasDesktopBridge()) await desktopInvoke("delete_provider_secret", { referenceId }); setSelected(null); await refresh(); onChanged?.(); setMessage("Профиль удалён."); }
    catch (cause) { setError((cause as Error).message); }
    finally { setBusy(false); }
  }

  return <section className="providers-settings">
    <header className="settings-content-header"><div><h1>Провайдеры</h1><p>Локальные и API-профили для текста, голоса, Vision и генерации.</p></div>
      <button className="text-button" onClick={() => { setCreating(true); setSelected(null); setForm(blank()); setMessage(""); }}><Plus size={17} /> Новый профиль</button></header>
    {error ? <div className="settings-alert" role="alert"><WarningCircle size={17} /><span>{error}</span></div> : null}
    {message ? <div className="settings-alert settings-success" role="status"><CheckCircle size={17} /><span>{message}</span></div> : null}
    <div className="providers-layout">
      <aside className="provider-index"><div className="skills-count">{profiles.length} профиля</div><nav>
        {profiles.map(profile => <button key={profile.id} className={profile.id === selected ? "selected" : ""} onClick={() => { setCreating(false); setSelected(profile.id); setMessage(""); }}>
          <Cloud size={17} /><span><strong>{profile.title}</strong><small>{profile.enabled ? profile.default_model : "Выключен"}</small></span>
        </button>)}
      </nav></aside>
      <div className="provider-editor">
        <section className="settings-card provider-form">
          <div className="provider-fields">
            <label><span>Тип</span><select value={form.provider_type} disabled={!creating || busy} onChange={event => field("provider_type", event.target.value as Form["provider_type"])}><option value="ollama">Ollama</option><option value="openai_compatible">OpenAI-compatible</option></select></label>
            <label><span>Название</span><input value={form.title} disabled={busy} onChange={event => field("title", event.target.value)} /></label>
            <label className="wide"><span>Base URL</span><input value={form.base_url} disabled={busy} onChange={event => field("base_url", event.target.value)} /></label>
            <label><span>Модель по умолчанию</span><input value={form.default_model} disabled={busy} onChange={event => field("default_model", event.target.value)} /></label>
            {hasDesktopBridge() ? <label><span>Новый API-ключ</span><input type="password" autoComplete="off" value={form.secret} disabled={busy || form.provider_type === "ollama"} placeholder={current?.secret.configured ? "•••••••• (сохранён)" : "Необязательно"} onChange={event => field("secret", event.target.value)} /></label>
              : <label><span>Переменная окружения с ключом</span><input value={form.secretEnvVar} disabled={busy || form.provider_type === "ollama"} placeholder="FINCTRL_PROVIDER_API_KEY" onChange={event => field("secretEnvVar", event.target.value.toUpperCase())} /></label>}
          </div>
          <div className="provider-switches"><label><input type="checkbox" checked={form.enabled} onChange={event => field("enabled", event.target.checked)} /> Профиль включён</label><label><input type="checkbox" checked={form.is_local} onChange={event => field("is_local", event.target.checked)} /> Локальный endpoint</label></div>
        </section>
        <h2>Возможности модели</h2><section className="settings-card capability-grid">{capabilityLabels.map(([name, label]) => <label key={name}><input type="checkbox" checked={Boolean(form.capabilities[name])} onChange={event => field("capabilities", { ...form.capabilities, [name]: event.target.checked })} /><span>{label}</span><code>{name}</code></label>)}</section>
        <div className="provider-actions"><button className="settings-primary" disabled={busy || !form.title.trim() || !form.default_model.trim()} onClick={() => void save()}>{busy ? "Сохраняем…" : "Сохранить"}</button>{!creating && current ? <button className="text-button" disabled={busy || !current.enabled} onClick={() => void health()}><Pulse size={17} /> Проверить соединение</button> : null}{current && !current.id.startsWith("builtin-") ? <button className="danger-text" disabled={busy} onClick={() => void remove()}><Trash size={17} /> Удалить</button> : null}</div>
      </div>
    </div>
  </section>;
}
