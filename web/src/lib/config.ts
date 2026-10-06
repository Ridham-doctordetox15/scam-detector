/**
 * Build-time configuration (see next.config.mjs). Both values are public and non-secret.
 *
 * API_URL empty => the backend is not hosted: the site runs in demo mode only.
 * To go live later: set NEXT_PUBLIC_API_URL and rebuild - nothing else changes.
 */
export const API_URL: string = (process.env.SCAM_API_URL ?? "").replace(/\/+$/, "");
export const BASE_PATH: string = process.env.SCAM_BASE_PATH ?? "";

export const isBackendConfigured = (apiUrl: string = API_URL): boolean => apiUrl.length > 0;

/** Path to a file in public/, honouring the base path (GitHub Pages project sites). */
export const assetPath = (path: string): string => `${BASE_PATH}${path.startsWith("/") ? path : `/${path}`}`;

/** GitHub repository (NEXT_PUBLIC_REPO_URL). Empty = the About page shows no repo link. */
export const REPO_URL: string = process.env.SCAM_REPO_URL ?? "";

// Client-side limits mirror the API's (the API still enforces its own).
export const MAX_TEXT_CHARS = 5000;
export const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
export const HEALTH_TIMEOUT_MS = 4000;
export const TEXT_TIMEOUT_MS = 30_000;
export const IMAGE_TIMEOUT_MS = 60_000;
export const FEEDBACK_TIMEOUT_MS = 10_000;
