/**
 * Maps every error code the API documents (plus client-side ones) to a friendly, translated
 * message. Unknown codes fall back to a generic message rather than showing raw server text.
 */
import type { Dictionary } from "@/i18n/en";
import { MAX_TEXT_CHARS } from "./config";
import { fmt } from "./format";

/** Every `error.code` the API can return (api/main.py, src/ocr/validate.py). */
export const API_ERROR_CODES = [
  "empty_text",
  "text_too_long",
  "too_large",
  "body_too_large",
  "unsupported_type",
  "corrupt",
  "too_small",
  "too_many_pixels",
  "empty",
  "no_text_found",
  "invalid_request",
  "length_required",
  "rate_limited",
  "busy",
  "timeout",
  "classifier_unavailable",
  "ocr_unavailable",
  "feedback_not_configured",
  "feedback_storage_error",
  "unknown_prediction",
  "internal_error",
] as const;

/** Codes produced in the browser: network failure, our own timeout, no API configured, unknown. */
export const CLIENT_ERROR_CODES = ["network_error", "client_timeout", "not_configured", "unknown_error", "demo_unavailable"] as const;

export type KnownErrorCode = (typeof API_ERROR_CODES)[number] | (typeof CLIENT_ERROR_CODES)[number];

const KNOWN_CODES: ReadonlySet<string> = new Set([...API_ERROR_CODES, ...CLIENT_ERROR_CODES]);

/** Only documented codes map to their message; anything else (even other dictionary keys) is unknown. */
const isKnown = (code: string): code is KnownErrorCode => KNOWN_CODES.has(code);

/** Friendly message for an error code. `retryAfterS` comes from the Retry-After header (429). */
export function errorMessage(code: string, t: Dictionary, retryAfterS: number | null = null): string {
  if (code === "rate_limited") {
    return retryAfterS !== null && retryAfterS > 0
      ? fmt(t.errors.rate_limited, { seconds: retryAfterS })
      : t.errors.rate_limited_generic;
  }
  if (code === "text_too_long") return fmt(t.errors.text_too_long, { max: MAX_TEXT_CHARS });
  return isKnown(code) ? t.errors[code] : t.errors.unknown_error;
}

/** Errors where trying the same request again later can succeed. */
export const isRetryable = (code: string): boolean =>
  ["rate_limited", "busy", "timeout", "client_timeout", "network_error", "internal_error", "feedback_storage_error"].includes(code);
