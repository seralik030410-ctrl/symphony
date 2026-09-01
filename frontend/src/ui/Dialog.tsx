import { useEffect, useRef, type ReactNode } from "react";

export function Dialog({ title, className = "", onClose, children }: {
  title: string; className?: string; onClose: () => void; children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const element = ref.current!;
    const previous = document.activeElement as HTMLElement | null;
    element.showModal();
    return () => { element.close(); previous?.focus(); };
  }, []);
  return <dialog ref={ref} className={`app-dialog ${className}`} aria-label={title}
    onCancel={(event) => { event.preventDefault(); closeRef.current(); }}>
    {children}
  </dialog>;
}
