import { CheckCircle, DownloadSimple, WarningCircle } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { DiagnosticReport } from "../types";
import { DependencySetup } from "./DependencySetup";

export function DiagnosticsSettings() {
  const [report, setReport] = useState<DiagnosticReport | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { api.diagnostics().then(setReport).catch(cause => setError(cause instanceof Error ? cause.message : "Диагностика недоступна")); }, []);
  return <><h2>Диагностика</h2><section className="settings-card diagnostics-card">
    {error ? <p role="alert"><WarningCircle size={17} /> {error}</p> : report ? <>
      <div className="settings-row"><div><strong>{report.platform} · {report.architecture}</strong><small>Symphony {report.release} · Python {report.python} · SQLite {report.sqlite}</small></div><span>{report.checks.every(item => item.ready) ? <CheckCircle size={17} /> : <WarningCircle size={17} />} {report.checks.filter(item => item.ready).length}/{report.checks.length} готово</span></div>
      <ul>{report.checks.map(item => <li key={item.name}><strong>{item.name}</strong><span>{item.ready ? "Готово" : item.hint}</span></li>)}</ul>
      <p>{report.privacy}</p>
      <a className="settings-primary diagnostics-download" href="/api/diagnostics/bundle"><DownloadSimple size={17} /> Скачать ZIP для проверки</a>
    </> : <p role="status">Проверяем зависимости…</p>}
    <DependencySetup />
  </section></>;
}
