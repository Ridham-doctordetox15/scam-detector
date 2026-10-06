"use client";

import { BookOpen, ExternalLink, FlaskConical, Info, Lock, Route } from "lucide-react";
import type { ReactNode } from "react";
import { useDocumentTitle, useI18n } from "@/i18n/I18nProvider";
import {
  CLASSIFIER_ROWS,
  FINDING_SOURCES,
  OCR_ROWS,
  OCR_SECONDS,
  RAG_ROWS,
  SOURCES,
  TEST_SET,
  type FindingKey,
  type SourceKey,
} from "@/lib/aboutData";
import { REPO_URL } from "@/lib/config";
import { fmt } from "@/lib/format";
import { cn } from "@/lib/utils";
import { PipelineDiagram } from "./PipelineDiagram";
import { PrivacyList } from "./PrivacyDialog";

function Source({ id, className }: { id: SourceKey; className?: string }) {
  const { t } = useI18n();
  return (
    <p className={cn("text-xs text-muted-foreground", className)}>
      {t.about.sourcePrefix} <span lang="en">{SOURCES[id]}</span>
    </p>
  );
}

/** A horizontally scrollable table wrapper that keyboard users can scroll too. */
function TableCard({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-2xl border bg-card shadow-soft" role="region" aria-label={label} tabIndex={0}>
      {children}
    </div>
  );
}

const th = "border-b bg-subtle px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground";
const td = "border-b px-4 py-3 align-top";
const num = "whitespace-nowrap text-right tabular";

function SectionHeading({ id, icon: Icon, children }: { id: string; icon: typeof Info; children: ReactNode }) {
  return (
    <h2 id={id} className="flex items-center gap-2.5 text-2xl font-semibold">
      <span className="grid size-9 place-items-center rounded-xl bg-accent text-accent-foreground">
        <Icon aria-hidden="true" className="size-[18px]" />
      </span>
      {children}
    </h2>
  );
}

