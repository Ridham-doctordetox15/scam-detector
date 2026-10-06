import { describe, expect, it } from "vitest";
import { buildCsp } from "./csp";

const directives = (csp: string) => new Map(csp.split(";").map((d) => d.trim().split(/\s+/)).map(([name, ...values]) => [name!, values]));

describe("Content-Security-Policy", () => {
  it("lets the page connect only to itself and the configured API origin", () => {
    const csp = directives(buildCsp("https://me-scam-api.hf.space"));
    expect(csp.get("connect-src")).toEqual(["'self'", "https://me-scam-api.hf.space"]);
  });

  it("allows only same-origin connections when no API is configured (demo-only build)", () => {
    expect(directives(buildCsp("")).get("connect-src")).toEqual(["'self'"]);
  });

  it("blocks plugins, form posts and base-tag hijacking", () => {
    const csp = directives(buildCsp("https://x.test"));
    expect(csp.get("object-src")).toEqual(["'none'"]);
    expect(csp.get("form-action")).toEqual(["'none'"]);
    expect(csp.get("base-uri")).toEqual(["'self'"]);
    expect(csp.get("font-src")).toEqual(["'self'"]);
  });

  it("never allows wildcard connections", () => {
    expect(buildCsp("https://x.test")).not.toMatch(/connect-src[^;]*\*/);
  });
});
