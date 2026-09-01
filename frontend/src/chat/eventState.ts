import type { Message, Turn, TurnEvent, TurnStatus } from "../types";

const finalEventStatus: Record<string, TurnStatus | undefined> = {
  "turn.completed": "completed",
  "turn.failed": "failed",
  "turn.cancelled": "cancelled",
  "turn.interrupted": "interrupted",
};

export function applyTurnEvent(
  messages: Message[],
  turns: Turn[],
  event: TurnEvent,
): { messages: Message[]; turns: Turn[] } {
  const turn = turns.find((item) => item.id === event.turn_id);
  if (!turn) return { messages, turns };

  let nextMessages = messages;
  if (event.type === "model.delta" && typeof event.payload.delta === "string") {
    nextMessages = messages.map((message) =>
      message.id === turn.assistant_message_id
        ? { ...message, content: message.content + event.payload.delta }
        : message,
    );
  }

  const finalStatus = finalEventStatus[event.type];
  const streamingStatus: TurnStatus | undefined =
    event.type === "model.started"
      ? "model_running"
      : event.type === "context.built"
        ? "preparing"
        : undefined;
  const status = finalStatus ?? streamingStatus;
  const nextTurns = status
    ? turns.map((item) =>
        item.id === event.turn_id
          ? { ...item, status, last_event_sequence: event.sequence }
          : item,
      )
    : turns.map((item) =>
        item.id === event.turn_id
          ? { ...item, last_event_sequence: event.sequence }
          : item,
      );
  if (finalStatus) {
    nextMessages = nextMessages.map((message) =>
      message.id === turn.assistant_message_id
        ? {
            ...message,
            status:
              finalStatus === "completed"
                ? "complete"
                : finalStatus === "cancelled"
                  ? "cancelled"
                  : "failed",
          }
        : message,
    );
  }
  return { messages: nextMessages, turns: nextTurns };
}

export function isFinalEvent(event: TurnEvent): boolean {
  return event.type in finalEventStatus;
}

