import type { VisionModelLimits } from "../types";

export const DEFAULT_VISION_LIMITS: VisionModelLimits = {
  max_vision_frames: 8,
  max_image_bytes: 10_000_000,
  max_image_width: 4096,
  max_image_height: 4096,
  max_image_tokens: 2048,
  max_vision_tokens: 8192,
};

export function estimateImageTokens(width: number, height: number, cap = DEFAULT_VISION_LIMITS.max_image_tokens): number {
  if (width < 1 || height < 1) return cap;
  return Math.min(cap, 85 + 170 * Math.ceil(width / 512) * Math.ceil(height / 512));
}

export function selectedFrameLimitError(selectedCount: number, maxFrames: number): string | null {
  return selectedCount >= maxFrames ? `Можно выбрать не более ${maxFrames} кадров` : null;
}

export function frameLimitError(file: File, width: number, height: number, limits: VisionModelLimits): string | null {
  if (file.size > limits.max_image_bytes) return `${file.name}: больше лимита ${Math.floor(limits.max_image_bytes / 1_000_000)} МБ`;
  if (width > limits.max_image_width || height > limits.max_image_height) return `${file.name}: больше ${limits.max_image_width}×${limits.max_image_height}`;
  return null;
}
