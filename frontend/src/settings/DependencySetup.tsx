import { ArrowSquareOut, DownloadSimple } from "@phosphor-icons/react";
import { useState, type MouseEvent } from "react";
import { hasDesktopBridge, openExternal } from "../desktop";

export function DependencySetup() {
  const [error, setError] = useState("");
  function follow(event: MouseEvent<HTMLAnchorElement>) {
    if (!hasDesktopBridge()) return;
    event.preventDefault();
    void openExternal(event.currentTarget.href).catch(cause => setError(String(cause)));
  }
  return <details className="dependency-setup">
    <summary>Установка зависимостей</summary>
    <p>Для обычного чата Docker не нужен. Локальные модели работают через Ollama, а выполнение кода и обработка документов — в Docker runtime.</p>
    <ol>
      <li>Установите и запустите <a href="https://www.docker.com/products/docker-desktop/" target="_blank" rel="noreferrer" onClick={follow}>Docker Desktop <ArrowSquareOut size={13} /></a>. В Windows нужны Linux-контейнеры.</li>
      <li><a href="/api/setup/runtime-kit" className="dependency-download"><DownloadSimple size={16} /> Скачайте набор runtime 6.0</a> и распакуйте ZIP целиком в отдельную папку. Исходники Symphony, Python и Node.js на компьютере не нужны.</li>
      <li>Windows: откройте <code>INSTALL.bat</code>. macOS: в Терминале из распакованной папки выполните <code>bash INSTALL.sh</code>. Прочитайте условия и подтвердите сборку.</li>
      <li>Вернитесь в этот раздел настроек, чтобы обновить диагностику.</li>
    </ol>
    <p>Первая сборка скачивает несколько ГБ из Docker Hub, Debian и PyPI. Желательно иметь не менее 12 ГБ свободного места. Набор обновляет только образ runtime, не удаляя чаты, модели, тома и кэш.</p>
    <p>Для локального чата отдельно установите <a href="https://ollama.com/download" target="_blank" rel="noreferrer" onClick={follow}>Ollama <ArrowSquareOut size={13} /></a> и скачайте модель. При использовании API Ollama не требуется.</p>
    {error ? <p role="alert">Не удалось открыть ссылку: {error}</p> : null}
  </details>;
}
