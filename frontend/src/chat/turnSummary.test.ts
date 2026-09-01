import { describe, expect, it } from "vitest";
import { summarizeTurn } from "./turnSummary";
import type { Turn, TurnEvent } from "../types";

const turn = { status: "model_running" } as Turn;
function event(type: string, payload: Record<string, unknown> = {}): TurnEvent {
  return { type, payload } as TurnEvent;
}

describe("turn presentation", () => {
  it("uses the latest step instead of any earlier answer to name the active stage", () => {
    const events = [event("model.started"), event("model.delta", { delta: "Answer" }),
      event("tool.started"), event("model.started"), event("model.reasoning_delta", { delta: "Thinking" })];
    expect(summarizeTurn(turn, events)).toMatchObject({ stage: "Думает…", modelSteps: 2, reasoning: "Thinking" });
    expect(summarizeTurn(turn, [...events, event("approval.requested")]).stage).toBe("Нужно разрешение");
  });

  it("sums usage across model calls but uses only the latest input as context", () => {
    const summary = summarizeTurn(turn, [event("context.built", { estimated_tokens: 90, context_window: 16384 }),
      event("model.usage", { input_tokens: 123, output_tokens: 45, reasoning_tokens: 12 }),
      event("model.usage", { input_tokens: 234, output_tokens: 56, reasoning_tokens: 9 })]);
    expect(summary).toMatchObject({ inputTokens: 357, outputTokens: 101, reasoningTokens: 21,
      contextUsed: 234, contextWindow: 16384, estimated: false, hasUsage: true });
  });

  it("distinguishes zero usage from unknown and approximate values", () => {
    expect(summarizeTurn(turn, [event("context.built", { estimated_tokens: 99 })]))
      .toMatchObject({ hasUsage: false, estimated: true, contextUsed: 99, reasoningTokens: null });
    expect(summarizeTurn(turn, [event("model.usage", { input_tokens: 0, output_tokens: 0 })]))
      .toMatchObject({ hasUsage: true, estimated: false, contextUsed: 0 });
  });

  it("includes memory-model usage without confusing it with the active context", () => {
    const summary = summarizeTurn(turn, [
      event("memory.snapshot", { input_tokens: 1100, output_tokens: 90 }),
      event("context.built", { estimated_tokens: 180, context_window: 16384 }),
      event("model.usage", { input_tokens: 200, output_tokens: 30 }),
    ]);
    expect(summary).toMatchObject({ inputTokens: 1300, outputTokens: 120,
      contextUsed: 200, contextWindow: 16384, estimated: false });
  });

  it("stops the progress state for all terminal statuses", () => {
    for (const status of ["completed", "cancelled", "failed", "interrupted"] as const) {
      expect(summarizeTurn({ ...turn, status }, []).active).toBe(false);
    }
  });
});
