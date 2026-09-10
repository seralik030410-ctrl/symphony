import { previewPath } from "../chat/preview";

export type WorkspaceTab = { id: string; kind: "new" | "files" | "preview" | "file" | "changes" | "artifact" | "office"; title: string; path?: string };
export type OpenWorkspace = { nonce: number; kind: WorkspaceTab["kind"]; path?: string };
export type WorkspaceState = { tabs: WorkspaceTab[]; activeId: string };
export const emptyWorkspace = (): WorkspaceState => ({ tabs: [{ id: "new", kind: "new", title: "Новая вкладка" }], activeId: "new" });

export function isOfficePath(path: string | undefined): boolean {
  if (!path) return false;
  return /\.(docx|xlsx|xlsm|xltx|pptx|pdf)$/i.test(path);
}

export function openTab(state: WorkspaceState, request: OpenWorkspace): WorkspaceState {
  const effectiveKind = request.kind === "file" && isOfficePath(request.path) ? "office" : request.kind;
  const id = effectiveKind === "new" ? `new:${request.nonce}` : `${effectiveKind}:${request.path ?? ""}`;
  if (state.tabs.some(tab => tab.id === id)) return { ...state, activeId: id };
  const title = effectiveKind === "new" ? "Новая вкладка" : effectiveKind === "files" ? "Файлы проекта" : effectiveKind === "artifact" ? "Документ" : effectiveKind === "changes" ? "Изменения" : effectiveKind === "preview" ? "Preview" : effectiveKind === "office" ? (request.path?.split("/").at(-1) ?? "Office") : request.path?.split("/").at(-1) ?? "Файл";
  const tab: WorkspaceTab = { id, kind: effectiveKind, title, path: request.path };
  const active = state.tabs.find(item => item.id === state.activeId);
  const tabs = active?.kind === "new" && effectiveKind !== "new"
    ? state.tabs.map(item => item.id === active.id ? tab : item) : [...state.tabs, tab];
  return { tabs: tabs.slice(-20), activeId: id };
}

export function closeTab(state: WorkspaceState, id: string): WorkspaceState {
  const index = state.tabs.findIndex(tab => tab.id === id);
  const tabs = state.tabs.filter(tab => tab.id !== id);
  if (!tabs.length) return emptyWorkspace();
  return { tabs, activeId: state.activeId === id ? tabs[Math.max(0, index - 1)].id : state.activeId };
}

export function restoreWorkspace(raw: string | null, sessionId: string, origin: string): WorkspaceState {
  try {
    const value = JSON.parse(raw ?? "null") as WorkspaceState;
    const tabs = value.tabs.filter(tab => typeof tab.id === "string" && typeof tab.title === "string" && (
      tab.kind === "new" || tab.kind === "files" || tab.kind === "changes" ||
      (tab.kind === "artifact" && typeof tab.path === "string" && /^[a-f0-9]{32}$/.test(tab.path)) ||
      (tab.kind === "office" && typeof tab.path === "string" && !/[:\\]|(^|\/)\.\.(\/|$)|^\//.test(tab.path)) ||
      (tab.kind === "file" && typeof tab.path === "string" && !/[:\\]|(^|\/)\.\.(\/|$)|^\//.test(tab.path)) ||
      (tab.kind === "preview" && typeof tab.path === "string" && previewPath(tab.path, sessionId, origin))
    )).slice(-20);
    if (!tabs.length) return emptyWorkspace();
    return { tabs, activeId: tabs.some(tab => tab.id === value.activeId) ? value.activeId : tabs[0].id };
  } catch { return emptyWorkspace(); }
}

export function diffRows(diff: string) {
  let old = 0, next = 0;
  return diff.split("\n").filter(line => !line.startsWith("--- ") && !line.startsWith("+++ ")).map(line => {
    const header = /^@@ -(\d+)(?:,\d+)? \+(\d+)/.exec(line);
    if (header) { old = Number(header[1]); next = Number(header[2]); return { kind: "hunk", text: line, old: "", next: "" }; }
    if (line.startsWith("+")) return { kind: "add", text: line.slice(1), old: "", next: String(next++) };
    if (line.startsWith("-")) return { kind: "remove", text: line.slice(1), old: String(old++), next: "" };
    return { kind: "context", text: line.slice(1), old: String(old++), next: String(next++) };
  });
}
