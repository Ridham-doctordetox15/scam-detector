"use client";

import { ArrowUpRight, Image as ImageIcon, MessageSquareText, ShieldAlert, ShieldCheck } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";
import { assetPath } from "@/lib/config";
import { guessLangAttr } from "@/lib/lang";
import { IMAGE_SAMPLES, TEXT_SAMPLES, type Sample } from "@/lib/samples";
import { cn } from "@/lib/utils";

export interface SamplePickerProps {
  onPick: (sample: Sample) => void;
  disabled: boolean;
}

/** "English - fake KYC update" -> ["English", "fake KYC update"]: a language chip and a title. */
function splitTitle(title: string): [string | null, string] {
  const at = title.indexOf(" - ");
  return at > 0 ? [title.slice(0, at), title.slice(at + 3)] : [null, title];
}

const card =
  "group relative flex h-full w-full flex-col gap-3 rounded-2xl border bg-card p-4 text-left shadow-soft transition " +
  "hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lift disabled:pointer-events-none disabled:opacity-55";

/** Clickable samples. Clicking a text sample fills and checks it; a screenshot sample uploads it. */
export function SamplePicker({ onPick, disabled }: SamplePickerProps) {
  const { t } = useI18n();

  const Expected = ({ s }: { s: Sample }) => (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground">
      {s.expected === "scam" ? <ShieldAlert aria-hidden="true" className="size-3.5" /> : <ShieldCheck aria-hidden="true" className="size-3.5" />}
      {s.expected === "scam" ? t.samples.expectedScam : t.samples.expectedSafe}
    </span>
  );

  return (
    <section aria-labelledby="samples-heading" className="mx-auto max-w-6xl px-4 sm:px-6">
      <div className="mb-6 max-w-2xl">
        <h2 id="samples-heading" className="text-2xl font-semibold">
          {t.samples.heading}
        </h2>
        <p className="mt-1 text-muted-foreground">{t.samples.intro}</p>
      </div>

      <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        <MessageSquareText aria-hidden="true" className="size-4" />
        {t.samples.textHeading}
      </h3>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {TEXT_SAMPLES.map((s) => {
          const [chip, title] = splitTitle(t.samples.titles[s.titleKey]);
          return (
            <li key={s.id}>
              <button type="button" className={card} disabled={disabled} onClick={() => onPick(s)} data-sample-id={s.id}>
                <span className="flex items-center justify-between gap-2">
                  {chip && <span className="rounded-full bg-secondary px-2 py-0.5 text-xs font-semibold text-secondary-foreground">{chip}</span>}
                  <ArrowUpRight aria-hidden="true" className="size-4 text-muted-foreground transition group-hover:text-primary" />
                </span>
                <span className="font-semibold leading-snug">{title}</span>
                <span className="line-clamp-2 text-sm text-muted-foreground" lang={guessLangAttr(s.text)}>
                  {s.text}
                </span>
                <span className="mt-auto">
                  <Expected s={s} />
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      <h3 className="mb-3 mt-10 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        <ImageIcon aria-hidden="true" className="size-4" />
        {t.samples.imageHeading}
      </h3>
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {IMAGE_SAMPLES.map((s) => {
          const [chip, title] = splitTitle(t.samples.titles[s.titleKey]);
          return (
            <li key={s.id}>
              <button type="button" className={cn(card, "p-2.5")} disabled={disabled} onClick={() => onPick(s)} data-sample-id={s.id}>
                <span className="block h-40 overflow-hidden rounded-xl border bg-subtle">
                  {/* eslint-disable-next-line @next/next/no-img-element -- static export, no optimizer */}
                  <img
                    src={assetPath(s.file)}
                    alt="" // the button's visible title names it; alt text would read it twice
                    width={720}
                    height={1280}
                    loading="lazy"
                    decoding="async"
                    className="h-full w-full object-cover object-top transition duration-300 group-hover:scale-[1.03]"
                  />
                </span>
                <span className="px-1 text-sm font-semibold leading-snug">
                  {chip && <span className="block text-xs font-medium text-muted-foreground">{chip}</span>}
                  {title}
                </span>
                <span className="mt-auto px-1 pb-1">
                  <Expected s={s} />
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
