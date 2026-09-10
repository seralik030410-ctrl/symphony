from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class MediaUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=180, pattern=r"^[^/\\:\x00]+$")
    mime_type: Literal[
        "image/png", "image/jpeg", "image/webp", "image/gif",
        "video/mp4", "video/webm", "audio/wav", "audio/mpeg", "audio/webm", "audio/ogg", "audio/mp4",
    ]
    content_base64: str = Field(min_length=4, max_length=140_000_000)
    source: str = Field(default="upload", min_length=1, max_length=80)
    provenance: dict[str, Any] = Field(default_factory=dict)


class MediaJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["media.preview"] = "media.preview"
    input: dict[str, Any] = Field(default_factory=dict)
    turn_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    provider_profile_id: str | None = Field(default=None, min_length=1, max_length=64)


class ComfyUIConnectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_url: str = Field(min_length=8, max_length=2_000)
    allow_private_network: bool = False
    timeout_seconds: float = Field(default=120, gt=0, le=3_600)


class ComfyUIQuickGenerate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["image", "video"]
    template_id: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    values: dict[str, Any] = Field(default_factory=dict)
    turn_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    provider_profile_id: str | None = Field(default=None, min_length=1, max_length=64)


class ComfyUIWorkflowImport(BaseModel):
    """Persisted in the browser/recent list until custom template storage lands."""

    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    workflow: dict[str, Any]


class ComfyUIWorkflowRun(ComfyUIWorkflowImport):
    kind: Literal["image", "video"]
    turn_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    provider_profile_id: str | None = Field(default=None, min_length=1, max_length=64)
