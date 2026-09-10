import type { VoiceState } from "../types";

export type VoiceAction =
  | { type: "connected" }
  | { type: "state"; state: VoiceState }
  | { type: "transcript"; text: string }
  | { type: "error"; message: string }
  | { type: "reset" };

export interface VoiceViewState { state: VoiceState; transcript: string; error: string }

export const initialVoiceState: VoiceViewState = { state: "idle", transcript: "", error: "" };

export function voiceReducer(current: VoiceViewState, action: VoiceAction): VoiceViewState {
  if (action.type === "reset" || action.type === "connected") return initialVoiceState;
  if (action.type === "state") return { ...current, state: action.state, error: action.state === "error" ? current.error : "" };
  if (action.type === "transcript") return { ...current, transcript: action.text };
  return { ...current, state: "error", error: action.message };
}

