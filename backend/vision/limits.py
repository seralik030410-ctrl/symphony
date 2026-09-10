from __future__ import annotations

from dataclasses import asdict
from math import ceil
from typing import Any, Iterable

from backend.models.base import ModelCapabilities


class VisionLimitError(ValueError):
    pass


def estimate_image_tokens(width: int | None, height: int | None, *, per_image_cap: int = 2_048) -> int:
    """Estimate high-detail image cost using 512px tiles.

    The value deliberately remains an estimate: individual provider tokenizers
    differ, but the same formula is used for the UI budget and server reserve.
    """
    if not width or not height or width < 1 or height < 1:
        return min(2_048, per_image_cap)
    tiles = ceil(width / 512) * ceil(height / 512)
    return min(per_image_cap, 85 + 170 * tiles)


def limits_from_capabilities(capabilities: ModelCapabilities) -> dict[str, int]:
    return {
        key: int(value)
        for key, value in asdict(capabilities).items()
        if key in {
            "max_vision_frames", "max_image_bytes", "max_image_width",
            "max_image_height", "max_image_tokens", "max_vision_tokens",
        }
    }


def validate_image_attachments(
    attachments: Iterable[dict[str, Any]], capabilities: ModelCapabilities,
) -> tuple[list[dict[str, Any]], int]:
    """Return selected vision images and their conservative aggregate cost."""
    selected = [
        item for item in attachments
        if str(item.get("mime_type", "")).startswith("image/")
        and item.get("image_mode", "vision") == "vision"
    ]
    if len(selected) > capabilities.max_vision_frames:
        raise VisionLimitError(f"This model accepts at most {capabilities.max_vision_frames} vision frames per turn")
    total = 0
    for item in selected:
        width, height, size = item.get("width"), item.get("height"), item.get("size")
        if not isinstance(size, int) or size < 0 or size > capabilities.max_image_bytes:
            raise VisionLimitError(f"{item.get('filename', 'Image')} exceeds the {capabilities.max_image_bytes // 1_000_000} MB model limit")
        if not isinstance(width, int) or not isinstance(height, int) or width < 1 or height < 1:
            raise VisionLimitError(f"{item.get('filename', 'Image')} has no valid dimensions")
        if width > capabilities.max_image_width or height > capabilities.max_image_height:
            raise VisionLimitError(
                f"{item.get('filename', 'Image')} exceeds the {capabilities.max_image_width}×{capabilities.max_image_height} model limit"
            )
        estimated = estimate_image_tokens(width, height, per_image_cap=capabilities.max_image_tokens)
        total += estimated
        item["estimated_tokens"] = estimated
    if total > capabilities.max_vision_tokens:
        raise VisionLimitError(f"Selected frames need about {total} tokens; this model allows {capabilities.max_vision_tokens}")
    return selected, total
