import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// Parses the colour tokens from globals.css (:root = light, .dark = dark) and checks WCAG contrast:
// 4.5:1 for text (AA, normal size) and 3:1 for graphics and control borders (WCAG 1.4.11).
const css = readFileSync(join(__dirname, "..", "app", "globals.css"), "utf-8");

function block(selector: string): string {
  const start = css.indexOf(`${selector} {`);
  if (start < 0) throw new Error(`no ${selector} block`);
  return css.slice(start, css.indexOf("\n}\n", start));
}

function tokens(text: string): Record<string, string> {
  return Object.fromEntries([...text.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)].map((m) => [m[1]!, m[2]!]));
}

const THEMES = { light: tokens(block(":root")), dark: tokens(block(".dark")) };

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = Number.parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
}

const SURFACES = ["background", "card", "subtle"];
const RISKS = ["low", "medium", "high"];

const TEXT_PAIRS: [string, string][] = [
  ...SURFACES.flatMap((s) => [["foreground", s], ["muted-foreground", s], ["primary", s]] as [string, string][]),
  ["foreground", "muted"],
  ["muted-foreground", "muted"],
  ["card-foreground", "card"],
  ["popover-foreground", "popover"],
  ["primary-foreground", "primary"],
  ["secondary-foreground", "secondary"],
  ["accent-foreground", "accent"],
  ["destructive", "card"],
  ["destructive", "background"],
  ...RISKS.flatMap((r) =>
    [[`risk-${r}-fg`, `risk-${r}-bg`], ...SURFACES.map((s) => [`risk-${r}-fg`, s])] as [string, string][],
  ),
  ["foreground", "risk-medium-bg"], // demo banner body text
  ["foreground", "risk-high-bg"], // error card body text
];

const GRAPHIC_PAIRS: [string, string][] = [
  ...RISKS.flatMap((r) => [[`risk-${r}-solid`, "card"], [`risk-${r}-solid`, "background"]] as [string, string][]),
  ["input", "card"], // text field and drop-zone borders
  ["ring", "card"], // focus ring
  ["ring", "background"],
];

describe.each(Object.entries(THEMES))("%s theme", (_name, theme) => {
  it("defines every token used in the checks", () => {
    for (const [fg, bg] of [...TEXT_PAIRS, ...GRAPHIC_PAIRS]) {
      expect(theme[fg], fg).toBeDefined();
      expect(theme[bg], bg).toBeDefined();
    }
  });

  it.each(TEXT_PAIRS)("text %s on %s meets WCAG AA (4.5:1)", (fg, bg) => {
    expect(contrast(theme[fg]!, theme[bg]!)).toBeGreaterThanOrEqual(4.5);
  });

  it.each(GRAPHIC_PAIRS)("graphic %s on %s meets 3:1", (fg, bg) => {
    expect(contrast(theme[fg]!, theme[bg]!)).toBeGreaterThanOrEqual(3);
  });
});

describe("Devanagari typography rules", () => {
  it("never redefines next/font's --font-deva variable (a self-reference would wipe it out)", () => {
    expect(css).not.toMatch(/--font-deva:\s*var\(--font-deva/);
  });

  it("applies the Devanagari font and 1.75 line height outside Tailwind's layers, by nearest language", () => {
    const rule = css.match(/:lang\(hi\):not\(:lang\(hi-Latn\)\)\s*\{([^}]*)\}/);
    expect(rule?.[1]).toMatch(/font-family:\s*var\(--font-devanagari\)/);
    expect(rule?.[1]).toMatch(/line-height:\s*1\.75/);
    // Unlayered: the rule must not sit inside an @layer block.
    const before = css.slice(0, css.indexOf(rule![0]));
    const opened = (before.match(/@layer\s+\w+\s*\{/g) ?? []).length;
    const depth = [...before].reduce((d, ch) => d + (ch === "{" ? 1 : ch === "}" ? -1 : 0), 0);
    expect(opened > 0 ? depth : 0).toBe(0);
  });
});
