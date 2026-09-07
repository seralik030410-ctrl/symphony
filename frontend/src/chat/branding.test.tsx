import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { Message } from "../types";
import { MessageList } from "./MessageList";

const assistantMessage: Message = {
  id: "message-1",
  session_id: "session-1",
  turn_id: null,
  role: "assistant",
  content: "Готово",
  status: "complete",
  created_at: "2026-09-07T00:00:00Z",
  updated_at: "2026-09-07T00:00:00Z",
};

describe("FinCtrl branding", () => {
  it("labels assistant messages with the public product name", () => {
    const html = renderToStaticMarkup(
      <MessageList
        messages={[assistantMessage]}
        turns={[]}
        events={[]}
        retryingTurnId={null}
        onRetry={() => {}}
        decidingApprovalId={null}
        onApproval={() => {}}
        onPreview={() => {}}
        onFile={() => {}}
        onChanges={() => {}}
        onArtifact={() => {}}
      />,
    );

    expect(html).toContain("FinCtrl");
    expect(html).not.toContain("Symphony");
  });
});
