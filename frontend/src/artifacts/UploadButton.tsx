import { Paperclip, CircleNotch } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { api } from "../api";

export function UploadButton({ sessionId, disabled, remaining, onBusyChange, onUploaded, onError }: { sessionId: string; disabled: boolean; remaining: number; onBusyChange: (busy: boolean) => void; onUploaded: (value: Awaited<ReturnType<typeof api.uploadInput>>) => void; onError: (message: string) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; onBusyChange(false); }; }, []);
  async function upload(file: File) {
    try {
      const image = /^image\//.test(file.type) || /\.(png|jpe?g|webp)$/i.test(file.name);
      if (file.size > (image ? 10_000_000 : 25_000_000)) throw new Error(`Максимальный размер ${image ? "изображения — 10" : "файла — 25"} МБ`);
      const encoded = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(",")[1]); reader.onerror = reject; reader.readAsDataURL(file); });
      const result = await api.uploadInput(sessionId, file.name, encoded); onUploaded(result);
    } catch (error) { onError(error instanceof Error ? error.message : "Не удалось прикрепить файл"); }
  }
  async function uploadBatch(files: File[]) {
    if (busy || disabled) return;
    if (files.length > remaining) { onError(`Можно добавить ещё ${remaining} файлов. В одном сообщении — не больше восьми.`); if (input.current) input.current.value = ""; return; }
    setBusy(true); onBusyChange(true);
    try { for (const file of files) { if (!mounted.current) break; await upload(file); } }
    finally { if (mounted.current) { setBusy(false); onBusyChange(false); if (input.current) input.current.value = ""; } }
  }
  return <><input ref={input} type="file" hidden multiple accept=".txt,.md,.xlsx,.csv,.json,.pdf,.docx,.pptx,.png,.jpg,.jpeg,.webp" onChange={event => void uploadBatch([...(event.target.files ?? [])])} />
    <button type="button" className="icon-button upload-button" aria-label="Прикрепить файлы или изображения" title="До 8 файлов: документы до 25 МБ, изображения до 10 МБ" disabled={disabled || busy} onClick={() => input.current?.click()}>{busy ? <CircleNotch size={20} className="turn-spinner" /> : <Paperclip size={20} />}</button></>;
}
