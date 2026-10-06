"use client";

import { Clock, FileWarning, ImageOff, Info, OctagonAlert, PenLine, ServerCrash, WifiOff, type LucideIcon } from "lucide-react";
import { forwardRef } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { errorMessage } from "@/lib/errors";
import { fmt } from "@/lib/format";

export interface ErrorInfo {
  code: string;
  requestId: string | null;
  retryAfterS: number | null;
}

/** An icon that hints at the kind of problem (connection, waiting, file, input, server). */
export function errorIcon(code: string): LucideIcon {
  if (["network_error", "client_timeout", "not_configured"].includes(code)) return WifiOff;
  if (["rate_limited", "busy", "timeout"].includes(code)) return Clock;
  if (["unsupported_type", "corrupt", "empty", "too_small", "too_many_pixels", "no_text_found"].includes(code)) return ImageOff;
  if (["too_large", "body_too_large", "length_required"].includes(code)) return FileWarning;
  if (["empty_text", "text_too_long", "invalid_request"].includes(code)) return PenLine;
  if (code === "demo_unavailable") return Info;
  if (code.endsWith("_unavailable") || code === "internal_error") return ServerCrash;
  return OctagonAlert;
}

/** A friendly message for any error code, plus the request ID (small) for support. */
export const ErrorNotice = forwardRef<HTMLHeadingElement, { error: ErrorInfo }>(function ErrorNotice({ error }, ref) {
  const { t } = useI18n();
  const Icon = errorIcon(error.code);
  return (
    <div
      className="flex gap-4 rounded-2xl border border-risk-high-border bg-card p-5 shadow-soft"
      data-error-code={error.code}
      data-testid="error-notice"
    >
      <span className="grid size-10 shrink-0 place-items-center rounded-full bg-risk-high-bg text-risk-high-fg">
        <Icon aria-hidden="true" className="size-5" />
      </span>
      <div className="min-w-0">
        <h2 ref={ref} tabIndex={-1} className="text-base font-semibold outline-none">
          {t.errors.heading}
        </h2>
        <p className="mt-1 text-foreground">{errorMessage(error.code, t, error.retryAfterS)}</p>
        {error.requestId && (
          <p className="mt-2 text-xs text-muted-foreground">
            {fmt(t.errors.requestId, { id: "" })}
            <code lang="en" translate="no" className="font-mono">{error.requestId}</code>
          </p>
        )}
      </div>
    </div>
  );
});
