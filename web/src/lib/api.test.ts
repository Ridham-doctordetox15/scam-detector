import { describe, expect, it, vi } from "vitest";
import { analyzeImage, analyzeText, ApiError, checkHealth, sendFeedback } from "./api";

const API = "https://api.example.test";

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });
}

const errorBody = (code: string, requestId = "req-123") => ({ error: { code, message: "server text", request_id: requestId } });

async function catchError(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (err) {
    expect(err).toBeInstanceOf(ApiError);
    return err as ApiError;
  }
  throw new Error("expected the call to fail");
}

describe("analyzeText", () => {
  it("posts JSON to /analyze/text and returns the body", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(200, { verdict: "safe" }));
    const result = await analyzeText("hello", { apiUrl: API, fetchImpl });
    expect(result).toEqual({ verdict: "safe" });
    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${API}/analyze/text`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ text: "hello" });
    expect(init.credentials).toBe("omit");
    expect(init.referrerPolicy).toBe("no-referrer");
  });

  it("parses the API error code and request id", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(422, errorBody("empty_text")));
    const err = await catchError(analyzeText(" ", { apiUrl: API, fetchImpl }));
    expect(err.code).toBe("empty_text");
    expect(err.status).toBe(422);
    expect(err.requestId).toBe("req-123");
    expect(err.retryAfterS).toBeNull();
  });

  it("reads Retry-After on 429", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(429, errorBody("rate_limited"), { "Retry-After": "17" }));
    const err = await catchError(analyzeText("x", { apiUrl: API, fetchImpl }));
    expect(err.code).toBe("rate_limited");
    expect(err.retryAfterS).toBe(17);
  });

  it("falls back to unknown_error and the X-Request-ID header for a non-JSON error", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response("<html>bad gateway</html>", { status: 502, headers: { "X-Request-ID": "hdr-9" } }));
    const err = await catchError(analyzeText("x", { apiUrl: API, fetchImpl }));
    expect(err.code).toBe("unknown_error");
    expect(err.status).toBe(502);
    expect(err.requestId).toBe("hdr-9");
  });

  it("reports a network failure as network_error", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    const err = await catchError(analyzeText("x", { apiUrl: API, fetchImpl }));
    expect(err.code).toBe("network_error");
    expect(err.status).toBe(0);
  });

  it("aborts after the timeout and reports client_timeout", async () => {
    vi.useFakeTimers();
    try {
      const fetchImpl = vi.fn((_url: string, init: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        }),
      );
      const pending = catchError(analyzeText("x", { apiUrl: API, fetchImpl: fetchImpl as unknown as typeof fetch, timeoutMs: 30_000 }));
      await vi.advanceTimersByTimeAsync(29_999);
      expect(fetchImpl.mock.calls[0]?.[1].signal?.aborted).toBe(false);
      await vi.advanceTimersByTimeAsync(1);
      const err = await pending;
      expect(err.code).toBe("client_timeout");
    } finally {
      vi.useRealTimers();
    }
  });

  it("refuses to call anything when no API is configured", async () => {
    const fetchImpl = vi.fn();
    const err = await catchError(analyzeText("x", { apiUrl: "", fetchImpl }));
    expect(err.code).toBe("not_configured");
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});

describe("analyzeImage", () => {
  it("uploads multipart form data with the file field and the image timeout", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(200, { verdict: "scam" }));
    await analyzeImage(new Blob(["png"], { type: "image/png" }), "shot.png", { apiUrl: API, fetchImpl });
    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${API}/analyze/image`);
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("file")).toBeInstanceOf(Blob);
    // The browser must set the multipart boundary itself.
    expect(init.headers).toBeUndefined();
  });
});

describe("sendFeedback", () => {
  it("posts the prediction id and verdict", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(201, { status: "saved" }));
    await sendFeedback("abc", "incorrect", { apiUrl: API, fetchImpl });
    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${API}/feedback`);
    expect(JSON.parse(init.body as string)).toEqual({ prediction_id: "abc", user_verdict: "incorrect" });
  });

  it.each([
    [404, "unknown_prediction"],
    [503, "feedback_not_configured"],
    [502, "feedback_storage_error"],
  ])("surfaces HTTP %i as %s", async (status, code) => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(status, errorBody(code)));
    const err = await catchError(sendFeedback("abc", "correct", { apiUrl: API, fetchImpl }));
    expect(err.code).toBe(code);
    expect(err.status).toBe(status);
  });
});

describe("checkHealth", () => {
  it("returns the body when the server answers", async () => {
    const body = { status: "ok", components: {} };
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(200, body));
    await expect(checkHealth({ apiUrl: API, fetchImpl })).resolves.toEqual(body);
  });

  it("treats 503 as reachable but unavailable", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(503, { status: "unavailable", components: {} }));
    await expect(checkHealth({ apiUrl: API, fetchImpl })).resolves.toEqual({ status: "unavailable", components: {} });
  });

  it("returns null when the server can't be reached", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(checkHealth({ apiUrl: API, fetchImpl })).resolves.toBeNull();
  });
});
