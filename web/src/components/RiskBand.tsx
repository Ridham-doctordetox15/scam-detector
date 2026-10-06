"use client";

import { OctagonAlert, ShieldCheck, TriangleAlert, type LucideIcon } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";
import type { RiskLevel, Verdict } from "@/lib/types";
import { cn } from "@/lib/utils";

// A different icon shape per level, so colour is never the only signal (the words are the main one).
export const RISK_ICON: Record<RiskLevel, LucideIcon> = { low: ShieldCheck, medium: TriangleAlert, high: OctagonAlert };

export const RISK_STYLES: Record<RiskLevel, { text: string; bg: string; border: string; solid: string }> = {
  low: { text: "text-risk-low-fg", bg: "bg-risk-low-bg", border: "border-risk-low-border", solid: "bg-risk-low-solid" },
  medium: { text: "text-risk-medium-fg", bg: "bg-risk-medium-bg", border: "border-risk-medium-border", solid: "bg-risk-medium-solid" },
  high: { text: "text-risk-high-fg", bg: "bg-risk-high-bg", border: "border-risk-high-border", solid: "bg-risk-high-solid" },
};

/** Verdict and risk as words, with an icon whose shape differs per level. */
export function RiskBand({ verdict, risk, className }: { verdict: Verdict; risk: RiskLevel; className?: string }) {
  const { t } = useI18n();
  const Icon = RISK_ICON[risk];
  return (
    <div data-testid="risk-band" data-risk={risk} className={cn("flex items-center gap-3", RISK_STYLES[risk].text, className)}>
      <Icon aria-hidden="true" className="size-7 shrink-0" strokeWidth={2.25} />
      <div>
        <p className="text-2xl font-bold leading-tight tracking-tight">{t.result.verdict[verdict]}</p>
        <p className="text-sm font-semibold">{t.result.risk[risk]}</p>
      </div>
    </div>
  );
}

/** Small pill with the risk word (used for links). */
export function RiskChip({ risk, label }: { risk: RiskLevel; label: string }) {
  const Icon = RISK_ICON[risk];
  const s = RISK_STYLES[risk];
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold", s.text, s.bg, s.border)}>
      <Icon aria-hidden="true" className="size-3.5" />
      {label}
    </span>
  );
}