export function AboutContent() {
  const { t } = useI18n();
  const a = t.about;
  useDocumentTitle(`${a.title} - ${t.meta.title}`);

  const deployed = CLASSIFIER_ROWS.find((r) => r.deployed)!;
  const realRag = RAG_ROWS.find((r) => r.split === "real")!;
  const stats: { value: string; label: string; source: SourceKey }[] = [
    { value: deployed.f1, label: a.stats.f1, source: "phase4Test" },
    { value: deployed.promoFlagged, label: a.stats.promo, source: "phase4Test" },
    { value: deployed.unseenAuc, label: a.stats.unseen, source: "phase4Loso" },
    { value: realRag.top3, label: a.stats.rag, source: "rag" },
  ];

  return (
    <article className="mx-auto max-w-6xl px-4 pb-8 sm:px-6">
      <header className="max-w-3xl pb-10 pt-12 sm:pt-16">
        <h1 className="text-[2rem] font-bold leading-tight sm:text-[2.6rem]">{a.title}</h1>
        <p className="mt-4 text-lg text-muted-foreground">{a.intro}</p>
      </header>

      <section aria-labelledby="how-heading" className="space-y-6">
        <SectionHeading id="how-heading" icon={Route}>
          {a.howHeading}
        </SectionHeading>
        <div className="grid gap-8 rounded-2xl border bg-card p-5 shadow-soft sm:p-8 lg:grid-cols-[minmax(0,26rem)_1fr]">
          <PipelineDiagram />
          <ol className="space-y-5 self-center">
            {a.steps.map((step, i) => (
              <li key={i} className="flex gap-3.5">
                <span aria-hidden="true" className="grid size-7 shrink-0 place-items-center rounded-full bg-primary text-sm font-bold text-primary-foreground tabular">
                  {i + 1}
                </span>
                <span className="pt-0.5">{step}</span>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section aria-labelledby="results-heading" className="mt-16 space-y-6">
        <SectionHeading id="results-heading" icon={FlaskConical}>
          {a.resultsHeading}
        </SectionHeading>
        <p className="max-w-3xl text-muted-foreground">{fmt(a.resultsIntro, { rows: TEST_SET.rows, scamShare: TEST_SET.scamShare })}</p>

        <h3 className="text-lg font-semibold">{a.statsHeading}</h3>
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {stats.map((s) => (
            <li key={s.label} className="flex flex-col rounded-2xl border bg-card p-5 shadow-soft">
              <span className="text-3xl font-bold tracking-tight tabular">{s.value}</span>
              <span className="mt-1.5 text-sm">{s.label}</span>
              <Source id={s.source} className="mt-auto pt-3" />
            </li>
          ))}
        </ul>

        <h3 className="pt-4 text-lg font-semibold">{a.tablesHeading}</h3>
        <TableCard label={a.tableCaption}>
          <table className="w-full min-w-[44rem] border-collapse text-sm">
            <caption className="px-4 pb-2 pt-4 text-left font-semibold">{a.tableCaption}</caption>
            <thead>
              <tr>
                <th scope="col" className={th}>{a.colSystem}</th>
                <th scope="col" className={th}>{a.colThreshold}</th>
                <th scope="col" className={cn(th, num)}>{a.colF1}</th>
                <th scope="col" className={cn(th, num)}>{a.colAuc}</th>
                <th scope="col" className={cn(th, num)}>{a.colUnseen}</th>
                <th scope="col" className={cn(th, num)}>{a.colPromo}</th>
              </tr>
            </thead>
            <tbody>
              {CLASSIFIER_ROWS.map((row) => (
                <tr key={`${row.system}-${row.operatingPoint}`} className={row.deployed ? "bg-accent/60 font-medium" : undefined}>
                  <th scope="row" className={cn(td, "text-left font-medium")}>
                    <span lang="en">{row.system}</span>
                    {row.deployed && (
                      <span className="ml-2 inline-flex rounded-full border border-primary px-2 text-xs font-semibold text-accent-foreground">
                        {a.deployedTag}
                      </span>
                    )}
                  </th>
                  <td className={td}>{a.operatingPoint[row.operatingPoint]}</td>
                  <td className={cn(td, num)}>{row.f1}</td>
                  <td className={cn(td, num)}>{row.rocAuc}</td>
                  <td className={cn(td, num)}>{row.unseenAuc}</td>
                  <td className={cn(td, num)}>{row.promoFlagged}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableCard>
        <div>
          <Source id="phase4Test" />
          <Source id="phase4Loso" />
        </div>

        <h3 className="pt-4 text-lg font-semibold">{a.findingsHeading}</h3>
        <ul className="grid gap-4 md:grid-cols-2">
          {(Object.keys(FINDING_SOURCES) as FindingKey[]).map((key) => (
            <li key={key} className="flex flex-col rounded-2xl border bg-card p-5 shadow-soft">
              <span className="flex gap-2.5">
                <Info aria-hidden="true" className="mt-1 size-4 shrink-0 text-primary" />
                <span>{a.findings[key]}</span>
              </span>
              <Source id={FINDING_SOURCES[key]} className="mt-auto pl-6 pt-3" />
            </li>
          ))}
        </ul>

        <div className="grid gap-6 pt-4 lg:grid-cols-2">
          <div className="min-w-0 space-y-3">
            <h3 className="text-lg font-semibold">{a.ragHeading}</h3>
            <TableCard label={a.ragCaption}>
              <table className="w-full border-collapse text-sm">
                <caption className="px-4 pb-2 pt-4 text-left font-semibold">{a.ragCaption}</caption>
                <thead>
                  <tr>
                    <th scope="col" className={th}>{a.colSplit}</th>
                    <th scope="col" className={cn(th, num)}>{a.colN}</th>
                    <th scope="col" className={cn(th, num)}>{a.colTop1}</th>
                    <th scope="col" className={cn(th, num)}>{a.colTop3}</th>
                  </tr>
                </thead>
                <tbody>
                  {RAG_ROWS.map((row) => (
                    <tr key={row.split}>
                      <th scope="row" className={cn(td, "text-left font-medium")}>{a.ragSplit[row.split]}</th>
                      <td className={cn(td, num)}>{row.n}</td>
                      <td className={cn(td, num)}>{row.top1}</td>
                      <td className={cn(td, num)}>{row.top3}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableCard>
            <Source id="rag" />
          </div>

          <div className="min-w-0 space-y-3">
            <h3 className="text-lg font-semibold">{a.ocrHeading}</h3>
            <TableCard label={a.ocrCaption}>
              <table className="w-full min-w-[30rem] border-collapse text-sm">
                <caption className="px-4 pb-2 pt-4 text-left font-semibold">{a.ocrCaption}</caption>
                <thead>
                  <tr>
                    <th scope="col" className={th}>{a.colSample}</th>
                    <th scope="col" className={cn(th, num)}>{a.colCer}</th>
                    <th scope="col" className={cn(th, num)}>{a.colKeywords}</th>
                    <th scope="col" className={th}>{a.colVerdict}</th>
                  </tr>
                </thead>
                <tbody>
                  {OCR_ROWS.map((row) => (
                    <tr key={row.sample}>
                      <th scope="row" className={cn(td, "text-left font-normal")}>
                        <code lang="en" translate="no" className="font-mono text-xs">{row.sample}</code>
                      </th>
                      <td className={cn(td, num)}>{row.cer}</td>
                      <td className={cn(td, num)}>{row.keywordRecall}</td>
                      <td className={td} lang="en">{row.verdict}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableCard>
            <p className="text-sm text-muted-foreground">{fmt(a.ocrNote, { min: OCR_SECONDS.min, max: OCR_SECONDS.max })}</p>
            <Source id="ocr" />
          </div>
        </div>
      </section>

      <div className="mt-16 grid gap-6 lg:grid-cols-2">
        <section aria-labelledby="privacy-heading" className="space-y-5 rounded-2xl border bg-card p-6 shadow-soft">
          <SectionHeading id="privacy-heading" icon={Lock}>
            {a.privacyHeading}
          </SectionHeading>
          <PrivacyList items={a.privacy} />
        </section>

        <section aria-labelledby="limits-heading" className="space-y-5 rounded-2xl border bg-card p-6 shadow-soft">
          <SectionHeading id="limits-heading" icon={Info}>
            {a.limitsHeading}
          </SectionHeading>
          <ul className="space-y-3">
            {a.limits.map((item, i) => (
              <li key={i} className="flex gap-3 text-sm">
                <span aria-hidden="true" className="mt-2 size-1.5 shrink-0 rounded-full bg-muted-foreground" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section aria-labelledby="source-heading" className="mt-16 space-y-3">
        <SectionHeading id="source-heading" icon={BookOpen}>
          {a.sourceHeading}
        </SectionHeading>
        <p className="text-muted-foreground">{a.sourceText}</p>
        {REPO_URL && (
          <p>
            <a
              href={`${REPO_URL.replace(/\/+$/, "")}#readme`}
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 font-medium text-primary underline-offset-4 hover:underline"
            >
              {a.repoLink}
              <ExternalLink aria-hidden="true" className="size-4" />
            </a>
          </p>
        )}
      </section>
    </article>
  );
}
