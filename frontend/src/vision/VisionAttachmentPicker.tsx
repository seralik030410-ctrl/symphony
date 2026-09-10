import { Camera, ClipboardText, Desktop, ImageSquare, Stop, X } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Attachment, AttachmentUse, VisionModelLimits } from "../types";
import { clipboardImages, pastedImages, startCameraCapture, startScreenCapture, type ActiveCapture, type CapturedImage } from "./capture";
import { DEFAULT_VISION_LIMITS, estimateImageTokens, frameLimitError, selectedFrameLimitError } from "./limits";
import "./vision.css";

type Selected = { attachment: Attachment; use: AttachmentUse; preview: string; width: number; height: number; selected: boolean };

export function VisionAttachmentPicker({
  sessionId, disabled, limits = DEFAULT_VISION_LIMITS, onSelectionChange,
}: {
  sessionId: string; disabled: boolean; limits?: VisionModelLimits;
  onSelectionChange: (items: Array<{ attachment: Attachment; use: AttachmentUse }>) => void;
}) {
  const [items, setItems] = useState<Selected[]>([]);
  const [capture, setCapture] = useState<ActiveCapture | null>(null);
  const [notice, setNotice] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const captureRef = useRef<ActiveCapture | null>(null);
  const itemsRef = useRef<Selected[]>([]);

  useEffect(() => { captureRef.current = capture; }, [capture]);
  useEffect(() => { itemsRef.current = items; }, [items]);
  useEffect(() => () => { captureRef.current?.stop(); itemsRef.current.forEach(item => URL.revokeObjectURL(item.preview)); }, []);
  useEffect(() => { onSelectionChange(items.filter(item => item.selected).map(({ attachment, use }) => ({ attachment, use }))); }, [items, onSelectionChange]);
  useEffect(() => {
    const paste = (event: ClipboardEvent) => {
      const captures = pastedImages(event);
      if (!captures.length || disabled) return;
      event.preventDefault();
      void addMany(captures);
    };
    window.addEventListener("paste", paste);
    return () => window.removeEventListener("paste", paste);
  });

  async function addMany(captures: CapturedImage[]) {
    for (const captured of captures) await add(captured);
  }
  async function add(captured: CapturedImage) {
    setNotice("");
    try {
      const selectionIssue = selectedFrameLimitError(itemsRef.current.filter(item => item.selected).length, limits.max_vision_frames);
      if (selectionIssue) throw new Error(selectionIssue);
      const dimensions = await imageSize(captured.file);
      const issue = frameLimitError(captured.file, dimensions.width, dimensions.height, limits);
      if (issue) throw new Error(issue);
      const attachment = await api.uploadInput(sessionId, captured.file.name, await base64(captured.file));
      const currentIssue = selectedFrameLimitError(itemsRef.current.filter(item => item.selected).length, limits.max_vision_frames);
      if (currentIssue) {
        await api.deleteInput(sessionId, attachment.id);
        throw new Error(currentIssue);
      }
      const preview = URL.createObjectURL(captured.file);
      const next = [...itemsRef.current, {
        attachment,
        use: { attachment_id: attachment.id, provenance: captured.provenance },
        preview, ...dimensions, selected: true,
      }];
      itemsRef.current = next;
      setItems(next);
    } catch (error) { setNotice(error instanceof Error ? error.message : "Кадр не добавлен"); }
  }
  async function begin(kind: "camera" | "screen") {
    setNotice("");
    try {
      capture?.stop();
      const next = kind === "camera" ? await startCameraCapture() : await startScreenCapture();
      next.stream.getVideoTracks()[0]?.addEventListener("ended", () => {
        setCapture(current => current === next ? null : current);
        setNotice(kind === "screen" ? "Демонстрация экрана завершена" : "Камера отключена");
      }, { once: true });
      setCapture(next);
    } catch (error) { setNotice(error instanceof Error ? error.message : "Захват не начался"); }
  }
  async function captureFrame() {
    if (!capture) return;
    try { await add(await capture.captureFrame()); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Кадр не получен"); }
  }
  async function remove(item: Selected) {
    try { await api.deleteInput(sessionId, item.attachment.id); }
    catch (error) { setNotice(error instanceof Error ? error.message : "Кадр не удалён"); return; }
    URL.revokeObjectURL(item.preview);
    const next = itemsRef.current.filter(candidate => candidate.attachment.id !== item.attachment.id);
    itemsRef.current = next;
    setItems(next);
  }
  function toggle(item: Selected) {
    if (!item.selected) {
      const issue = selectedFrameLimitError(itemsRef.current.filter(candidate => candidate.selected).length, limits.max_vision_frames);
      if (issue) { setNotice(issue); return; }
    }
    setNotice("");
    const next = itemsRef.current.map(candidate => candidate.attachment.id === item.attachment.id ? { ...candidate, selected: !candidate.selected } : candidate);
    itemsRef.current = next;
    setItems(next);
  }
  return <section className="vision-picker" aria-label="Кадры для анализа">
    <div className="vision-picker-actions">
      <button type="button" className="icon-button" disabled={disabled} title="Добавить изображение" onClick={() => fileInput.current?.click()}><ImageSquare size={18} /></button>
      <button type="button" className="icon-button" disabled={disabled} title="Снимок с камеры" onClick={() => void begin("camera")}><Camera size={18} /></button>
      <button type="button" className="icon-button" disabled={disabled} title="Снимок экрана" onClick={() => void begin("screen")}><Desktop size={18} /></button>
      <button type="button" className="icon-button" disabled={disabled} title="Вставить изображение" onClick={() => void clipboardImages().then(addMany).catch(error => setNotice(error instanceof Error ? error.message : "Буфер недоступен"))}><ClipboardText size={18} /></button>
      <input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp" hidden multiple onChange={event => { void addMany([...event.currentTarget.files ?? []].map(file => ({ file, provenance: { source: "file", reason: "manual", captured_at: new Date().toISOString() } }))); event.currentTarget.value = ""; }} />
    </div>
    {capture ? <div className="vision-capture-status"><span>{capture.source === "camera" ? "Камера активна" : "Захват экрана активен"}</span><button type="button" className="text-button" onClick={() => void captureFrame()}>Сохранить кадр</button><button type="button" className="icon-button" aria-label="Остановить захват" onClick={() => { capture.stop(); setCapture(null); }}><Stop size={16} /></button></div> : null}
    {items.length ? <div className="vision-frame-grid">{items.map(item => <article key={item.attachment.id} className={item.selected ? "vision-frame selected" : "vision-frame"}>
      <img src={item.preview} alt={`Предпросмотр ${item.attachment.filename}`} />
      <label><input type="checkbox" checked={item.selected} disabled={disabled} onChange={() => toggle(item)} /> В контексте</label>
      <small>{item.use.provenance.source} · {item.width}×{item.height} · ≈{estimateImageTokens(item.width, item.height, limits.max_image_tokens)} токенов</small>
      <button type="button" className="icon-button" disabled={disabled} aria-label={`Удалить ${item.attachment.filename}`} onClick={() => void remove(item)}><X size={15} /></button>
    </article>)}</div> : null}
    {notice ? <p role="status">{notice}</p> : null}
  </section>;
}

async function base64(file: Blob): Promise<string> {
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let value = "";
  for (let index = 0; index < bytes.length; index += 0x8000) value += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
  return btoa(value);
}

async function imageSize(file: Blob): Promise<{ width: number; height: number }> {
  const bitmap = await createImageBitmap(file);
  try { return { width: bitmap.width, height: bitmap.height }; }
  finally { bitmap.close(); }
}
