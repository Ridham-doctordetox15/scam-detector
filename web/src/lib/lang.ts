import type { ContentLanguage } from "./types";

/**
 * BCP 47 tag for result content, from the API's `language` field.
 * Hinglish is Hindi written in Latin script: "hi-Latn" (correct for screen readers and
 * hyphenation, and it keeps the Latin font rather than the Devanagari line-height rules).
 */
export function contentLangAttr(language: ContentLanguage): string {
  switch (language) {
    case "hi":
      return "hi";
    case "hinglish":
      return "hi-Latn";
    default:
      return "en";
  }
}

/** True for text that should get Devanagari typography (font + taller line height). */
export const usesDevanagari = (language: ContentLanguage): boolean => language === "hi";

const DEVANAGARI_RE = /[ऀ-ॿ]/;

/** Language tag for arbitrary text we did not get a language for (e.g. extracted OCR text). */
export function guessLangAttr(text: string): string {
  return DEVANAGARI_RE.test(text) ? "hi" : "en";
}
