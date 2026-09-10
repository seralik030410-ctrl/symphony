export type TurnStatus =
  | "queued"
  | "preparing"
  | "model_running"
  | "completed"
  | "failed"
  | "cancelled"
  | "interrupted";

export interface Message {
  id: string;
  session_id: string;
  turn_id: string | null;
  role: "user" | "assistant" | "system";
  content: string;
  status: "complete" | "streaming" | "cancelled" | "failed";
  created_at: string;
  updated_at: string;
  attachments?: Attachment[];
}

export interface Attachment {
  id: string;
  filename: string;
  mime_type: string;
  size: number;
  width: number | null;
  height: number | null;
  path: string;
  image_mode?: VisionMode;
  ordinal?: number;
  estimated_tokens?: number;
  provenance?: FrameProvenance;
  snapshot?: Record<string, unknown>;
}

export type VisionMode = "auto" | "vision" | "ocr";
export type VisionCaptureSource = "file" | "clipboard" | "camera" | "screen" | "live";
export type VisionFrameReason = "manual" | "initial" | "change" | "interval";

export interface FrameProvenance {
  source: VisionCaptureSource;
  reason: VisionFrameReason;
  captured_at?: string | null;
  sequence?: number | null;
  device_label?: string | null;
  display_label?: string | null;
  change_score?: number | null;
}

export interface AttachmentUse {
  attachment_id: string;
  image_mode?: Exclude<VisionMode, "auto">;
  provenance: FrameProvenance;
}

export interface VisionModelLimits {
  max_vision_frames: number;
  max_image_bytes: number;
  max_image_width: number;
  max_image_height: number;
  max_image_tokens: number;
  max_vision_tokens: number;
}

export interface IndexedSource {
  id: string; path: string; mime_type: string; size: number; sha256: string; status: "ready" | "failed";
  error: string | null; characters: number; chunk_count: number; created_at: string; updated_at: string;
}

export interface MemorySnapshot {
  id: string | null; session_id: string; version: number; facts: string[]; decisions: string[];
  open_tasks: string[]; artifact_index: string[]; source_message_ids: string[]; created_at: string | null; updated_at: string | null;
  kind?: "empty" | "manual" | "automatic" | "cleared";
  model?: string; input_tokens?: number; output_tokens?: number;
}
export interface ResearchSettings {
  enabled: boolean; allowed_domains: string[]; search_provider: string; search_domain: string;
}
export interface ResearchSource {
  id: string; session_id: string; turn_id: string; url: string; title: string;
  kind: "search_result" | "page"; published_at: string | null; checked_at: string;
  sha256: string; excerpt: string; trust: "untrusted";
}
export interface DiagnosticReport {
  schema_version: number; generated_at: string; application: string; release: string;
  platform: string; architecture: string; python: string; sqlite: string;
  packages: Record<string, string>; checks: Array<{ name: string; ready: boolean; hint: string }>;
  privacy: string; macos_acceptance: string;
}

export interface Turn {
  id: string;
  session_id: string;
  user_message_id: string;
  assistant_message_id: string;
  status: TurnStatus;
  provider: string;
  model: string;
  request_id: string;
  error: string | null;
  cancel_requested: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  last_event_sequence: number;
}

export interface SessionSummary {
  id: string;
  title: string;
  provider: string;
  model: string;
  created_at: string;
  updated_at: string;
  last_message_preview: string;
  active_turn: boolean;
}

export interface Session {
  id: string;
  title: string;
  provider: string;
  provider_profile_id: string | null;
  model: string;
  system_prompt: string;
  context_window: number;
  max_output: number;
  policy_profile: "read_only" | "project_edit" | "build" | "full_manual";
  created_at: string;
  updated_at: string;
  messages: Message[];
  turns: Turn[];
}

