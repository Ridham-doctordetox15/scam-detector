"use client";

import { ChevronDown, Fingerprint, Lock, MoonStar, ScanText, Sparkles, TriangleAlert, type LucideIcon } from "lucide-react";
import * as m from "motion/react-m";
import { forwardRef, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useI18n } from "@/i18n/I18nProvider";
import { fmt } from "@/lib/format";
import { contentLangAttr, guessLangAttr } from "@/lib/lang";
import { patternInfo } from "@/lib/patterns";
import type { AnalyzeResponse, UserVerdict } from "@/lib/types";
import { cn } from "@/lib/utils";
import { FeedbackBox } from "./FeedbackBox";
import { RISK_STYLES, RiskBand, RiskChip } from "./RiskBand";
import { RiskGauge } from "./RiskGauge";

export interface ResultCardProps {
  result: AnalyzeResponse;
  /** Recording date when this is a recorded demo result (feedback is then hidden). */
  demoDate?: string | null;
  sendFeedback?: (predictionId: string, verdict: UserVerdict) => Promise<void>;
}

const reveal = (i: number) => ({
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.35, ease: [0.22, 1, 0.36, 1] as const, delay: 0.08 + i * 0.06 },
});

function Section({ index, icon: Icon, title, children }: { index: number; icon?: LucideIcon; title: string; children: ReactNode }) {
  return (
    <m.section {...reveal(index)} className="space-y-2.5">
      <h3 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        {Icon && <Icon aria-hidden="true" className="size-4" />}
        {title}
      </h3>
      {children}
    </m.section>
  );
}

/**
 * Shows an analysis result. Deliberately never renders: probabilities or scores (the API has none),
 * timings, or any link as an anchor - links stay defanged plain text in an "inspected link" panel.
 *
 * Interface labels follow the UI language; the API's content (red flags, explanation, advice)
 * carries its own lang attribute from the response's `language` field.
 */
