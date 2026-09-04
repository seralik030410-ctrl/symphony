import { describe, expect, it } from "vitest";
import { contextOptions, validContextBudget } from "./contextLimits";

describe("context settings", () => {
  it("includes all standard presets up to maximum", () => {
    expect(contextOptions(16384, 65536)).toEqual([8192, 16384, 32768, 65536, 131072, 262144, 524288, 1048576]);
    expect(contextOptions(12288, 65536)).toContain(12288);
    expect(contextOptions(16384, 4096)).toContain(4096);
  });
  it("includes 128K and 256K presets", () => {
    const opts = contextOptions(16384, 131072);
    expect(opts).toContain(131072);
    expect(opts).toContain(65536);
    expect(opts).toContain(32768);
  });
  it("includes the model maximum if it is not a standard preset", () => {
    const opts = contextOptions(16384, 100000);
    expect(opts).toContain(100000);
  });
  it("accepts only whole output limits inside a known context limit", () => {
    expect(validContextBudget(32768, "4096", 65536)).toBe(true);
    for (const output of ["", "0", "63", "4.5", "NaN", "32768"]) {
      expect(validContextBudget(32768, output, 65536)).toBe(false);
    }
    expect(validContextBudget(32768, "4096", null)).toBe(false);
    expect(validContextBudget(32768, "4096", 16384)).toBe(false);
  });
  it("allows output larger than 65536 when window is bigger", () => {
    expect(validContextBudget(131072, "100000", 131072)).toBe(true);
    expect(validContextBudget(262144, "131072", 262144)).toBe(true);
  });
});
