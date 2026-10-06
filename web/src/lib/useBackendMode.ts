"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { checkHealth } from "./api";
import { API_URL, isBackendConfigured } from "./config";
import type { HealthResponse } from "./types";

/**
 * - `not_hosted`: no API URL was set at build time (the backend isn't deployed yet). Demo only.
 * - `checking`:   waiting for GET /health (4 s timeout).
 * - `live`:       the API answered and can analyze.
 * - `unreachable`: the API didn't answer, or answered "unavailable". Demo only, with a retry.
 */
export type BackendMode = "not_hosted" | "checking" | "live" | "unreachable";

export interface BackendModeOptions {
  apiUrl?: string;
  check?: (apiUrl: string) => Promise<HealthResponse | null>;
}

const defaultCheck = (apiUrl: string) => checkHealth({ apiUrl });

export const modeFromHealth = (health: HealthResponse | null): BackendMode =>
  health && health.status !== "unavailable" ? "live" : "unreachable";

export function useBackendMode({ apiUrl = API_URL, check = defaultCheck }: BackendModeOptions = {}) {
  const configured = isBackendConfigured(apiUrl);
  const [mode, setMode] = useState<BackendMode>(configured ? "checking" : "not_hosted");
  const [retrying, setRetrying] = useState(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    if (configured) {
      void check(apiUrl).then((health) => {
        if (mounted.current) setMode(modeFromHealth(health));
      });
    }
    return () => {
      mounted.current = false;
    };
  }, [apiUrl, check, configured]);

  /** Re-check the server. Resolves to the new mode so the caller can announce it. */
  const retry = useCallback(async (): Promise<BackendMode> => {
    if (!configured) return "not_hosted";
    setRetrying(true);
    const next = modeFromHealth(await check(apiUrl));
    if (mounted.current) {
      setMode(next);
      setRetrying(false);
    }
    return next;
  }, [apiUrl, check, configured]);

  return { mode, retrying, retry, isDemo: mode === "not_hosted" || mode === "unreachable" };
}
