import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";


afterEach(() => vi.unstubAllGlobals());


describe("Stage 20 API contracts", () => {
  it("encodes history queries and keeps returned message text as data", async () => {
    const result = {
      query: "чат & отчёт",
      results: [{
        message_id: "message-1", session_id: "session-1", turn_id: "turn-1",
        role: "assistant", session_title: "Финансы", snippet: "<script>данные</script>",
        created_at: "2026-09-10T00:00:00Z", rank: -1,
      }],
    };
    const fetch = vi.fn(async () => new Response(JSON.stringify(result), {
      status: 200, headers: { "content-type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetch);

    await expect(api.searchHistory("чат & отчёт", 7)).resolves.toEqual(result);
    expect(fetch).toHaveBeenCalledWith(
      "/api/search/history?q=%D1%87%D0%B0%D1%82%20%26%20%D0%BE%D1%82%D1%87%D1%91%D1%82&limit=7",
      expect.any(Object),
    );
  });

  it("acknowledges a heartbeat event through its scoped endpoint", async () => {
    const event = {
      id: "event-1", watch_id: "watch-1", sequence: 1, task_id: "task-1",
      session_id: "session-1", type: "stalled", payload: {},
      created_at: "2026-09-10T00:00:00Z", acknowledged_at: "2026-09-10T00:01:00Z",
    };
    const fetch = vi.fn(async () => new Response(JSON.stringify(event), {
      status: 200, headers: { "content-type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetch);

    await expect(api.acknowledgeAgentHeartbeatEvent("event-1")).resolves.toEqual(event);
    expect(fetch).toHaveBeenCalledWith(
      "/api/agents/heartbeat-events/event-1/acknowledge",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
