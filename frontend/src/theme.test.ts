import { describe, expect, it } from "vitest";
import { createThemeStore, parseTheme, type ThemeEnvironment } from "./theme";

function fixture(stored: string | null = null, system = false) {
  const applied: string[] = [], written: string[] = [];
  let onSystem = () => {}, onStorage = (_value: string | null) => {};
  const env: ThemeEnvironment = {
    read: () => stored, write: value => { written.push(value); }, systemDark: () => system,
    apply: value => { applied.push(value); },
    watchSystem: callback => { onSystem = callback; return () => { onSystem = () => {}; }; },
    watchStorage: callback => { onStorage = callback; return () => { onStorage = () => {}; }; },
  };
  return { env, applied, written, os: (dark: boolean) => { system = dark; onSystem(); }, storage: (value: string | null) => onStorage(value) };
}

describe("application theme", () => {
  it("defaults to the OS and follows changes without persisting a manual choice", () => {
    const f = fixture(null, true), store = createThemeStore(f.env);
    expect(store.getSnapshot()).toBe("system");
    f.os(false); expect(f.applied).toEqual(["dark", "light"]); expect(f.written).toEqual([]);
    store.dispose(); f.os(true); expect(f.applied).toHaveLength(2);
  });
  it("restores explicit preference, ignores OS changes until switched back", () => {
    const f = fixture("light", true), store = createThemeStore(f.env);
    f.os(true); expect(f.applied).toEqual(["light"]);
    store.set("system"); expect(f.applied.at(-1)).toBe("dark");
    expect(f.written).toEqual(["system"]);
  });
  it("updates subscribers on cross-window changes and clearing storage", () => {
    const f = fixture("dark"), store = createThemeStore(f.env);
    const seen: string[] = []; const stop = store.subscribe(() => seen.push(store.getSnapshot()));
    f.storage("light"); f.storage("light"); f.storage(null);
    expect(seen).toEqual(["light", "system"]); expect(f.written).toEqual([]);
    stop(); f.storage("dark"); expect(seen).toHaveLength(2);
  });
  it("still starts and switches when webview storage is unavailable", () => {
    const f = fixture(null, true);
    f.env.read = () => { throw new Error("denied"); }; f.env.write = () => { throw new Error("quota"); };
    const store = createThemeStore(f.env); store.set("light");
    expect(f.applied).toEqual(["dark", "light"]); expect(store.getSnapshot()).toBe("light");
  });
  it("normalizes corrupt preferences to system", () => {
    for (const value of [undefined, "LIGHT", "", "<script>", 4]) expect(parseTheme(value)).toBe("system");
  });
});
