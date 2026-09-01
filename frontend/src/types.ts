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

export interface ModelProfile {
  provider: "ollama" | "openai";
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
    max_context: number;
    max_output: number;
  };
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
