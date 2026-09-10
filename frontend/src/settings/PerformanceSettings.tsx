import { CheckCircle, Gauge, WarningCircle } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

export type PerformanceProfile = "conservative" | "balanced" | "maximum" | "custom";

export type ResourceSettingsSnapshot = {
  profile: PerformanceProfile;
  effective_limits: { max_queued_requests: number; max_active_leases: number; lease_ttl_seconds: number; groups: Record<string, number> };
};

/**
 * Presentation-only settings panel. The host supplies authenticated API calls
 * so this component stays usable in desktop, web, and offline diagnostics.
 */
export function PerformanceSettings({ load, save }: {
  load: () => Promise<ResourceSettingsSnapshot>;
  save: (profile: PerformanceProfile, customLimits?: Record<string, unknown>) => Promise<ResourceSettingsSnapshot>;
}) {
  const [settings, setSettings] = useState<ResourceSettingsSnapshot | null>(null);
  const [pending, setPending] = useState<PerformanceProfile>("balanced");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [customLimits, setCustomLimits] = useState("");

  useEffect(() => { void load().then(value => { setSettings(value); setPending(value.profile); }).catch(cause => setError(cause instanceof Error ? cause.message : "Диагностика производительности недоступна")); }, [load]);
  async function apply() {
    if (busy) return;
    setBusy(true); setError("");
    try {
      const custom = pending === "custom" ? JSON.parse(customLimits) as Record<string, unknown> : undefined;
      const value = await save(pending, custom); setSettings(value);
    }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Профиль не сохранён"); }
    finally { setBusy(false); }
  }

  return <section className="general-settings" aria-labelledby="performance-heading">
    <header className="settings-content-header"><div><h1 id="performance-heading">Производительность</h1><p>Голос и активный чат получают GPU раньше фоновой генерации.</p></div></header>
    {error ? <p className="settings-alert" role="alert"><WarningCircle size={17} /> {error}</p> : null}
    <section className="settings-card"><div className="settings-row"><div><strong>Профиль ресурсов</strong><small>Conservative оставляет больше запаса для системы; Balanced подходит для одной GPU; Maximum разрешает больше параллельной работы, если оборудование справляется.</small></div>
      <select aria-label="Профиль ресурсов" value={pending} disabled={busy} onChange={event => setPending(event.target.value as PerformanceProfile)}>
        <option value="conservative">Conservative</option><option value="balanced">Balanced</option><option value="maximum">Maximum</option><option value="custom">Custom</option>
      </select></div>
      <div className="settings-row"><div><strong>Очередь медиа</strong><small>Новые image/video jobs ставятся на паузу, пока есть ожидающий или активный голос, чат либо распознавание речи. Уже начатая генерация не прерывается автоматически.</small></div><span><Gauge size={17} /> Приоритет включён</span></div>
      <div className="settings-row"><div><strong>Lease recovery</strong><small>После перезапуска активные GPU-lease освобождаются; безопасные media jobs возвращаются в очередь, интерактивные запросы завершаются честно.</small></div><span>{settings ? <CheckCircle size={17} /> : null} {settings ? `${settings.effective_limits.lease_ttl_seconds} с` : "Проверяем…"}</span></div>
    </section>
    {pending === "custom" ? <label className="settings-card" style={{ display: "grid", gap: 8, padding: 18 }}><strong>Custom limits (JSON)</strong><small>Укажите max_queued_requests, max_active_leases, lease_ttl_seconds и groups, например gpu:local. Секреты здесь не допускаются.</small><textarea aria-label="Custom resource limits JSON" value={customLimits} onChange={event => setCustomLimits(event.target.value)} placeholder={'{"max_queued_requests":25000,"max_active_leases":2048,"lease_ttl_seconds":90,"groups":{"gpu:local":100,"cpu:local":200}}'} /></label> : null}
    <button className="settings-primary" disabled={busy || !settings || pending === settings.profile} onClick={() => void apply()}>{busy ? "Сохраняем…" : "Применить профиль"}</button>
  </section>;
}
