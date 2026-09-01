import { FileText, ImageSquare, X } from "@phosphor-icons/react";
import type { Attachment } from "../types";

export function AttachmentTray({ sessionId, items, disabled, onRemove }: { sessionId: string; items: Attachment[]; disabled: boolean; onRemove: (id: string) => void }) {
  if (!items.length) return null;
  return <div className="attachment-tray" aria-label="Вложения сообщения">
    {items.map(item => <div className="attachment-chip" key={item.id}>
      {item.mime_type.startsWith("image/")
        ? <img src={`/api/sessions/${sessionId}/inputs/${item.id}`} alt={`Предпросмотр ${item.filename}`} />
        : <span className="attachment-file-icon"><FileText size={20} aria-hidden="true" /></span>}
      <span><strong>{item.filename}</strong><small>{item.mime_type.startsWith("image/") ? `${item.width}×${item.height}` : `${Math.max(1, Math.round(item.size / 1024))} КБ · проиндексирован`}</small></span>
      <button type="button" disabled={disabled} aria-label={`Убрать ${item.filename}`} onClick={() => onRemove(item.id)}><X size={14} /></button>
      {item.mime_type.startsWith("image/") ? <ImageSquare className="sr-only" /> : null}
    </div>)}
  </div>;
}
