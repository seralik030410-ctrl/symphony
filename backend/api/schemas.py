from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ProviderName = Literal["ollama", "openai"]
PolicyProfile = Literal["read_only", "project_edit", "build", "full_manual"]
SkillMode = Literal["off", "explicit", "auto", "always"]


class SessionCreate(BaseModel):
    title: str = Field(default="Новый чат", min_length=1, max_length=120)
    provider: ProviderName | None = None
    model: str | None = Field(default=None, max_length=200)
    system_prompt: str = Field(default="You are a helpful, direct assistant.", max_length=4_000)


class SessionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    provider: ProviderName | None = None
    model: str | None = Field(default=None, min_length=1, max_length=200)
    system_prompt: str | None = Field(default=None, max_length=4_000)
    context_window: int | None = Field(default=None, ge=1_024, le=262_144)
    max_output: int | None = Field(default=None, ge=64, le=65_536)
    policy_profile: PolicyProfile | None = None


class ApprovalDecision(BaseModel):
    approved: bool
    note: str | None = Field(default=None, max_length=1_000)


class SkillInstall(BaseModel):
    source_type: Literal["zip", "folder", "git"]
    source: str = Field(default="", max_length=2_000)
    zip_base64: str | None = Field(default=None, max_length=14_000_000)
    filename: str | None = Field(default=None, max_length=240)
    mode: SkillMode = "explicit"


class SkillUpdate(BaseModel):
    mode: SkillMode | None = None
    priority: int | None = Field(default=None, ge=0, le=100)
    skill_md: str | None = Field(default=None, max_length=256_000)


class SkillValidate(BaseModel):
    skill_md: str = Field(min_length=1, max_length=256_000)


class SkillTestPrompt(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)


class TurnCreate(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=8)
    image_mode: Literal["vision", "ocr"] = "vision"


class AttachmentRead(BaseModel):
    id: str
    filename: str
    mime_type: str
    size: int
    width: int | None = None
    height: int | None = None
    path: str
    image_mode: Literal["vision", "ocr"] = "vision"


class MessageRead(BaseModel):
    id: str
    session_id: str
    turn_id: str | None
    role: Literal["user", "assistant", "system"]
    content: str
    status: Literal["complete", "streaming", "cancelled", "failed"]
    created_at: str
    updated_at: str
    attachments: list[AttachmentRead] = []


class TurnRead(BaseModel):
    id: str
    session_id: str
    user_message_id: str
    assistant_message_id: str
    status: Literal[
        "queued",
        "preparing",
        "model_running",
        "completed",
        "failed",
        "cancelled",
        "interrupted",
    ]
    provider: str
    model: str
    request_id: str
    error: str | None
    cancel_requested: bool
    created_at: str
    started_at: str | None
    finished_at: str | None
    last_event_sequence: int = 0


class SessionSummary(BaseModel):
    id: str
    title: str
    provider: str
    model: str
    created_at: str
    updated_at: str
    last_message_preview: str = ""
    active_turn: bool = False


class SessionRead(BaseModel):
    id: str
    title: str
    provider: str
    model: str
    system_prompt: str
    context_window: int
    max_output: int
    policy_profile: PolicyProfile
    created_at: str
    updated_at: str
    messages: list[MessageRead] = []
    turns: list[TurnRead] = []


class EventRead(BaseModel):
    id: int
    turn_id: str
    session_id: str
    sequence: int
    type: str
    payload: dict[str, Any]
    created_at: str


class TurnCreated(BaseModel):
    turn: TurnRead
    user_message: MessageRead
    assistant_message: MessageRead


class ModelCapabilities(BaseModel):
    text: bool = True
    vision: bool = False
    native_tools: bool = False
    json_schema: bool = False
    reasoning_stream: bool = False
    max_context: int = 16_384
    max_output: int = 2_048


class ModelProfileRead(BaseModel):
    provider: ProviderName
    title: str
    base_url: str
    default_model: str
    models: list[str]
    available: bool
    health_message: str
    capabilities: ModelCapabilities
