import { MAX_IMAGE_BYTES } from "./config";

export const ACCEPTED_IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp"] as const;

/** Error code (same vocabulary as the API) or null if the file may be uploaded. The API re-checks. */
export function validateImageFile(file: { type: string; size: number }): "unsupported_type" | "too_large" | "empty" | null {
  if (file.size === 0) return "empty";
  if (!(ACCEPTED_IMAGE_TYPES as readonly string[]).includes(file.type)) return "unsupported_type";
  if (file.size > MAX_IMAGE_BYTES) return "too_large";
  return null;
}
