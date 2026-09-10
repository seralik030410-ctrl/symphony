import type { FrameProvenance, VisionCaptureSource } from "../types";

export interface CapturedImage {
  file: File;
  provenance: FrameProvenance;
}

export interface ActiveCapture {
  readonly source: "camera" | "screen";
  readonly stream: MediaStream;
  captureFrame(reason?: FrameProvenance["reason"]): Promise<CapturedImage>;
  stop(): void;
}

export async function startCameraCapture(constraints: MediaTrackConstraints = {}): Promise<ActiveCapture> {
  if (!navigator.mediaDevices?.getUserMedia) throw new Error("Камера недоступна в этом браузере");
  const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", ...constraints }, audio: false });
  return makeActiveCapture("camera", stream);
}

export async function startScreenCapture(): Promise<ActiveCapture> {
  if (!navigator.mediaDevices?.getDisplayMedia) throw new Error("Захват экрана недоступен в этом браузере");
  const stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
  return makeActiveCapture("screen", stream);
}

export async function clipboardImages(): Promise<CapturedImage[]> {
  if (!navigator.clipboard?.read) throw new Error("Вставка изображений из буфера недоступна. Используйте Ctrl+V в поле вложений.");
  const entries = await navigator.clipboard.read();
  const images: CapturedImage[] = [];
  for (const entry of entries) {
    const type = entry.types.find(item => item.startsWith("image/"));
    if (!type) continue;
    const blob = await entry.getType(type);
    images.push(asCapture(blob, "clipboard", "manual"));
  }
  return images;
}

export function pastedImages(event: ClipboardEvent): CapturedImage[] {
  const files = [...(event.clipboardData?.files ?? [])].filter(file => file.type.startsWith("image/"));
  return files.map(file => ({ file, provenance: baseProvenance("clipboard", "manual") }));
}

function makeActiveCapture(source: "camera" | "screen", stream: MediaStream): ActiveCapture {
  const track = stream.getVideoTracks()[0];
  let stopped = false;
  const stop = () => {
    if (stopped) return;
    stopped = true;
    stream.getTracks().forEach(item => item.stop());
  };
  track?.addEventListener("ended", stop, { once: true });
  return {
    source, stream,
    async captureFrame(reason = "manual") {
      if (stopped || !track || track.readyState !== "live") throw new Error("Захват уже остановлен");
      const video = document.createElement("video");
      video.muted = true;
      video.playsInline = true;
      video.srcObject = stream;
      await waitForVideo(video);
      try {
        const blob = await frameFromVideo(video);
        const label = track.label || undefined;
        return asCapture(blob, source, reason, source === "camera" ? { device_label: label } : { display_label: label });
      } finally {
        video.pause();
        video.srcObject = null;
      }
    },
    stop,
  };
}

async function waitForVideo(video: HTMLVideoElement): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const timeout = window.setTimeout(() => reject(new Error("Кадр с камеры не получен")), 8_000);
    video.addEventListener("loadeddata", () => { window.clearTimeout(timeout); resolve(); }, { once: true });
    void video.play().catch(error => { window.clearTimeout(timeout); reject(error); });
  });
}

async function frameFromVideo(video: HTMLVideoElement): Promise<Blob> {
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  if (!canvas.width || !canvas.height) throw new Error("Источник не передал размеры кадра");
  canvas.getContext("2d")?.drawImage(video, 0, 0);
  const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, "image/jpeg", 0.9));
  if (!blob) throw new Error("Не удалось сохранить кадр");
  return blob;
}

function asCapture(blob: Blob, source: VisionCaptureSource, reason: FrameProvenance["reason"], extra: Partial<FrameProvenance> = {}): CapturedImage {
  const suffix = blob.type === "image/png" ? "png" : "jpg";
  return {
    file: new File([blob], `${source}-${Date.now()}.${suffix}`, { type: blob.type || "image/jpeg" }),
    provenance: { ...baseProvenance(source, reason), ...extra },
  };
}

function baseProvenance(source: VisionCaptureSource, reason: FrameProvenance["reason"]): FrameProvenance {
  return { source, reason, captured_at: new Date().toISOString() };
}
