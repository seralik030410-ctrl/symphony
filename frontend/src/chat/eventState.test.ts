import { describe, expect, it } from "vitest";

import { applyTurnEvent } from "./eventState";
import type { Message, Turn, TurnEvent } from "../types";

const message: Message = {
  id: "assistant",
  session_id: "session-a",
  turn_id: "turn-a",
  role: "assistant",
  content: "Привет",
  status: "streaming",
  created_at: "2026-08-29T00:00:00Z",
  updated_at: "2026-08-29T00:00:00Z",
};

const turn: Turn = {
  id: "turn-a",
  session_id: "session-a",
  user_message_id: "user",
  assistant_message_id: "assistant",
  status: "model_running",
  provider: "ollama",
  model: "test",
  request_id: "request",
  error: null,
  cancel_requested: false,
  created_at: "2026-08-29T00:00:00Z",
  started_at: null,
  finished_at: null,
  last_event_sequence: 2,
};

it("applies model deltas only to the turn assistant message", () => {
  const event: TurnEvent = {
    id: 3,
    turn_id: "turn-a",
    session_id: "session-a",
    sequence: 3,
    type: "model.delta",
    payload: { delta: ", мир" },
    created_at: "2026-08-29T00:00:01Z",
  };
  const state = applyTurnEvent([message], [turn], event);
  expect(state.messages[0].content).toBe("Привет, мир");
  expect(state.turns[0].last_event_sequence).toBe(3);
});

describe("final events", () => {
  it("marks a cancelled assistant message without removing partial text", () => {
    const event: TurnEvent = {
      id: 4,
      turn_id: "turn-a",
      session_id: "session-a",
      sequence: 4,
      type: "turn.cancelled",
      payload: {},
      created_at: "2026-08-29T00:00:02Z",
    };
    const state = applyTurnEvent([message], [turn], event);
    expect(state.messages[0]).toMatchObject({ content: "Привет", status: "cancelled" });
    expect(state.turns[0].status).toBe("cancelled");
  });
});

