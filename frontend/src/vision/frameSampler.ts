import type { CapturedImage } from "./capture";

export interface FrameSamplerOptions {
  changeThreshold?: number;
  minIntervalMs?: number;
  maxIntervalMs?: number;
}

export interface SampledFrame extends CapturedImage {
  provenance: CapturedImage["provenance"] & { sequence: number; change_score?: number };
}

/** Samples deliberately: first frame, meaningful visual changes, or a safe interval. */
export class FrameSampler {
  private previousHash: Uint8Array | null = null;
  private lastAcceptedAt = 0;
  private sequence = 0;
  private readonly changeThreshold: number;
  private readonly minIntervalMs: number;
  private readonly maxIntervalMs: number;

  constructor(options: FrameSamplerOptions = {}) {
    this.changeThreshold = options.changeThreshold ?? 0.14;
    this.minIntervalMs = options.minIntervalMs ?? 1_500;
    this.maxIntervalMs = options.maxIntervalMs ?? 15_000;
  }

  async consider(capture: CapturedImage, force = false): Promise<SampledFrame | null> {
    const now = Date.now();
    const hash = await perceptualHash(capture.file);
    const change = this.previousHash ? hammingDistance(hash, this.previousHash) / hash.length : 1;
    const elapsed = now - this.lastAcceptedAt;
    const reason = force ? "manual" : this.previousHash === null ? "initial" : change >= this.changeThreshold ? "change" : elapsed >= this.maxIntervalMs ? "interval" : null;
    if (!reason || (!force && elapsed < this.minIntervalMs)) return null;
    this.previousHash = hash;
    this.lastAcceptedAt = now;
    this.sequence += 1;
    return { ...capture, provenance: { ...capture.provenance, reason, sequence: this.sequence, change_score: Number(change.toFixed(4)) } };
  }

  reset(): void {
    this.previousHash = null;
    this.lastAcceptedAt = 0;
    this.sequence = 0;
  }
}

async function perceptualHash(blob: Blob): Promise<Uint8Array> {
  const bitmap = await createImageBitmap(blob);
  try {
    const canvas = document.createElement("canvas");
    canvas.width = 8; canvas.height = 8;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) throw new Error("Недоступен анализ кадров");
    context.drawImage(bitmap, 0, 0, 8, 8);
    const pixels = context.getImageData(0, 0, 8, 8).data;
    const values = new Uint8Array(64);
    let total = 0;
    for (let index = 0; index < 64; index += 1) {
      const offset = index * 4;
      values[index] = Math.round(0.299 * pixels[offset] + 0.587 * pixels[offset + 1] + 0.114 * pixels[offset + 2]);
      total += values[index];
    }
    const average = total / values.length;
    return Uint8Array.from(values, value => value >= average ? 1 : 0);
  } finally { bitmap.close(); }
}

function hammingDistance(left: Uint8Array, right: Uint8Array): number {
  let total = 0;
  for (let index = 0; index < left.length; index += 1) total += left[index] === right[index] ? 0 : 1;
  return total;
}
