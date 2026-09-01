import { useEffect, useState } from "react";
import { api } from "../api";
import type { Session } from "../types";
import { CustomSelect } from "../ui/CustomSelect";

export function ImageMode({ session, value, disabled, onChange }: { session: Session; value: "vision" | "ocr"; disabled: boolean; onChange: (value: "vision" | "ocr") => void }) {
  const [supported, setSupported] = useState<boolean | null>(null);
  useEffect(() => {
    let disposed = false;
    api.modelCapabilities(session.id).then(caps => { if (!disposed) setSupported(caps.vision); }).catch(() => { if (!disposed) setSupported(null); });
    return () => { disposed = true; };
  }, [session.id, session.provider, session.model]);
  return <div className="context-budget-footer">
    <CustomSelect ariaLabel="Обработка изображений" value={value} disabled={disabled} onChange={next => onChange(next as "vision" | "ocr")} options={[
      { value: "vision", label: "Анализ изображения", description: "Отправить фото выбранной vision-модели" },
      { value: "ocr", label: "Только текст · локальный OCR", description: "Без отправки самого изображения модели" },
    ]} />
    {value === "vision" && supported === false ? <p role="status">Эта модель не заявляет vision. Выберите совместимую модель или OCR для чтения текста.</p> : null}
  </div>;
}