export interface TurnEvent {
  id: number;
  turn_id: string;
  session_id: string;
  sequence: number;
  type: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export type AgentTaskStatus = "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
export type AgentRole = "worker" | "orchestrator" | "code" | "research" | "vision" | "media" | "review";
export interface AgentTask {
  id: string; session_id: string; root_turn_id: string; parent_task_id: string | null;
  ordinal: number; depth: number; goal: string; context: Record<string, unknown>;
  provider_profile_id: string | null; model: string; status: AgentTaskStatus;
  permission_profile: Session["policy_profile"]; allowed_tools: string[];
  output_schema: Record<string, unknown> | null;
  result: { summary?: string; changed_files?: string[]; artifacts?: Array<Record<string, unknown>>;
    evidence?: Array<Record<string, unknown>>; usage?: Record<string, number> } | null;
  error: string | null; cancel_requested: boolean; created_at: string;
  started_at: string | null; finished_at: string | null;
  used_steps: number; used_tool_calls: number; used_input_tokens: number; used_output_tokens: number;
  execution_mode: "foreground" | "background"; last_activity_at: string | null;
  activity_phase: string; activity: Record<string, unknown>; stalled_at: string | null;
  role: AgentRole;
}
export interface AgentCommand {
  id: string; task_id: string; sequence: number; type: "steer" | "stop";
  payload: { message?: string; subtree?: boolean }; status: "queued" | "delivered" | "applied" | "rejected";
  rejection_reason: string | null; created_at: string; delivered_at: string | null; applied_at: string | null;
  affected_task_ids?: string[];
}
export interface AgentCompletionReceipt {
  id: string; task_id: string; session_id: string; root_turn_id: string;
  status: "completed" | "failed" | "cancelled" | "interrupted"; created_at: string; acknowledged_at: string | null;
}
export interface AgentHeartbeatWatch {
  id: string; task_id: string; session_id: string; interval_seconds: number;
  status: "active" | "completed"; last_observed_status: AgentTaskStatus | null;
  last_observed_stalled: boolean; next_check_at: string; last_checked_at: string | null;
  created_at: string; completed_at: string | null;
}
export interface AgentHeartbeatEvent {
  id: string; watch_id: string; sequence: number; task_id: string; session_id: string;
  type: "stalled" | "resumed" | "completed" | "failed" | "cancelled" | "interrupted";
  payload: Record<string, unknown>; created_at: string; acknowledged_at: string | null;
}
export interface HistorySearchResult {
  message_id: string; session_id: string; turn_id: string | null;
  role: "user" | "assistant"; session_title: string; snippet: string;
  created_at: string; rank: number;
}
export interface AgentLimits {
  max_concurrent: number; max_depth: number; max_children: number; max_tasks_per_tree: number;
  max_steps: number; max_tool_calls: number; max_input_tokens: number; max_output_tokens: number;
  deadline_seconds: number; stall_warning_seconds: number;
}
export interface AgentSettings {
  enabled: boolean; profile: "conservative" | "balanced" | "maximum" | "custom";
  overrides: Partial<AgentLimits>; effective_limits: AgentLimits; profiles: Record<string, AgentLimits>;
  lazy_tools_enabled: boolean;
  role_routes: Partial<Record<AgentRole, { provider_profile_id: string; model: string }>>;
}

export interface ResourceSettings {
  profile: "conservative" | "balanced" | "maximum" | "custom";
  custom_limits: Record<string, unknown>;
  effective_limits: { max_queued_requests: number; max_active_leases: number; lease_ttl_seconds: number; groups: Record<string, number> };
}
export interface ResourceDiagnostics {
  settings: ResourceSettings;
  groups: Array<{ name: string; capacity_units: number; used_units: number; available_units: number; enabled: boolean }>;
  requests_by_status: Record<string, number>; restart_recovery: Record<string, number>;
  dependencies: Record<string, boolean | string | number | null>; redaction: string;
}

export interface ModelProfile {
  provider: "ollama" | "openai";
  profile_id: string;
  enabled: boolean;
  title: string;
  base_url: string;
  default_model: string;
  models: string[];
  available: boolean;
  health_message: string;
  capabilities: {
    text: boolean;
    vision: boolean;
    native_tools: boolean;
    json_schema: boolean;
    reasoning_stream: boolean;
    vision_live_frames: boolean;
    audio_transcription: boolean;
    audio_synthesis: boolean;
    audio_realtime: boolean;
    media_image_generation: boolean;
    media_video_generation: boolean;
    max_context: number;
    max_output: number;
    max_vision_frames: number;
    max_image_bytes: number;
    max_image_width: number;
    max_image_height: number;
    max_image_tokens: number;
    max_vision_tokens: number;
  };
}

export type ProviderCapability =
  | "text.chat" | "vision.images" | "vision.live_frames"
  | "audio.transcription" | "audio.synthesis" | "audio.realtime"
  | "media.image_generation" | "media.video_generation";

export interface ProviderProfile {
  id: string;
  provider_type: "ollama" | "openai_compatible";
  title: string;
  base_url: string;
  default_model: string;
  enabled: boolean;
  is_local: boolean;
  request_timeout_seconds: number;
  discovery_timeout_seconds: number;
  config: Record<string, unknown>;
  secret: { configured: boolean; reference_id: string | null; masked: string | null };
  last_health_ok: boolean | null;
  last_health_message?: string | null;
  last_checked_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProviderHealth {
  profile_id: string; ready: boolean; message: string; checked_at: string;
}

export interface MediaAsset {
  id: string; session_id: string; kind: "image" | "video" | "audio"; filename: string;
  mime_type: string; size: number; sha256: string; preview_url: string | null; download_url: string;
  width: number | null; height: number | null; duration_seconds: number | null; source: string;
  provider_profile_id: string | null; model: string | null; provenance: Record<string, unknown>;
  created_at: string; updated_at: string; deleted_at: string | null; created?: boolean;
}

export type MediaJobStatus = "queued" | "preparing" | "running" | "paused" | "completed" | "failed" | "cancelled";
export interface MediaJob {
  id: string; session_id: string; turn_id: string | null; kind: "media.preview"; status: MediaJobStatus;
  input: Record<string, unknown>; result_asset_id: string | null; provider_profile_id: string | null;
  attempt: number; retry_of_job_id: string | null; progress: number; cancel_requested: boolean;
  error_code: string | null; error_message: string | null; created_at: string; updated_at: string;
  started_at: string | null; finished_at: string | null;
}

export interface MediaJobEvent {
  id: number; job_id: string; session_id: string; sequence: number; type: string;
  payload: Record<string, unknown>; created_at: string;
}

export type VoiceState = "idle" | "listening" | "transcribing" | "thinking" | "speaking" | "interrupted" | "cancelled" | "error";
export interface VoiceSettings {
  session_id: string; mode: "auto" | "omni" | "modular"; realtime_profile_id: string | null; realtime_model: string;
  input_codec: "pcm16"; output_codec: "pcm16"; sample_rate: number; server_vad: boolean; tool_support: boolean;
  stt_profile_id: string | null; tts_profile_id: string | null;
  stt_model: string; tts_model: string; language: string; voice: string;
  input_device_id: string | null; output_device_id: string | null;
  vad_threshold: number; vad_silence_ms: number; save_audio: boolean; updated_at: string;
}
export interface VoiceSession {
  id: string; session_id: string; status: VoiceState; turn_id: string | null; transcript: string;
  transcript_final: boolean; error_code: string | null; error_message: string | null;
  created_at: string; updated_at: string; finished_at: string | null;
  requested_mode: "auto" | "omni" | "modular"; resolved_mode: "omni" | "modular" | null;
  provider_profile_id: string | null; provider_session_id: string | null;
  input_audio_sequence: number; output_audio_sequence: number; usage: Record<string, unknown> | null;
  first_audio_in_at: string | null; first_transcript_at: string | null; first_text_at: string | null; first_audio_out_at: string | null;
}

export interface TurnCreated {
  turn: Turn;
  user_message: Message;
  assistant_message: Message;
}

export type SkillMode = "off" | "explicit" | "auto" | "always";
export interface SkillSummary {
  id: string; slug: string; name: string; description: string; source_type: "bundled" | "zip" | "folder" | "git";
  source_ref: string | null; mode: SkillMode; priority: number; manifest: Record<string, unknown>;
  enabled: boolean; created_at: string; updated_at: string; deleted_at: string | null;
}
export interface SkillResource { path: string; size: number; category: string }
export interface SkillDetail extends SkillSummary { skill_md: string; resources: SkillResource[] }
export interface SkillMatchItem extends Pick<SkillSummary, "id" | "slug" | "name" | "description" | "mode" | "priority"> {
  score: number; reason: string; matched_terms: string[]; selected: boolean;
}
export interface SkillMatch { explicit: string[]; candidates: SkillMatchItem[]; selected: SkillMatchItem[] }
