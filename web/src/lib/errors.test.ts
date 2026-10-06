import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { en } from "@/i18n/en";
import { hi } from "@/i18n/hi";
import { API_ERROR_CODES, CLIENT_ERROR_CODES, errorMessage } from "./errors";

const DICTS = { en, hi };

describe("errorMessage", () => {
  it.each(Object.entries(DICTS))("has a specific %s message for every documented API and client error code", (_lang, t) => {
    for (const code of [...API_ERROR_CODES, ...CLIENT_ERROR_CODES]) {
      const message = errorMessage(code, t, 5);
      expect(message.trim(), code).not.toBe("");
      if (code !== "unknown_error") expect(message, code).not.toBe(t.errors.unknown_error);
      expect(message, `${code} has an unfilled placeholder`).not.toMatch(/\{\w+\}/);
    }
  });

  it("uses the Retry-After seconds when present", () => {
    expect(errorMessage("rate_limited", en, 42)).toContain("42 seconds");
    expect(errorMessage("rate_limited", hi, 42)).toContain("42");
  });

  it("falls back to a generic rate-limit message without Retry-After", () => {
    expect(errorMessage("rate_limited", en, null)).toBe(en.errors.rate_limited_generic);
  });

  it("fills in the text limit", () => {
    expect(errorMessage("text_too_long", en)).toContain("5000");
  });

  it("maps unknown or hostile codes to the generic message", () => {
    for (const code of ["teapot", "__proto__", "constructor", "toString", "heading", "requestId", "rate_limited_generic"]) {
      expect(errorMessage(code, en)).toBe(en.errors.unknown_error);
    }
  });

  it("covers every error code the API source can raise", () => {
    // Guard against the backend adding a code the UI doesn't know about.
    const root = join(__dirname, "..", "..", "..");
    const source = ["api/main.py", "src/ocr/validate.py"].map((p) => readFileSync(join(root, p), "utf-8")).join("\n");
    const raised = new Set<string>();
    for (const m of source.matchAll(/APIError\(\s*\d+,\s*"([a-z_]+)"/g)) raised.add(m[1]!);
    for (const m of source.matchAll(/_error_response\(request,\s*\d+,\s*"([a-z_]+)"/g)) raised.add(m[1]!);
    for (const m of source.matchAll(/InvalidImageError\(\s*"([a-z_]+)"/g)) raised.add(m[1]!);
    for (const m of source.matchAll(/ServiceUnavailable\("([a-z_]+)"\)/g)) raised.add(`${m[1]!}_unavailable`);
    const services = readFileSync(join(root, "api/services.py"), "utf-8");
    for (const m of services.matchAll(/ServiceUnavailable\("([a-z_]+)"\)/g)) raised.add(`${m[1]!}_unavailable`);
    expect(raised.size).toBeGreaterThan(15);
    for (const code of raised) expect(API_ERROR_CODES as readonly string[], code).toContain(code);
  });
});
