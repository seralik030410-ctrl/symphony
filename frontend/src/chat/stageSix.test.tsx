import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ContextTrace } from "./ContextTrace";
import { AttachmentTray } from "./AttachmentTray";
import type { TurnEvent } from "../types";

const event = (type: string, payload: Record<string, unknown> = {}): TurnEvent => ({ id: 1, turn_id: "turn", session_id: "session", sequence: 1, created_at: "", type, payload });

describe("Stage 6 context UI", () => {
  it("shows only the newest memory snapshot after multiple batches", () => {
    const html = renderToStaticMarkup(<ContextTrace events={[event("memory.snapshot", { version: 1 }), event("memory.snapshot", { version: 2 })]} />);
    expect(html).toContain("Память v2");
    expect(html).not.toContain(" open=");
  });
  it("does not show a context panel for an ordinary chat", () => {
    expect(renderToStaticMarkup(<ContextTrace events={[event("context.built", {memory_version: 0})]} />)).toBe("");
  });
  it("escapes untrusted filenames and uses session-scoped image URLs", () => {
    const html = renderToStaticMarkup(<AttachmentTray sessionId="session-a" disabled={false} onRemove={() => {}} items={[{id: "image-1", filename: '<script>alert(1)</script>.png', mime_type:"image/png", size:100, width:30, height:20, path:"inputs/image.png"}]} />);
    expect(html).not.toContain("<script>");
    expect(html).toContain("/api/sessions/session-a/inputs/image-1");
    expect(html).toContain("Убрать");
  });
});
