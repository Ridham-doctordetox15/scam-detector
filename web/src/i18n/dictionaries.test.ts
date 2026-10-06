import { describe, expect, it } from "vitest";
import { en } from "./en";
import { hi } from "./hi";

type Tree = { [key: string]: Tree | string | string[] };

/** Every leaf path with its value, e.g. ["result.verdict.safe", "Looks safe"]. */
function leaves(tree: Tree, prefix = ""): [string, string | string[]][] {
  return Object.entries(tree).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return typeof value === "string" || Array.isArray(value) ? [[path, value] as [string, string | string[]]] : leaves(value, path);
  });
}

const placeholders = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe("interface dictionaries", () => {
  const enLeaves = new Map(leaves(en as unknown as Tree));
  const hiLeaves = new Map(leaves(hi as unknown as Tree));

  it("have exactly the same keys", () => {
    const missingInHi = [...enLeaves.keys()].filter((k) => !hiLeaves.has(k));
    const missingInEn = [...hiLeaves.keys()].filter((k) => !enLeaves.has(k));
    expect(missingInHi).toEqual([]);
    expect(missingInEn).toEqual([]);
  });

  it("have no empty strings and the same list lengths", () => {
    for (const [key, enValue] of enLeaves) {
      const hiValue = hiLeaves.get(key)!;
      if (Array.isArray(enValue)) {
        expect(Array.isArray(hiValue), key).toBe(true);
        expect((hiValue as string[]).length, key).toBe(enValue.length);
        for (const item of [...enValue, ...(hiValue as string[])]) expect(item.trim(), key).not.toBe("");
      } else {
        expect(enValue.trim(), key).not.toBe("");
        expect((hiValue as string).trim(), key).not.toBe("");
      }
    }
  });

  it("use the same {placeholders} in both languages", () => {
    for (const [key, enValue] of enLeaves) {
      if (typeof enValue !== "string") continue;
      expect(placeholders(hiLeaves.get(key) as string), key).toEqual(placeholders(enValue));
    }
  });

  it("keep the same numbers in the About findings (no translation drift)", () => {
    const numbers = (s: string) => (s.match(/[+-]?\d[\d,]*(?:\.\d+)?%?/g) ?? []).sort();
    for (const key of Object.keys(en.about.findings) as (keyof typeof en.about.findings)[]) {
      expect(numbers(hi.about.findings[key]), key).toEqual(numbers(en.about.findings[key]));
    }
  });

  it("write the Hindi interface in Devanagari", () => {
    const devanagari = /[ऀ-ॿ]/;
    for (const text of [hi.form.heading, hi.result.redFlags, hi.about.title, hi.mode.notHostedTitle]) {
      expect(text).toMatch(devanagari);
    }
  });
});
