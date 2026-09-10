from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


CaptureSource = Literal["file", "clipboard", "camera", "screen", "live"]
FrameReason = Literal["manual", "initial", "change", "interval"]


@dataclass(frozen=True, slots=True)
class FrameProvenance:
    """Non-secret information explaining how a selected frame entered a turn."""

    source: CaptureSource = "file"
    reason: FrameReason = "manual"
    captured_at: str | None = None
    sequence: int | None = None
    device_label: str | None = None
    display_label: str | None = None
    change_score: float | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None) -> "FrameProvenance":
        value = value or {}
        source = value.get("source", "file")
        reason = value.get("reason", "manual")
        if source not in {"file", "clipboard", "camera", "screen", "live"}:
            source = "file"
        if reason not in {"manual", "initial", "change", "interval"}:
            reason = "manual"
        score = value.get("change_score")
        return cls(
            source=source,
            reason=reason,
            captured_at=_bounded_text(value.get("captured_at"), 64),
            sequence=_bounded_int(value.get("sequence"), 0, 1_000_000),
            device_label=_bounded_text(value.get("device_label"), 160),
            display_label=_bounded_text(value.get("display_label"), 160),
            change_score=round(float(score), 4) if isinstance(score, (int, float)) and 0 <= score <= 1 else None,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "reason": self.reason,
            "captured_at": self.captured_at,
            "sequence": self.sequence,
            "device_label": self.device_label,
            "display_label": self.display_label,
            "change_score": self.change_score,
        }


@dataclass(frozen=True, slots=True)
class VisionAttachmentUse:
    attachment_id: str
    image_mode: Literal["vision", "ocr"] = "vision"
    provenance: FrameProvenance = field(default_factory=FrameProvenance)


@dataclass(frozen=True, slots=True)
class VisionModelLimits:
    """Provider-declared bounds; estimates are conservative, not tokenizer counts."""

    max_vision_frames: int = 8
    max_image_bytes: int = 10_000_000
    max_image_width: int = 4_096
    max_image_height: int = 4_096
    max_image_tokens: int = 2_048
    max_vision_tokens: int = 8_192


def _bounded_text(value: Any, maximum: int) -> str | None:
    return value.strip()[:maximum] if isinstance(value, str) and value.strip() else None


def _bounded_int(value: Any, minimum: int, maximum: int) -> int | None:
    return value if isinstance(value, int) and minimum <= value <= maximum else None
