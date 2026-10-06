import { describe, expect, it } from "vitest";
import { DEMO, demoRecordedDate, DemoUnavailableError, getDemoResponse, hasDemoResponse } from "./demo";
import { ALL_SAMPLES, TEXT_SAMPLES } from "./samples";

describe("demo recordings", () => {
  it("exist for every sample, and only for samples", () => {
    expect(Object.keys(DEMO.responses).sort()).toEqual(ALL_SAMPLES.map((s) => s.id).sort());
  });

  it("are real API responses with the language field and the right input type", () => {
    for (const sample of ALL_SAMPLES) {
      const r = getDemoResponse(sample.id);
      expect(["en", "hi", "hinglish"], sample.id).toContain(r.language);
      expect(r.input_type).toBe(sample.kind);
      expect(r.prediction_id).toMatch(/^[0-9a-f-]{36}$/);
      if (sample.kind === "image") expect(r.ocr?.extracted_text.length).toBeGreaterThan(0);
    }
  });

  it("include a Devanagari text sample answered in Hindi", () => {
    const hindi = TEXT_SAMPLES.find((s) => /[ऀ-ॿ]/.test(s.text));
    expect(hindi).toBeDefined();
    expect(getDemoResponse(hindi!.id).language).toBe("hi");
  });

  it("have a recording date", () => {
    expect(demoRecordedDate()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});

describe("getDemoResponse refuses anything that isn't a recorded sample", () => {
  it.each([
    "my own message",
    "Dear customer, your KYC is not updated.",
    "",
    "__proto__",
    "constructor",
    "toString",
    "hasOwnProperty",
  ])("refuses %j", (input) => {
    expect(() => getDemoResponse(input)).toThrow(DemoUnavailableError);
    expect(hasDemoResponse(input)).toBe(false);
  });

  it("does not match sample text, only sample ids", () => {
    const sample = TEXT_SAMPLES[0]!;
    expect(() => getDemoResponse(sample.text)).toThrow(DemoUnavailableError);
    expect(getDemoResponse(sample.id).input_type).toBe("text");
  });
});