export const ResultCard = forwardRef<HTMLHeadingElement, ResultCardProps>(function ResultCard(
  { result, demoDate = null, sendFeedback },
  headingRef,
) {
  const { t } = useI18n();
  const contentLang = contentLangAttr(result.language);
  const pattern = result.matched_pattern ? patternInfo(result.matched_pattern) : null;
  const isDemo = demoDate !== null;
  const risk = RISK_STYLES[result.risk_level];
  let i = 0;

  return (
    <m.article
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
      className="overflow-hidden rounded-2xl border bg-card shadow-lift"
      aria-labelledby="result-heading"
      data-testid="result-card"
    >
      <div className="grid md:grid-cols-[17rem_1fr]">
        {/* Verdict column: tinted by risk, always with the words. */}
        <div className={cn("flex flex-col items-center gap-3 border-b p-6 text-center md:border-b-0 md:border-r", risk.bg, risk.border)}>
          <h2 id="result-heading" ref={headingRef} tabIndex={-1} className="text-xs font-semibold uppercase tracking-[0.14em] text-foreground outline-none">
            {t.result.heading}
          </h2>
          <RiskGauge risk={result.risk_level} />
          <RiskBand verdict={result.verdict} risk={result.risk_level} className="justify-center text-left" />
          {isDemo && (
            <Badge variant="outline" className="mt-1 h-auto max-w-full whitespace-normal border-dashed bg-card text-center text-xs font-medium text-muted-foreground">
              {fmt(t.result.demoTag, { date: demoDate })}
            </Badge>
          )}
        </div>

        <div className="space-y-7 p-6 sm:p-7">
          <Section index={i++} icon={TriangleAlert} title={t.result.redFlags}>
            {result.red_flags.length > 0 ? (
              <ul lang={contentLang} data-testid="red-flags" className="space-y-2">
                {result.red_flags.map((flag, k) => (
                  <li key={k} className="flex gap-2.5">
                    <TriangleAlert aria-hidden="true" className={cn("mt-1 size-4 shrink-0", risk.text)} />
                    <span>{flag}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground">{t.result.noRedFlags}</p>
            )}
          </Section>

          <Section index={i++} title={t.result.explanation}>
            <p lang={contentLang} data-testid="explanation" className="text-[15px]">
              {result.explanation}
            </p>
            <Tooltip>
              <TooltipTrigger asChild>
                <button type="button" className="inline-flex items-center gap-1.5 rounded-full border bg-subtle px-2.5 py-1 text-xs font-medium text-muted-foreground">
                  <Sparkles aria-hidden="true" className="size-3.5" />
                  {fmt(t.result.explainedBy, { who: t.result.explainer[result.explainer_path] })}
                </button>
              </TooltipTrigger>
              <TooltipContent className="max-w-xs">{t.result.aiTooltip}</TooltipContent>
            </Tooltip>
          </Section>

          <Section index={i++} title={t.result.whatToDo}>
            <ol lang={contentLang} data-testid="what-to-do" className="space-y-2.5">
              {result.what_to_do.map((step, k) => (
                <li key={k} className="flex gap-3">
                  <span aria-hidden="true" className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-accent text-xs font-bold text-accent-foreground tabular">
                    {k + 1}
                  </span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
          </Section>

          {pattern && (
            <Section index={i++} icon={Fingerprint} title={t.result.matchedPattern}>
              <p className="rounded-xl border bg-subtle px-4 py-3">
                <span lang="en" className="font-medium">{pattern.name}</span>
                {pattern.category && (
                  <span className="text-muted-foreground">
                    {" "}
                    ({pattern.category === "scam" ? t.result.patternScam : t.result.patternLegit})
                  </span>
                )}
              </p>
            </Section>
          )}

          {result.url_findings.length > 0 && (
            <Section index={i++} icon={Lock} title={t.result.links}>
              <p className="text-sm text-muted-foreground">{t.result.linkNote}</p>
              <ul className="space-y-3">
                {result.url_findings.map((finding, k) => (
                  <li key={k} className="overflow-hidden rounded-xl border bg-subtle">
                    <div className="flex items-center justify-between gap-2 border-b px-3.5 py-2 text-xs font-medium text-muted-foreground">
                      <span className="inline-flex items-center gap-1.5">
                        <ScanText aria-hidden="true" className="size-3.5" />
                        {t.result.inspectedLink}
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <Lock aria-hidden="true" className="size-3" />
                        {t.result.notClickable}
                      </span>
                    </div>
                    <div className="space-y-2.5 px-3.5 py-3">
                      <code lang="en" className="block select-all break-all font-mono text-sm text-foreground" translate="no" data-testid="defanged-url">
                        {finding.url_defanged}
                      </code>
                      <RiskChip risk={finding.risk_band} label={fmt(t.result.linkRisk, { risk: t.result.risk[finding.risk_band] })} />
                      {finding.reasons.length > 0 && (
                        <Collapsible>
                          <CollapsibleTrigger className="group inline-flex items-center gap-1 rounded text-sm font-medium text-primary">
                            {fmt(t.result.linkChecks, { n: finding.reasons.length })}
                            <ChevronDown aria-hidden="true" className="size-4 transition-transform group-data-[state=open]:rotate-180" />
                          </CollapsibleTrigger>
                          <CollapsibleContent>
                            <ul lang="en" className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                              {finding.reasons.map((reason, j) => (
                                <li key={j}>{reason}</li>
                              ))}
                            </ul>
                          </CollapsibleContent>
                        </Collapsible>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {result.ocr && (
            <Section index={i++} icon={ScanText} title={t.result.extractedText}>
              <p className="flex flex-wrap items-center gap-2 text-sm">
                <span>
                  <strong className="font-semibold">{t.result.ocrQuality}:</strong> {t.result.ocrQualityValue[result.ocr.quality]}
                </span>
                {result.ocr.dark_mode && (
                  <span className="inline-flex items-center gap-1 text-muted-foreground">
                    <MoonStar aria-hidden="true" className="size-3.5" />
                    {t.result.darkMode}
                  </span>
                )}
              </p>
              <Collapsible>
                <CollapsibleTrigger className="group inline-flex items-center gap-1 rounded text-sm font-medium text-primary">
                  {t.result.extractedText}
                  <ChevronDown aria-hidden="true" className="size-4 transition-transform group-data-[state=open]:rotate-180" />
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <pre
                    lang={guessLangAttr(result.ocr.extracted_text)}
                    data-testid="extracted-text"
                    className="mt-2 whitespace-pre-wrap break-words rounded-xl border bg-subtle p-4 font-sans text-sm"
                  >
                    {result.ocr.extracted_text}
                  </pre>
                </CollapsibleContent>
              </Collapsible>
            </Section>
          )}

          <m.p {...reveal(i++)} className="text-xs text-muted-foreground">
            {t.result.verdictNote}
          </m.p>

          {!isDemo && <FeedbackBox key={result.prediction_id} predictionId={result.prediction_id} send={sendFeedback} />}
        </div>
      </div>
    </m.article>
  );
});
