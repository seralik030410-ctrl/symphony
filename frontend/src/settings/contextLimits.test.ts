import { describe, expect, it } from "vitest";
import { contextOptions, validContextBudget } from "./contextLimits";

describe("context settings", () => {
  it("keeps current non-preset values and deduplicates presets", () => {
    expect(contextOptions(16384, 65536)).toEqual([8192, 16384, 32768, 65536]);
    expect(contextOptions(12288, 65536)).toContain(12288);
    expect(contextOptions(16384, 4096)).toContain(4096);
  });
  it("accepts only whole output limits inside a known context limit", () => {
    expect(validContextBudget(32768, "4096", 65536)).toBe(true);
    for (const output of ["", "0", "63", "4.5", "NaN", "32768", "65537"]) {
      expect(validContextBudget(32768, output, 65536)).toBe(false);
    }
    expect(validContextBudget(32768, "4096", null)).toBe(false);
    expect(validContextBudget(32768, "4096", 16384)).toBe(false);
  });
});
