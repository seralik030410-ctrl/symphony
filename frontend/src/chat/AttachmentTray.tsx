import { FileText, X } from "@phosphor-icons/react";
import type { Attachment } from "../types";

export function AttachmentTray({ sessionId, items, disabled, onRemove }: { sessionId: string; items: Attachment[]; disabled: boolean; onRemove: (id: string) => void }) {
  if (!items.length) return null;
  return <div className="attachment-tray" aria-label="Вложения сообщения">
    {items.map(item => item.mime_type.startsWith("image/")
      ? <figure className="attachment-preview attachment-preview-image" key={item.id}>
          <img src={`/api/sessions/${sessionId}/inputs/${item.id}`} alt={`Предпросмотр ${item.filename}`} />
          <figcaption title={item.filename}>{item.filename}</figcaption>
          <button type="button" disabled={disabled} aria-label={`Убрать ${item.filename}`} onClick={() => onRemove(item.id)}><X size={14} /></button>
        </figure>
      : <div className="attachment-preview attachment-preview-file" key={item.id}>
          <FileText size={18} aria-hidden="true" />
          <span title={item.filename}>{item.filename}</span>
          <button type="button" disabled={disabled} aria-label={`Убрать ${item.filename}`} onClick={() => onRemove(item.id)}><X size={14} /></button>
        </div>)}
  </div>;
}
