import { describe, expect, it, vi } from "vitest";
import { createScrollController } from "./scrollController";

function setup() {
  const element = { scrollTop: 0, scrollHeight: 2400, clientHeight: 600 };
  const showJump = vi.fn();
  return { element, showJump, scroll: createScrollController(element, showJump) };
}

describe("conversation scroll", () => {
  it("opens at the bottom and follows content and viewport resizing", () => {
    const { element, scroll } = setup();
    scroll.toBottom();
    expect(element.scrollTop).toBe(1800);
    element.scrollHeight += 100;
    scroll.onResize();
    expect(element.scrollTop).toBe(1900);
    element.clientHeight -= 80;
    scroll.onResize();
    expect(element.scrollTop).toBe(1980);
  });

  it("respects even a small upward scroll during streaming", () => {
    const { element, scroll, showJump } = setup();
    scroll.toBottom();
    element.scrollTop -= 20;
    scroll.onScroll();
    element.scrollHeight += 500;
    scroll.onResize();
    expect(element.scrollTop).toBe(1780);
    expect(showJump).toHaveBeenLastCalledWith(true);
  });

  it("pauses before a wheel/touch event or disclosure changes layout", () => {
    const { element, scroll } = setup();
    scroll.toBottom();
    scroll.pause();
    element.scrollHeight += 900;
    scroll.onResize();
    expect(element.scrollTop).toBe(1800);
  });

  it("resumes after jump, send, or manually reaching the bottom", () => {
    const { element, scroll } = setup();
    scroll.pause();
    scroll.toBottom();
    element.scrollHeight += 100;
    scroll.onResize();
    expect(element.scrollTop).toBe(1900);
    scroll.pause();
    scroll.followNext();
    element.scrollHeight += 100;
    scroll.onResize();
    expect(element.scrollTop).toBe(2000);
    element.scrollTop = 500;
    scroll.onScroll();
    element.scrollTop = 2000;
    scroll.onScroll();
    element.scrollHeight += 100;
    scroll.onResize();
    expect(element.scrollTop).toBe(2100);
  });

  it("does not produce negative scroll positions in an empty chat", () => {
    const { element, scroll, showJump } = setup();
    element.scrollHeight = 300;
    scroll.toBottom();
    expect(element.scrollTop).toBe(0);
    expect(showJump).toHaveBeenLastCalledWith(false);
  });
});
