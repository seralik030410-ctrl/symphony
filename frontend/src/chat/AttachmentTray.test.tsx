import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Attachment } from "../types";
import { AttachmentTray } from "./AttachmentTray";

const image: Attachment = {
  id: "image-1", filename: "diagram.png", mime_type: "image/png", size: 1200,
  width: 640, height: 480, path: "inputs/diagram.png",
};
const document: Attachment = {
  id: "file-1", filename: "notes.pdf", mime_type: "application/pdf", size: 4200,
  width: null, height: null, path: "inputs/notes.pdf",
};

describe("composer attachment previews", () => {
  it("shows simple previews without technical attachment metadata", () => {
    const html = renderToStaticMarkup(
      <AttachmentTray sessionId="session-1" items={[image, document]} disabled={false} onRemove={() => {}} />,
    );

    expect(html).toContain("/api/sessions/session-1/inputs/image-1");
    expect(html).toContain("diagram.png");
    expect(html).toContain("notes.pdf");
    expect(html).not.toContain("640×480");
    expect(html).not.toContain("проиндексирован");
    expect(html).not.toContain("application/pdf");
  });
});
