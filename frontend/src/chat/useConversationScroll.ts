import { useCallback, useLayoutEffect, useRef, useState } from "react";
import { createScrollController } from "./scrollController";

export function useConversationScroll(ready: boolean, sessionId: string | undefined) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const controller = useRef<ReturnType<typeof createScrollController> | null>(null);
  const [showJump, setShowJump] = useState(false);

  useLayoutEffect(() => {
    const element = scrollRef.current;
    const content = contentRef.current;
    if (!ready || !element || !content) return;
    const scroll = createScrollController(element, setShowJump);
    controller.current = scroll;
    scroll.toBottom();
    // Streaming, disclosure expansion, wrapping, and composer/viewport resizing.
    const observer = new ResizeObserver(scroll.onResize);
    observer.observe(element);
    observer.observe(content);
    return () => { observer.disconnect(); controller.current = null; };
  }, [ready, sessionId]);

  useLayoutEffect(() => { controller.current?.onResize(); });

  const toBottom = useCallback(() => controller.current?.toBottom(), []);
  const followNext = useCallback(() => controller.current?.followNext(), []);
  const pause = useCallback(() => controller.current?.pause(), []);
  const onScroll = useCallback(() => controller.current?.onScroll(), []);
  return { scrollRef, contentRef, showJump, toBottom, followNext, pause, onScroll };
}
