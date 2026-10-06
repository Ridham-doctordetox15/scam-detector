import { describe, expect, it } from "vitest";
import { MAX_IMAGE_BYTES } from "./config";
import { validateImageFile } from "./validateImage";

describe("client-side screenshot validation", () => {
  it.each(["image/png", "image/jpeg", "image/webp"])("accepts %s", (type) => {
    expect(validateImageFile({ type, size: 1000 })).toBeNull();
  });

  it.each(["image/gif", "image/svg+xml", "application/pdf", "text/plain", ""])("rejects %j as unsupported_type", (type) => {
    expect(validateImageFile({ type, size: 1000 })).toBe("unsupported_type");
  });

  it("allows exactly 5 MB and rejects one byte more", () => {
    expect(validateImageFile({ type: "image/png", size: MAX_IMAGE_BYTES })).toBeNull();
    expect(validateImageFile({ type: "image/png", size: MAX_IMAGE_BYTES + 1 })).toBe("too_large");
  });

  it("rejects empty files", () => {
    expect(validateImageFile({ type: "image/png", size: 0 })).toBe("empty");
  });
});
