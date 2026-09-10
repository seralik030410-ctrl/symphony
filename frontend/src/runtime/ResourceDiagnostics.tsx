import { CheckCircle, WarningCircle } from "@phosphor-icons/react";

export type ResourceDiagnosticSnapshot = {
  groups: Array<{ name: string; capacity_units: number; used_units: number; available_units: number; enabled: boolean }>;
  requests_by_status: Record<string, number>;
  restart_recovery: Record<string, number>;
  dependencies: Record<string, boolean | string | number | null>;
  redaction: string;
};

/** Compact, no-secret diagnostic card for Settings or a degraded-mode screen. */
export function ResourceDiagnostics({ snapshot, error }: { snapshot?: ResourceDiagnosticSnapshot | null; error?: string }) {
  if (error) return <section className="settings-card diagnostics-card"><p role="alert"><WarningCircle size={17} /> {error}</p></section>;
  if (!snapshot) return <section className="settings-card diagnostics-card"><p role="status">Проверяем ресурсы runtime…</p></section>;
  return <section className="settings-card diagnostics-card" aria-label="Диагностика ресурсов">
    <h3>Ресурсы runtime</h3>
    <ul>{snapshot.groups.map(group => <li key={group.name}><strong>{group.name}</strong><span>{group.enabled ? <CheckCircle size={16} /> : <WarningCircle size={16} />} {group.used_units}/{group.capacity_units} занято · {group.available_units} доступно</span></li>)}</ul>
    <p>Очередь: {Object.entries(snapshot.requests_by_status).map(([name, count]) => `${name}: ${count}`).join(" · ") || "пуста"}</p>
    <p>{snapshot.redaction}</p>
  </section>;
}
