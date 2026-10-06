"use client";

import { CloudOff, Info, RefreshCw } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/i18n/I18nProvider";
import { fmt } from "@/lib/format";
import type { BackendMode } from "@/lib/useBackendMode";
import { cn } from "@/lib/utils";

export interface ModeBannerProps {
  mode: BackendMode;
  demoDate: string;
  retrying: boolean;
  onRetry: () => Promise<BackendMode>;
}

/**
 * Says plainly when the site is showing recorded results. `not_hosted` (no API URL at build time)
 * has no retry button: there is nothing to retry until the site is rebuilt with an API URL.
 */
export function ModeBanner({ mode, demoDate, retrying, onRetry }: ModeBannerProps) {
  const { t } = useI18n();
  const [announcement, setAnnouncement] = useState("");

  async function retry() {
    setAnnouncement("");
    const next = await onRetry();
    setAnnouncement(next === "live" ? t.mode.nowLive : t.mode.stillUnreachable);
  }

  const demo = mode === "not_hosted" || mode === "unreachable";
  const Icon = mode === "unreachable" ? CloudOff : Info;

  return (
    <>
      {mode === "checking" && (
        <p className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
          <RefreshCw aria-hidden="true" className="size-4 animate-spin" />
          {t.mode.checking}
        </p>
      )}
      {demo && (
        <section
          aria-labelledby="demo-banner-title"
          data-testid="demo-banner"
          className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-3 rounded-2xl border border-risk-medium-border bg-risk-medium-bg p-4 sm:grid-cols-[auto_1fr_auto] sm:items-start sm:gap-x-4 sm:p-5"
        >
          <span className="grid size-9 shrink-0 place-items-center rounded-full bg-card text-risk-medium-fg shadow-soft">
            <Icon aria-hidden="true" className="size-[18px]" />
          </span>
          <div className="min-w-0 flex-1 space-y-1.5">
            <p className="inline-flex rounded-full bg-risk-medium-fg px-2 py-0.5 text-xs font-bold tracking-wide text-risk-medium-bg">
              {t.mode.demoBadge}
            </p>
            <h2 id="demo-banner-title" className="text-base font-semibold text-foreground">
              {mode === "not_hosted" ? t.mode.notHostedTitle : t.mode.unreachableTitle}
            </h2>
            <p className="text-sm text-foreground">
              {fmt(mode === "not_hosted" ? t.mode.notHostedBody : t.mode.unreachableBody, { date: demoDate })}
            </p>
          </div>
          {mode === "unreachable" && (
            <Button type="button" variant="outline" className="col-span-2 bg-card sm:col-span-1" onClick={retry} disabled={retrying}>
              <RefreshCw aria-hidden="true" className={cn(retrying && "animate-spin")} />
              {retrying ? t.mode.retrying : t.mode.retry}
            </Button>
          )}
        </section>
      )}
      <p role="status" className="visually-hidden">
        {announcement}
      </p>
    </>
  );
}
