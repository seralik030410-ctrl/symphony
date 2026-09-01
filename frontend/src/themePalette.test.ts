import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { describe, expect, it } from "vitest";

const css = readFileSync(new URL("./theme.css", import.meta.url), "utf8");
const definitions = (block: string) => Object.fromEntries([...block.matchAll(/--([\w-]+):\s*([^;]+);/g)].map(m => [m[1], m[2]]));
const light = definitions(css.match(/:root \{([^}]+)\}/)![1]);
const dark = { ...light, ...definitions(css.match(/:root\[data-theme="dark"\] \{([^}]+)\}/)![1]) };

// WCAG relative luminance; OKLCH -> linear sRGB (CSS Color 4 matrix).
function luminance(value: string) {
  if (value.startsWith("#")) {
    const hex = value.length === 4 ? value.slice(1).split("").map(c => c + c).join("") : value.slice(1);
    const rgb = [0, 2, 4].map(i => parseInt(hex.slice(i, i + 2), 16) / 255).map(c => c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4);
    return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
  }
  const [L, C, h] = value.match(/[\d.]+/g)!.map(Number), angle = h * Math.PI / 180;
  const a = C * Math.cos(angle), b = C * Math.sin(angle);
  const l = (L + .3963377774 * a + .2158037573 * b) ** 3;
  const m = (L - .1055613458 * a - .0638541728 * b) ** 3;
  const s = (L - .0894841775 * a - 1.291485548 * b) ** 3;
  const rgb = [4.0767416621 * l - 3.3077115913 * m + .2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - .3413193965 * s, -.0041960863 * l - .7034186147 * m + 1.707614701 * s].map(c => Math.max(0, Math.min(1, c)));
  return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
}

describe("theme palette and first paint", () => {
  for (const [name, palette] of Object.entries({ light, dark })) {
    it(`${name}: text, status, syntax and button labels remain readable`, () => {
      const pairs = ["text/surface", "text-secondary/surface", "muted/raised", "muted/rail", "accent/surface", "link/surface", "success/success-surface", "danger/danger-surface", "warning/warning-surface", "syntax-keyword/surface", "syntax-string/surface", "syntax-number/surface", "success/diff-add", "danger/diff-remove", "on-accent/accent-fill", "on-primary/primary-fill", "paper/danger-fill", "paper/link-fill", "code-text/code-surface"];
      for (const pair of pairs) {
        const [a, b] = pair.split("/").map(key => luminance(palette[key]));
        expect((Math.max(a, b) + .05) / (Math.min(a, b) + .05), `${name} ${pair}`).toBeGreaterThanOrEqual(4.5);
      }
    });
  }
  it("defines every semantic variable referenced by component styles", () => {
    for (const file of ["styles.css", "panels.css", "workspace/workspace.css", "settings/settings.css"]) {
      const source = readFileSync(new URL(file, import.meta.url), "utf8");
      for (const m of source.matchAll(/var\(--([\w-]+)\)/g)) expect(light, `${file}: ${m[1]}`).toHaveProperty(m[1]);
    }
  });
  it("early bootstrap restores theme even with blocked storage", () => {
    const script = readFileSync(new URL("../public/theme-init.js", import.meta.url), "utf8");
    for (const [saved, system, expected] of [["light", true, "light"], ["dark", false, "dark"], ["invalid", true, "dark"], [null, false, "light"]] as const) {
      const document = { documentElement: { dataset: {} as Record<string, string>, style: {} }, querySelector: () => null };
      runInNewContext(script, { document, matchMedia: () => ({ matches: system }), localStorage: { getItem: () => { if (saved === null) throw Error("denied"); return saved; } } });
      expect(document.documentElement.dataset.theme).toBe(expected);
    }
  });
});
