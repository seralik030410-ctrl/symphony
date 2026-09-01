type ScrollElement = Pick<HTMLElement, "scrollTop" | "scrollHeight" | "clientHeight">;

/** Reader intent is separate from layout changes and programmatic scroll events. */
export function createScrollController(element: ScrollElement, showJump: (show: boolean) => void) {
  let following = true;
  let lastTop = element.scrollTop;
  const distance = () => Math.max(0, element.scrollHeight - element.clientHeight - element.scrollTop);
  const update = () => showJump(distance() > 32);
  const toBottom = () => {
    following = true;
    element.scrollTop = Math.max(0, element.scrollHeight - element.clientHeight);
    lastTop = element.scrollTop;
    update();
  };
  return {
    toBottom,
    followNext: () => { following = true; },
    pause: () => { following = false; },
    onScroll: () => {
      if (element.scrollTop < lastTop - 1) following = false;
      else if (distance() <= 32) following = true;
      lastTop = element.scrollTop;
      update();
    },
    onResize: () => { if (following) toBottom(); else update(); },
  };
}
