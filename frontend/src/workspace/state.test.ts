import { describe, expect, it } from "vitest";
import { closeTab, diffRows, emptyWorkspace, openTab, restoreWorkspace } from "./state";

describe("workspace tabs", () => {
  it("opens a named files tab and keeps it when a source file opens", () => {
    let state = openTab(emptyWorkspace(), { nonce: 1, kind: "files" });
    expect(state.tabs[0].title).toBe("Файлы проекта");
    state = openTab(state, { nonce: 2, kind: "file", path: "index.html" });
    expect(state.tabs.map(tab => tab.kind)).toEqual(["files", "file"]);
    state = openTab(state, { nonce: 3, kind: "files" });
    expect(state.tabs).toHaveLength(2);
    expect(state.activeId).toBe("files:");
  });
  it("replaces chooser, deduplicates files and selects neighbour after close", () => {
    let state = openTab(emptyWorkspace(), { nonce: 1, kind: "file", path: "src/app.js" });
    state = openTab(state, { nonce: 2, kind: "changes" });
    state = openTab(state, { nonce: 3, kind: "file", path: "src/app.js" });
    expect(state.tabs).toHaveLength(2);
    state = closeTab(state, state.activeId);
    expect(state.tabs[0].kind).toBe("changes");
    expect(state.activeId).toBe(state.tabs[0].id);
    expect(closeTab(state, state.activeId)).toEqual(emptyWorkspace());
  });
  it("restores only workspace-scoped preview URLs and relative files", () => {
    const tabs = [
      { id: "bad", kind: "preview", title: "bad", path: "/api/sessions/other/preview/index.html" },
      { id: "external", kind: "preview", title: "bad", path: "https://example.com/" },
      { id: "escape", kind: "file", title: "bad", path: "../secret" },
      { id: "safe", kind: "file", title: "app.js", path: "app.js" },
    ];
    expect(restoreWorkspace(JSON.stringify({ tabs, activeId: "bad" }), "ours", "http://localhost").tabs).toEqual([tabs[3]]);
    expect(restoreWorkspace("broken", "ours", "http://localhost")).toEqual(emptyWorkspace());
  });
  it("numbers old/new lines from actual unified diff hunks", () => {
    expect(diffRows("--- a/a\n+++ b/a\n@@ -2,2 +2,2 @@\n same\n-old\n+new")).toEqual([
      { kind: "hunk", text: "@@ -2,2 +2,2 @@", old: "", next: "" },
      { kind: "context", text: "same", old: "2", next: "2" },
      { kind: "remove", text: "old", old: "3", next: "" },
      { kind: "add", text: "new", old: "", next: "3" },
    ]);
  });
});
