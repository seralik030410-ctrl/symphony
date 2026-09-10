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
  ProviderProfile, ProviderHealth, ProviderCapability,
  MediaAsset, MediaJob, MediaJobEvent,
  VoiceSession, VoiceSettings, AttachmentUse, VisionModelLimits, VisionMode,
  AgentTask, AgentSettings, AgentCommand, AgentCompletionReceipt, AgentHeartbeatWatch, AgentHeartbeatEvent,
  HistorySearchResult, ResourceSettings, ResourceDiagnostics,
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
  agentSettings: () => request<AgentSettings>("/agents/settings"),
  updateAgentSettings: (value: Pick<AgentSettings, "enabled" | "profile" | "overrides" | "lazy_tools_enabled" | "role_routes">) => request<AgentSettings>("/agents/settings", { method: "PUT", body: JSON.stringify(value) }),
  agentTaskTree: (turnId: string) => request<AgentTask[]>(`/agents/turns/${turnId}/tree`),
  cancelAgentTask: (taskId: string) => request<{ cancelled_task_ids: string[] }>(`/agents/tasks/${taskId}/cancel`, { method: "POST" }),
  commandAgentTask: (taskId: string, value: { type: "steer"; message: string } | { type: "stop"; subtree: boolean }) =>
    request<AgentCommand>(`/agents/tasks/${taskId}/commands`, { method: "POST", body: JSON.stringify(value) }),
  agentTaskCommands: (taskId: string, after = 0) => request<AgentCommand[]>(`/agents/tasks/${taskId}/commands?after=${after}`),
  agentBackground: (sessionId: string) => request<{ tasks: AgentTask[]; receipts: AgentCompletionReceipt[]; watches: AgentHeartbeatWatch[]; heartbeat_events: AgentHeartbeatEvent[] }>(`/agents/sessions/${sessionId}/background`),
  acknowledgeAgentReceipt: (receiptId: string) => request<AgentCompletionReceipt>(`/agents/receipts/${receiptId}/acknowledge`, { method: "POST" }),
  acknowledgeAgentHeartbeatEvent: (eventId: string) => request<AgentHeartbeatEvent>(`/agents/heartbeat-events/${eventId}/acknowledge`, { method: "POST" }),
  resourceSettings: () => request<ResourceSettings>("/resources/settings"),
  updateResourceSettings: (profile: ResourceSettings["profile"], custom_limits: Record<string, unknown> = {}) => request<ResourceSettings>("/resources/settings", { method: "PUT", body: JSON.stringify({ profile, custom_limits }) }),
  resourceDiagnostics: () => request<ResourceDiagnostics>("/resources/diagnostics"),
  voiceSettings: (id: string) => request<VoiceSettings>(`/voice/sessions/${id}/settings`),
  updateVoiceSettings: (id: string, value: Partial<Omit<VoiceSettings, "session_id" | "updated_at">>) => request<VoiceSettings>(`/voice/sessions/${id}/settings`, { method: "PUT", body: JSON.stringify(value) }),
  latestVoiceSession: (id: string) => request<VoiceSession | null>(`/voice/sessions/${id}/latest`),
  listMediaAssets: (id: string, deleted = false) => request<MediaAsset[]>(`/sessions/${id}/media/assets?deleted=${deleted}`),
  uploadMediaAsset: (id: string, value: { filename: string; mime_type: string; content_base64: string }) =>
    request<MediaAsset>(`/sessions/${id}/media/assets`, { method: "POST", body: JSON.stringify(value) }),
  trashMediaAsset: (id: string, asset: string) => request<{ id: string; recoverable: boolean }>(`/sessions/${id}/media/assets/${asset}`, { method: "DELETE" }),
  restoreMediaAsset: (id: string, asset: string) => request<MediaAsset>(`/sessions/${id}/media/assets/${asset}/restore`, { method: "POST" }),
  purgeMediaAsset: (id: string, asset: string) => request<{ id: string; recoverable: boolean }>(`/sessions/${id}/media/assets/${asset}/permanent`, { method: "DELETE" }),
  listMediaJobs: (id: string) => request<MediaJob[]>(`/sessions/${id}/media/jobs`),
  createMediaJob: (id: string, asset: string) => request<MediaJob>(`/sessions/${id}/media/jobs`, { method: "POST", body: JSON.stringify({ kind: "media.preview", input: { asset_id: asset } }) }),
  cancelMediaJob: (id: string, job: string) => request<MediaJob>(`/sessions/${id}/media/jobs/${job}/cancel`, { method: "POST" }),
  retryMediaJob: (id: string, job: string) => request<MediaJob>(`/sessions/${id}/media/jobs/${job}/retry`, { method: "POST" }),
  mediaJobEvents: (id: string, job: string, after = 0) => request<MediaJobEvent[]>(`/sessions/${id}/media/jobs/${job}/events?after=${after}`),
  listProviderProfiles: () => request<ProviderProfile[]>("/providers"),
  createProviderProfile: (value: {
    provider_type: ProviderProfile["provider_type"]; title: string; base_url: string; default_model: string;
    enabled: boolean; is_local: boolean; secret?: string; secret_storage?: "memory" | "desktop"; secret_env_var?: string;
    capabilities?: Partial<Record<ProviderCapability, boolean>>;
  }) => request<ProviderProfile>("/providers", { method: "POST", body: JSON.stringify(value) }),
  updateProviderProfile: (id: string, value: Partial<Pick<ProviderProfile, "title" | "base_url" | "default_model" | "enabled" | "is_local">> & {
    secret?: string; secret_storage?: "memory" | "desktop"; secret_env_var?: string; clear_secret?: boolean; capabilities?: Partial<Record<ProviderCapability, boolean>>;
  }) => request<ProviderProfile>(`/providers/${id}`, { method: "PATCH", body: JSON.stringify(value) }),
  deleteProviderProfile: (id: string) => request<void>(`/providers/${id}`, { method: "DELETE" }),
  checkProviderProfile: (id: string) => request<ProviderHealth>(`/providers/${id}/health`, { method: "POST" }),
  providerCapabilities: (id: string, model: string) => request<{ profile_id: string; model: string; capabilities: Record<ProviderCapability, boolean> }>(`/providers/${id}/capabilities?model=${encodeURIComponent(model)}`),
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
  updateCapabilities: (id: string, value: Partial<Pick<ModelProfile["capabilities"], "vision" | "max_context" | keyof VisionModelLimits>>) => request<ModelProfile["capabilities"]>(`/sessions/${id}/model-capabilities`, { method: "PUT", body: JSON.stringify(value) }),
  getMemory: (id: string) => request<MemorySnapshot>(`/sessions/${id}/memory`),
  getModelLimits: (id: string) => request<{ max_context: number; provider: string; model: string }>(`/sessions/${id}/model-limits`).catch(error => {
    if (error instanceof ApiError && error.status === 404) throw new Error("На этом порту работает предыдущая версия сервера. Перезапустите FinCtrl, затем повторите проверку.");
    throw error;
  }),
  updateMemory: (id: string, value: Pick<MemorySnapshot, "facts" | "decisions" | "open_tasks" | "artifact_index">) => request<MemorySnapshot>(`/sessions/${id}/memory`, { method: "PUT", body: JSON.stringify(value) }),
  createMemorySnapshot: (id: string) => request<MemorySnapshot>(`/sessions/${id}/memory/snapshot`, { method: "POST" }),
  clearMemory: (id: string) => request<void>(`/sessions/${id}/memory`, { method: "DELETE" }),
  listSessions: () => request<SessionSummary[]>("/sessions"),
  searchHistory: (query: string, limit = 20) => request<{ query: string; results: HistorySearchResult[] }>(`/search/history?q=${encodeURIComponent(query)}&limit=${limit}`),
  createSession: () =>
    request<Session>("/sessions", {
      method: "POST",
      body: JSON.stringify({ title: "Новый чат" }),
    }),
  getSession: (id: string) => request<Session>(`/sessions/${id}`),
  deleteSession: (id: string) => request<{ id: string; recoverable: boolean }>(`/sessions/${id}`, { method: "DELETE" }),
  restoreSession: (id: string) => request<Session>(`/sessions/${id}/restore`, { method: "POST" }),
  listTrash: () => request<Array<{ id: string; title: string; deleted_at: string }>>("/trash"),
  emptyTrash: () => request<{ deleted: number; ids: string[]; storage_warnings: Array<{ id: string; message: string }> }>("/trash", { method: "DELETE" }),
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
    changes: Partial<Pick<Session, "provider" | "provider_profile_id" | "model" | "title" | "policy_profile" | "context_window" | "max_output">>,
  ) =>
    request<Session>(`/sessions/${id}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),
  createTurn: (sessionId: string, content: string, attachment_ids: string[] = [], image_mode: VisionMode = "vision", attachment_uses: AttachmentUse[] = []) =>
    request<TurnCreated>(`/sessions/${sessionId}/turns`, {
      method: "POST",
      body: JSON.stringify({ content, attachment_ids, image_mode: image_mode === "auto" ? "vision" : image_mode, attachment_uses }),
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
  "vision.frame_selected",
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
  "media.job_queued",
  "media.job_state_changed",
  "media.job_progress",
  "media.output_created",
  "media.job_failed",
  "media.job_cancelled",
  "voice.user_committed",
  "voice.state_changed",
  "voice.tts_failed",
  "voice.audio_save_failed",
  "voice.interrupted",
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
