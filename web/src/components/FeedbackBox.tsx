"use client";

import { Check, ThumbsDown, ThumbsUp } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/i18n/I18nProvider";
import { ApiError, sendFeedback } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import type { UserVerdict } from "@/lib/types";

type State =
  | { kind: "idle" }
  | { kind: "sending"; verdict: UserVerdict }
  | { kind: "saved"; verdict: UserVerdict }
  /** final: the server said no for good (404 too old, 503 not configured). */
  | { kind: "failed"; code: string; retryAfterS: number | null; final: boolean };

const FINAL_CODES = new Set(["unknown_prediction", "feedback_not_configured", "invalid_request"]);

export interface FeedbackBoxProps {
  predictionId: string;
  send?: (predictionId: string, verdict: UserVerdict) => Promise<void>;
}

/**
 * "Was this correct?" Yes / No. One answer per result; retry only for transient errors.
 * The outcome is shown inline (permanent, announced via role="status") and as a short toast.
 */
export function FeedbackBox({ predictionId, send = sendFeedback }: FeedbackBoxProps) {
  const { t } = useI18n();
  const [state, setState] = useState<State>({ kind: "idle" });
  const inFlight = useRef(false);

  async function answer(verdict: UserVerdict) {
    if (inFlight.current) return;
    inFlight.current = true;
    setState({ kind: "sending", verdict });
    try {
      await send(predictionId, verdict);
      setState({ kind: "saved", verdict });
      toast.success(t.feedback.toastSaved);
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "unknown_error";
      const retryAfterS = err instanceof ApiError ? err.retryAfterS : null;
      setState({ kind: "failed", code, retryAfterS, final: FINAL_CODES.has(code) });
      toast.error(t.feedback.toastFailed, { description: errorMessage(code, t, retryAfterS) });
    } finally {
      inFlight.current = false;
    }
  }

  const disabled = state.kind === "sending" || state.kind === "saved" || (state.kind === "failed" && state.final);
  const chosen = state.kind === "saved" || state.kind === "sending" ? state.verdict : null;

  return (
    <div
      className="flex flex-col gap-3 rounded-xl border bg-subtle p-4 sm:flex-row sm:items-center sm:justify-between"
      role="group"
      aria-labelledby={`fb-${predictionId}`}
    >
      <div className="min-w-0">
        <p id={`fb-${predictionId}`} className="font-semibold">
          {t.feedback.question}
        </p>
        <p role="status" className="min-h-5 text-sm text-muted-foreground">
          {state.kind === "sending" && t.feedback.sending}
          {state.kind === "saved" && (
            <span className="inline-flex items-center gap-1.5">
              <Check aria-hidden="true" className="size-4 text-risk-low-fg" />
              {t.feedback.thanks}
            </span>
          )}
          {state.kind === "failed" && (
            <>
              {errorMessage(state.code, t, state.retryAfterS)}
              {!state.final && ` ${t.feedback.retry}`}
            </>
          )}
        </p>
      </div>
      <div className="flex shrink-0 gap-2">
        <Button type="button" variant={chosen === "correct" ? "default" : "outline"} disabled={disabled} onClick={() => answer("correct")}>
          <ThumbsUp aria-hidden="true" />
          {t.feedback.yes}
        </Button>
        <Button type="button" variant={chosen === "incorrect" ? "default" : "outline"} disabled={disabled} onClick={() => answer("incorrect")}>
          <ThumbsDown aria-hidden="true" />
          {t.feedback.no}
        </Button>
      </div>
    </div>
  );
}
