import { describe, it, expect } from "vitest";
import { openTab, emptyWorkspace, restoreWorkspace } from "../workspace/state";
import { artifactEvents } from "./ArtifactView";
import type { TurnEvent } from "../types";

describe("document workspace", () => {
  const id = "a".repeat(32);
  it("opens, deduplicates and restores a document tab", () => {
    const state = openTab(emptyWorkspace(), { kind: "artifact", path: id, nonce: 1 });
    expect(openTab(state, { kind: "artifact", path: id, nonce: 2 }).tabs).toHaveLength(1);
    expect(restoreWorkspace(JSON.stringify(state), "chat", "http://localhost")).toEqual(state);
  });
  it("rejects URLs and traversal in saved document tabs", () => {
    for (const path of ["../secret", "https://example.org", "C:\\secret"]) {
      const state = openTab(emptyWorkspace(), { kind: "artifact", path, nonce: 1 });
      expect(restoreWorkspace(JSON.stringify(state), "chat", "http://localhost").tabs[0].kind).toBe("new");
    }
  });
  it("only exposes persisted successful document events", () => {
    const events = [{ type: "artifact.created", payload: { id } }, { type: "tool.failed", payload: { id } }, { type: "artifact.created", payload: { id: "../../bad" } }].map((event, index): TurnEvent => ({ ...event, id: index, turn_id: "turn", session_id: "chat", sequence: index, created_at: "2026-08-30" }));
    expect(artifactEvents(events)).toHaveLength(1);
  });
});
