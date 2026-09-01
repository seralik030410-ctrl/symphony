import type {
  ModelProfile,
  Session,
  SessionSummary,
  Turn,
  TurnCreated,
  TurnEvent,
  SkillDetail, SkillMatch, SkillMode, SkillSummary,
  Attachment, IndexedSource, MemorySnapshot,
  ResearchSettings, ResearchSource, DiagnosticReport,
} from "./types";

const API_ROOT = "/api";

class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      detail = response.statusText || detail;
    }
    throw new ApiError(typeof detail === "string" ? detail : JSON.stringify(detail), response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  researchSettings: (id: string) => request<ResearchSettings>(`/sessions/${id}/research`),
  updateResearchSettings: (id: string, value: Pick<ResearchSettings, "enabled" | "allowed_domains">) => request<ResearchSettings>(`/sessions/${id}/research`, { method: "PUT", body: JSON.stringify(value) }),
  researchSources: (id: string, turn?: string) => request<ResearchSource[]>(`/sessions/${id}/research/sources${turn ? `?turn_id=${encodeURIComponent(turn)}` : ""}`),
  diagnostics: () => request<DiagnosticReport>("/diagnostics"),
  listArtifacts: (id: string) => request<ArtifactSummary[]>(`/sessions/${id}/artifacts`),
  getArtifact: (id: string, artifact: string, version?: number) => request<ArtifactDetail>(`/sessions/${id}/artifacts/${artifact}${version ? `/versions/${version}` : ""}`),
  uploadInput: (id: string, filename: string, content_base64: string) => request<Attachment & { indexed: IndexedSource | null }>(`/sessions/${id}/inputs`, { method: "POST", body: JSON.stringify({ filename, content_base64 }) }),
  listPendingInputs: (id: string) => request<Attachment[]>(`/sessions/${id}/inputs`).catch(error => {
    // Keep existing chats usable while a newly-built UI meets an older process.
    if (error instanceof ApiError && [404, 405].includes(error.status)) return [];
    throw error;
  }),
  deleteInput: (id: string, attachment: string) => request<void>(`/sessions/${id}/inputs/${attachment}`, { method: "DELETE" }),
  listSources: (id: string) => request<{ files: IndexedSource[]; matches: unknown[] }>(`/sessions/${id}/sources`),
  removeSource: (id: string, path: string) => request<void>(`/sessions/${id}/sources?path=${encodeURIComponent(path)}`, { method: "DELETE" }),
  indexSource: (id: string, path: string) => request<IndexedSource>(`/sessions/${id}/sources/index`, { method: "POST", body: JSON.stringify({ path }) }),
  memoryVersions: (id: string) => request<MemorySnapshot[]>(`/sessions/${id}/memory/versions`),
  modelCapabilities: (id: string) => request<ModelProfile["capabilities"]>(`/sessions/${id}/model-capabilities`),
  updateCapabilities: (id: string, value: { vision?: boolean; max_context?: number }) => request<ModelProfile["capabilities"]>(`/sessions/${id}/model-capabilities`, { method: "PUT", body: JSON.stringify(value) }),
  getMemory: (id: string) => request<MemorySnapshot>(`/sessions/${id}/memory`),
  getModelLimits: (id: string) => request<{ max_context: number; provider: string; model: string }>(`/sessions/${id}/model-limits`).catch(error => {
    if (error instanceof ApiError && error.status === 404) throw new Error("На этом порту работает предыдущая версия сервера. Перезапустите Symphony, затем повторите проверку.");
    throw error;
  }),
  updateMemory: (id: string, value: Pick<MemorySnapshot, "facts" | "decisions" | "open_tasks" | "artifact_index">) => request<MemorySnapshot>(`/sessions/${id}/memory`, { method: "PUT", body: JSON.stringify(value) }),
  createMemorySnapshot: (id: string) => request<MemorySnapshot>(`/sessions/${id}/memory/snapshot`, { method: "POST" }),
  clearMemory: (id: string) => request<void>(`/sessions/${id}/memory`, { method: "DELETE" }),
  listSessions: () => request<SessionSummary[]>("/sessions"),
  createSession: () =>
    request<Session>("/sessions", {
      method: "POST",
      body: JSON.stringify({ title: "Новый чат" }),
    }),
  getSession: (id: string) => request<Session>(`/sessions/${id}`),
  deleteSession: (id: string) => request<{ id: string; recoverable: boolean }>(`/sessions/${id}`, { method: "DELETE" }),
  restoreSession: (id: string) => request<Session>(`/sessions/${id}/restore`, { method: "POST" }),
  listTrash: () => request<Array<{ id: string; title: string; deleted_at: string }>>("/trash"),
  projectTree: (id: string) => request<{ entries: Array<{ path: string; type: "directory" | "file"; size: number | null }> }>(`/sessions/${id}/tree`),
  projectFile: (id: string, path: string) => request<ProjectFile>(`/sessions/${id}/files?path=${encodeURIComponent(path)}`),
  projectChanges: (id: string, snapshot?: string) => request<ProjectChanges>(`/sessions/${id}/changes${snapshot ? `?snapshot_id=${encodeURIComponent(snapshot)}` : ""}`),
  projectSnapshots: (id: string) => request<ProjectSnapshot[]>(`/sessions/${id}/snapshots`),
  listSkills: () => request<SkillSummary[]>("/skills"),
  listSkillTrash: () => request<SkillSummary[]>("/skills/trash"),
  getSkill: (id: string) => request<SkillDetail>(`/skills/${id}`),
  updateSkill: (id: string, changes: { mode?: SkillMode; priority?: number; skill_md?: string }) => request<SkillDetail>(`/skills/${id}`, { method: "PATCH", body: JSON.stringify(changes) }),
  installSkill: (payload: { source_type: "zip" | "folder" | "git"; source?: string; zip_base64?: string; filename?: string; mode?: SkillMode }) => request<SkillDetail>("/skills/install", { method: "POST", body: JSON.stringify(payload) }),
  validateSkill: (skill_md: string) => request<{ valid: boolean; name: string; slug: string; description: string }>("/skills/validate", { method: "POST", body: JSON.stringify({ skill_md }) }),
  testSkillPrompt: (prompt: string) => request<SkillMatch>("/skills/test", { method: "POST", body: JSON.stringify({ prompt }) }),
  skillResource: (id: string, path: string) => request<{ path: string; content: string; truncated: boolean }>(`/skills/${id}/resource?path=${encodeURIComponent(path)}`),
  trashSkill: (id: string) => request<{ id: string; recoverable: boolean }>(`/skills/${id}`, { method: "DELETE" }),
  restoreSkill: (id: string) => request<SkillDetail>(`/skills/${id}/restore`, { method: "POST" }),
  updateSession: (
    id: string,
    changes: Partial<Pick<Session, "provider" | "model" | "title" | "policy_profile" | "context_window" | "max_output">>,
  ) =>
    request<Session>(`/sessions/${id}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),
  createTurn: (sessionId: string, content: string, attachment_ids: string[] = [], image_mode: "vision" | "ocr" = "vision") =>
    request<TurnCreated>(`/sessions/${sessionId}/turns`, {
      method: "POST",
      body: JSON.stringify({ content, attachment_ids, image_mode }),
    }),
  cancelTurn: (turnId: string) =>
    request<Turn>(`/turns/${turnId}/cancel`, { method: "POST" }),
  retryTurn: (turnId: string) =>
    request<TurnCreated>(`/turns/${turnId}/retry`, { method: "POST" }),
  getTurnEvents: (turnId: string, after = 0) =>
    request<TurnEvent[]>(`/turns/${turnId}/events?after=${after}`),
  listModels: () => request<ModelProfile[]>("/models"),
  decideApproval: (approvalId: string, approved: boolean) =>
    request(`/approvals/${approvalId}/decision`, {
      method: "POST",
      body: JSON.stringify({ approved }),
    }),
};

export interface ProjectFile { path: string; content: string; size: number; binary: boolean; truncated: boolean }
export interface ArtifactSummary { id: string; version: number; title: string; format: string; download_url: string; size: number; valid: boolean; turn_id: string; created_at: string }
export interface ArtifactTable { name: string; columns: Array<{ name: string; format: string }>; rows: unknown[][]; formulas: Record<string, string>; total_rows: number; truncated: boolean }
export interface ArtifactDetail extends ArtifactSummary { pages: Array<{ url: string; width: number; height: number }>; tables: ArtifactTable[]; validation: { warnings?: string[]; renderer: string; geometry?: { checked: boolean }; calculation?: { formula_count: number; engine: string }; files: Record<string, { sha256: string }> }; source_url: string; recipe_url: string; validation_url: string }
export interface ProjectSnapshot { id: string; operation: string; created_at: string; turn_id: string }
export interface ProjectChanges {
  snapshot: ProjectSnapshot | null;
  files: Array<{ path: string; status: string; diff: string; additions: number; deletions: number; binary: boolean; truncated: boolean }>;
  truncated: boolean;
}

const EVENT_TYPES = [
  "turn.started",
  "turn.cancel_requested",
  "context.built",
  "context.indexed",
  "context.retrieved",
  "memory.snapshot",
  "memory.started",
  "vision.attached",
  "vision.ocr_completed",
  "research.needed",
  "research.requested",
  "research.received",
  "research.sources",
  "model.started",
  "model.delta",
  "model.reasoning_delta",
  "model.usage",
  "model.completed",
  "model.failed",
  "tool.requested",
  "tool.started",
  "tool.output",
  "tool.completed",
  "tool.failed",
  "tool.cancelled",
  "approval.requested",
  "approval.approved",
  "approval.denied",
  "approval.cancelled",
  "preview.ready",
  "artifact.created",
  "artifact.validated",
  "project.snapshot",
  "skill.cataloged",
  "skill.selected",
  "skill.read",
  "skill.resource_read",
  "skill.script_executed",
  "tool.output_delta",
  "file.changed",
  "turn.completed",
  "turn.failed",
  "turn.cancelled",
  "turn.interrupted",
];

export function subscribeToTurn(
  turnId: string,
  after: number,
  onEvent: (event: TurnEvent) => void,
  onConnectionError: () => void,
): EventSource {
  const source = new EventSource(`${API_ROOT}/turns/${turnId}/events?stream=true&after=${after}`);
  const listener = (message: MessageEvent<string>) => {
    onEvent(JSON.parse(message.data) as TurnEvent);
  };
  EVENT_TYPES.forEach((type) => source.addEventListener(type, listener as EventListener));
  source.onerror = onConnectionError;
  return source;
}
