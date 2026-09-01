export function previewPath(url: string, sessionId: string, origin: string): string | null {
  try {
    const parsed = new URL(url, origin);
    const prefix = `/api/sessions/${sessionId}/preview/`;
    if (parsed.origin !== origin || !parsed.pathname.startsWith(prefix)) return null;
    return parsed.pathname + parsed.search + parsed.hash;
  } catch { return null; }
}
