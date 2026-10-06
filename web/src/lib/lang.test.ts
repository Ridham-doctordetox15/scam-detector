import { describe, expect, it } from "vitest";
import { contentLangAttr, guessLangAttr, usesDevanagari } from "./lang";

describe("content language mapping", () => {
  it.each([
    ["en", "en", false],
    ["hi", "hi", true],
    ["hinglish", "hi-Latn", false],
  ] as const)("maps %s to lang=%s (Devanagari typography: %s)", (language, attr, deva) => {
    expect(contentLangAttr(language)).toBe(attr);
    expect(usesDevanagari(language)).toBe(deva);
  });

  it("guesses Hindi only when there is Devanagari text", () => {
    expect(guessLangAttr("प्रिय ग्राहक, KYC अपडेट करें")).toBe("hi");
    expect(guessLangAttr("Aapka bijli connection kat jayega")).toBe("en");
  });
});
