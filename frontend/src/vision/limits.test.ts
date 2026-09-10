import { describe, expect, it } from "vitest";
import { selectedFrameLimitError } from "./limits";

describe("vision selection limits", () => {
  it("allows a replacement after a retained frame is deselected", () => {
    expect(selectedFrameLimitError(1, 1)).toBeTruthy();
    expect(selectedFrameLimitError(0, 1)).toBeNull();
  });
});
