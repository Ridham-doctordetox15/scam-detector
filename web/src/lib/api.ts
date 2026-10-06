/**
 * The only network code in the app. It talks to our API and nothing else - never to Supabase
 * or an LLM provider directly - and sends no credentials of any kind.
 */
import {
  API_URL,
  FEEDBACK_TIMEOUT_MS,
  HEALTH_TIMEOUT_MS,
  IMAGE_TIMEOUT_MS,
  TEXT_TIMEOUT_MS,
} from "./config";
import type { AnalyzeResponse, HealthResponse, UserVerdict } from "./types";

/** Client-side error codes, in addition to the API's own `error.code` values. */
export type ClientErrorCode = "network_error" | "client_timeout" | "not_configured" | "unknown_error";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly requestId: string | null;
  readonly retryAfterS: number | null;

  constructor(code: string, status: number, message: string, requestId: string | null = null,
              retryAfterS: number | null = null) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.requestId = requestId;
    this.retryAfterS = retryAfterS;
  }
}

interface RequestOptions {
  method?: "GET" | "POST";
  body?: BodyInit;
  headers?: Record<string, string>;
  timeoutMs: number;
  apiUrl?: string;
  fetchImpl?: typeof fetch;
}

async function request<T>(path: string, opts: RequestOptions): Promise<{ data: T; status: number }> {
  const base = opts.apiUrl ?? API_URL;
  if (!base) throw new ApiError("not_configured", 0, "No API URL configured");
  const doFetch = opts.fetchImpl ?? fetch;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), opts.timeoutMs);
  let response: Response;
  try {
    response = await doFetch(`${base}${path}`, {
      method: opts.method ?? "GET",
      body: opts.body,
      headers: opts.headers,
      signal: controller.signal,
      credentials: "omit",
      cache: "no-store",
      referrerPolicy: "no-referrer",
    });
  } catch (err) {
    if (controller.signal.aborted) throw new ApiError("client_timeout", 0, "Request timed out");
    throw new ApiError("network_error", 0, err instanceof Error ? err.message : "Network error");
  } finally {
    clearTimeout(timer);
  }

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const err = (payload as { error?: { code?: string; message?: string; request_id?: string } } | null)?.error;
    const retry = Number.parseInt(response.headers.get("Retry-After") ?? "", 10);
    throw new ApiError(
      err?.code ?? "unknown_error",
      response.status,
      err?.message ?? `HTTP ${response.status}`,
      err?.request_id ?? response.headers.get("X-Request-ID"),
      Number.isFinite(retry) ? retry : null,
    );
  }
  return { data: payload as T, status: response.status };
}

export async function analyzeText(text: string, opts: Partial<RequestOptions> = {}): Promise<AnalyzeResponse> {
  const { data } = await request<AnalyzeResponse>("/analyze/text", {
    method: "POST",
    body: JSON.stringify({ text }),
    headers: { "Content-Type": "application/json" },
    timeoutMs: TEXT_TIMEOUT_MS,
    ...opts,
  });
  return data;
}

export async function analyzeImage(file: Blob, filename = "screenshot.png",
                                   opts: Partial<RequestOptions> = {}): Promise<AnalyzeResponse> {
  const form = new FormData();
  form.append("file", file, filename);
  const { data } = await request<AnalyzeResponse>("/analyze/image", {
    method: "POST",
    body: form,
    timeoutMs: IMAGE_TIMEOUT_MS,
    ...opts,
  });
  return data;
}

export async function sendFeedback(predictionId: string, userVerdict: UserVerdict,
                                   opts: Partial<RequestOptions> = {}): Promise<void> {
  await request("/feedback", {
    method: "POST",
    body: JSON.stringify({ prediction_id: predictionId, user_verdict: userVerdict }),
    headers: { "Content-Type": "application/json" },
    timeoutMs: FEEDBACK_TIMEOUT_MS,
    ...opts,
  });
}

/**
 * Reachability check. Returns the health body when the server answers (even 503 "unavailable"),
 * or null when it cannot be reached at all (asleep, offline, CORS-blocked, timed out).
 */
export async function checkHealth(opts: Partial<RequestOptions> = {}): Promise<HealthResponse | null> {
  try {
    const { data } = await request<HealthResponse>("/health", { timeoutMs: HEALTH_TIMEOUT_MS, ...opts });
    return data;
  } catch (err) {
    if (err instanceof ApiError && err.status === 503) return { status: "unavailable", components: {} };
    return null;
  }
}
