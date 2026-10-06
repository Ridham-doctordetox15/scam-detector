"use client";

import { Check, FileText, Image as ImageIcon, Loader2, ScanSearch, ShieldCheck } from "lucide-react";
import * as m from "motion/react-m";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useDocumentTitle, useI18n } from "@/i18n/I18nProvider";
import * as apiClient from "@/lib/api";
import { ApiError } from "@/lib/api";
import { assetPath, MAX_TEXT_CHARS } from "@/lib/config";
import { DEMO, demoRecordedDate, getDemoResponse, type DemoRecording } from "@/lib/demo";
import { charCount, fmt } from "@/lib/format";
import type { Sample } from "@/lib/samples";
import type { AnalyzeResponse, UserVerdict } from "@/lib/types";
import { useBackendMode, type BackendModeOptions } from "@/lib/useBackendMode";
import { cn } from "@/lib/utils";
import { validateImageFile } from "@/lib/validateImage";
import { ErrorNotice, type ErrorInfo } from "./ErrorNotice";
import { ModeBanner } from "./ModeBanner";
import { PrivacyDialog } from "./PrivacyDialog";
import { ResultCard } from "./ResultCard";
import { ResultSkeleton } from "./ResultSkeleton";
import { SamplePicker } from "./SamplePicker";
import { UploadZone } from "./UploadZone";

type Tab = "text" | "image";

type ImageSource =
  | { kind: "file"; file: File; url: string }
  | { kind: "sample"; sampleId: string; url: string; titleKey: Sample["titleKey"]; name: string };

type Outcome =
  | { kind: "result"; result: AnalyzeResponse; demo: boolean }
  | { kind: "error"; error: ErrorInfo }
  | null;

export interface AnalyzerApi {
  analyzeText: (text: string) => Promise<AnalyzeResponse>;
  analyzeImage: (file: Blob, filename: string) => Promise<AnalyzeResponse>;
  sendFeedback: (predictionId: string, verdict: UserVerdict) => Promise<void>;
}

export interface AnalyzerProps {
  /** Injection points for tests; the app uses the real API client and recordings. */
  api?: AnalyzerApi;
  backend?: BackendModeOptions;
  demo?: DemoRecording;
  fetchSample?: (url: string) => Promise<Blob>;
}

const defaultApi: AnalyzerApi = {
  analyzeText: (text) => apiClient.analyzeText(text),
  analyzeImage: (file, filename) => apiClient.analyzeImage(file, filename),
  sendFeedback: (id, verdict) => apiClient.sendFeedback(id, verdict),
};

async function defaultFetchSample(url: string): Promise<Blob> {
  const res = await fetch(url);
  if (!res.ok) throw new ApiError("unknown_error", res.status, "Sample screenshot could not be loaded");
  return res.blob();
}

const toErrorInfo = (err: unknown): ErrorInfo =>
  err instanceof ApiError
    ? { code: err.code, requestId: err.requestId, retryAfterS: err.retryAfterS }
    : { code: "unknown_error", requestId: null, retryAfterS: null };

const clientError = (code: string): ErrorInfo => ({ code, requestId: null, retryAfterS: null });

// Entrance only: an exiting copy would briefly duplicate the result (and its ids) for screen readers.
const fade = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.2 },
};

export function Analyzer({ api = defaultApi, backend, demo = DEMO, fetchSample = defaultFetchSample }: AnalyzerProps) {
  const { t } = useI18n();
  useDocumentTitle(t.meta.title);
  const { mode, retrying, retry, isDemo } = useBackendMode(backend);
  const demoDate = demoRecordedDate(demo);

  const [tab, setTab] = useState<Tab>("text");
  const [text, setText] = useState("");
  const [image, setImage] = useState<ImageSource | null>(null);
  const [busy, setBusy] = useState<Tab | null>(null);
  const [outcome, setOutcome] = useState<Outcome>(null);

  const busyRef = useRef(false); // blocks double-submits synchronously (state updates are async)
  const resultHeadingRef = useRef<HTMLHeadingElement>(null);
  const errorHeadingRef = useRef<HTMLHeadingElement>(null);

  const live = mode === "live";
  const inputsDisabled = !live || busy !== null;
  const samplesDisabled = mode === "checking" || busy !== null;
  const chars = charCount(text);
  const tooLong = chars > MAX_TEXT_CHARS;

  // Move keyboard focus to the new result (or error) so screen readers announce it.
  useEffect(() => {
    if (outcome?.kind === "result") resultHeadingRef.current?.focus();
    if (outcome?.kind === "error") errorHeadingRef.current?.focus();
  }, [outcome]);

  // Free the preview's object URL when the image changes or the page unmounts.
  useEffect(() => {
    return () => {
      if (image?.kind === "file") URL.revokeObjectURL(image.url);
    };
  }, [image]);

  async function run(kind: Tab, task: () => Promise<AnalyzeResponse>, fromDemo: boolean) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(kind);
    setOutcome(null);
    try {
      setOutcome({ kind: "result", result: await task(), demo: fromDemo });
    } catch (err) {
      setOutcome({ kind: "error", error: toErrorInfo(err) });
    } finally {
      busyRef.current = false;
      setBusy(null);
    }
  }

  /** Demo mode: only a recorded sample can produce a result - never typed text or an upload. */
  function runDemo(kind: Tab, sampleId: string | null) {
    if (sampleId === null) {
      setOutcome({ kind: "error", error: clientError("demo_unavailable") });
      return;
    }
    void run(kind, async () => getDemoResponse(sampleId, demo), true);
  }

  function submitText(value: string, sampleId: string | null = null) {
    if (busyRef.current || mode === "checking") return;
    if (isDemo) return runDemo("text", sampleId);
    if (value.trim() === "") return setOutcome({ kind: "error", error: clientError("empty_text") });
    if (charCount(value) > MAX_TEXT_CHARS) return setOutcome({ kind: "error", error: clientError("text_too_long") });
    void run("text", () => api.analyzeText(value), false);
  }

  function submitImage(source: ImageSource | null) {
    if (busyRef.current || mode === "checking" || source === null) return;
    if (isDemo) return runDemo("image", source.kind === "sample" ? source.sampleId : null);
    void run(
      "image",
      async () => {
        if (source.kind === "file") return api.analyzeImage(source.file, source.file.name);
        const blob = await fetchSample(source.url);
        return api.analyzeImage(blob, source.name);
      },
      false,
    );
  }

  function selectFile(file: File | undefined) {
    if (!file || inputsDisabled) return;
    const problem = validateImageFile(file);
    if (problem) {
      setOutcome({ kind: "error", error: clientError(problem) });
      return;
    }
    setOutcome(null);
    setImage({ kind: "file", file, url: URL.createObjectURL(file) });
  }

  function pickSample(sample: Sample) {
    if (busyRef.current) return;
    if (sample.kind === "text") {
      setTab("text");
      setText(sample.text);
      submitText(sample.text, sample.id);
    } else {
      const source: ImageSource = {
        kind: "sample",
        sampleId: sample.id,
        url: assetPath(sample.file),
        titleKey: sample.titleKey,
        name: sample.file.split("/").pop() ?? "sample.png",
      };
      setTab("image");
      setImage(source);
      submitImage(source);
    }
  }

  const describedBy = ["privacy-hint", isDemo ? "demo-note" : null].filter(Boolean).join(" ");
  // Loading text while busy; afterwards a one-line summary, so the result is announced briefly.
  const statusText =
    busy === "text"
      ? t.form.analyzingText
      : busy === "image"
        ? t.form.analyzingImage
        : outcome?.kind === "result"
          ? `${t.result.heading}: ${t.result.verdict[outcome.result.verdict]}, ${t.result.risk[outcome.result.risk_level]}`
          : "";

  const preview =
    image === null
      ? null
      : {
          url: image.url,
          name: image.kind === "file" ? image.file.name : image.name,
          alt: image.kind === "sample" ? fmt(t.samples.screenshotAlt, { title: t.samples.titles[image.titleKey] }) : t.form.previewAlt,
        };

  return (
    <div className="pb-4">
      {/* Hero: value proposition, then the input card front and centre. */}
      <section className="relative overflow-hidden border-b">
        <div aria-hidden="true" className="bg-grid pointer-events-none absolute inset-0 [mask-image:radial-gradient(ellipse_at_top,black_20%,transparent_70%)]" />
        <div aria-hidden="true" className="pointer-events-none absolute -top-40 left-1/2 h-80 w-[44rem] -translate-x-1/2 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative mx-auto max-w-3xl px-4 pb-12 pt-12 sm:px-6 sm:pt-16">
          <div className="text-center">
            <p className="inline-flex items-center gap-1.5 rounded-full border bg-card px-3 py-1 text-xs font-semibold text-muted-foreground shadow-soft">
              <ShieldCheck aria-hidden="true" className="size-3.5 text-primary" />
              {t.hero.eyebrow}
            </p>
            <h1 className="mt-5 text-[2rem] font-bold leading-[1.15] sm:text-[2.6rem]">{t.hero.title}</h1>
            <p className="mx-auto mt-4 max-w-2xl text-base text-muted-foreground sm:text-lg">{t.hero.subtitle}</p>
            <ul className="mx-auto mt-5 flex w-fit max-w-2xl flex-col items-start gap-x-5 gap-y-1.5 text-left text-sm text-muted-foreground sm:w-auto sm:flex-row sm:flex-wrap sm:items-center sm:justify-center">
              {t.hero.points.map((point, k) => (
                <li key={k} className="flex items-start gap-1.5">
                  <Check aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-risk-low-fg" />
                  {point}
                </li>
              ))}
            </ul>
          </div>

          <div className="mt-8 space-y-4">
            <ModeBanner mode={mode} demoDate={demoDate} retrying={retrying} onRetry={retry} />

            <section aria-labelledby="form-heading" className="rounded-2xl border bg-card p-4 shadow-lift sm:p-6">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                <h2 id="form-heading" className="text-lg font-semibold">
                  {t.form.heading}
                </h2>
                <PrivacyDialog />
              </div>

              <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)}>
                <TabsList aria-label={t.form.tabsLabel} className="grid w-full grid-cols-2 sm:w-80">
                  <TabsTrigger value="text">
                    <FileText aria-hidden="true" />
                    {t.form.tabText}
                  </TabsTrigger>
                  <TabsTrigger value="image">
                    <ImageIcon aria-hidden="true" />
                    {t.form.tabImage}
                  </TabsTrigger>
                </TabsList>

                {isDemo && (
                  <p id="demo-note" className="mt-4 rounded-lg border-l-4 border-risk-medium-solid bg-subtle px-3 py-2 text-sm">
                    {t.form.demoDisabled}
                  </p>
                )}

                {/* forceMount + hidden keeps both inputs in the page (state and labels stay stable). */}
                <TabsContent value="text" forceMount hidden={tab !== "text"} className="mt-4">
                  <form
                    onSubmit={(event) => {
                      event.preventDefault();
                      submitText(text);
                    }}
                    className="space-y-3"
                  >
                    <label htmlFor="message-text" className="block text-sm font-medium">
                      {t.form.textLabel}
                    </label>
                    <textarea
                      id="message-text"
                      value={text}
                      onChange={(event) => setText(event.target.value)}
                      placeholder={t.form.textPlaceholder}
                      rows={6}
                      disabled={inputsDisabled}
                      aria-describedby={`char-count ${describedBy}`}
                      aria-invalid={tooLong || undefined}
                      spellCheck={false}
                      className={cn(
                        "block min-h-36 w-full resize-y rounded-xl border border-input bg-background px-3.5 py-3 text-[15px] shadow-xs transition",
                        "placeholder:text-muted-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-ring/20",
                        "disabled:cursor-not-allowed disabled:opacity-70 aria-invalid:border-destructive aria-invalid:ring-destructive/20",
                      )}
                    />
                    <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <Button type="submit" size="lg" disabled={inputsDisabled} aria-disabled={inputsDisabled} className="sm:w-auto">
                        {busy === "text" ? <Loader2 aria-hidden="true" className="animate-spin" /> : <ScanSearch aria-hidden="true" />}
                        {t.form.submit}
                      </Button>
                      <p id="char-count" className={cn("text-xs tabular text-muted-foreground", tooLong && "font-semibold text-destructive")}>
                        {fmt(t.form.charCount, { n: chars, max: MAX_TEXT_CHARS })}
                        {tooLong && ` - ${fmt(t.errors.text_too_long, { max: MAX_TEXT_CHARS })}`}
                      </p>
                    </div>
                  </form>
                </TabsContent>

                <TabsContent value="image" forceMount hidden={tab !== "image"} className="mt-4">
                  <form
                    onSubmit={(event) => {
                      event.preventDefault();
                      submitImage(image);
                    }}
                    className="space-y-3"
                  >
                    <p className="text-sm font-medium" id="image-label">
                      {t.form.imageLabel}
                    </p>
                    <UploadZone
                      disabled={inputsDisabled}
                      busy={busy !== null}
                      preview={preview}
                      describedBy={describedBy}
                      onFile={selectFile}
                      onRemove={() => setImage(null)}
                    />
                    <Button type="submit" size="lg" disabled={inputsDisabled || image === null}>
                      {busy === "image" ? <Loader2 aria-hidden="true" className="animate-spin" /> : <ScanSearch aria-hidden="true" />}
                      {t.form.submitImage}
                    </Button>
                  </form>
                </TabsContent>
              </Tabs>

              <p id="privacy-hint" className="mt-4 border-t pt-4 text-xs text-muted-foreground">
                {t.form.privacyHint}
              </p>
            </section>

            <p role="status" aria-live="polite" data-testid="status" className="flex min-h-6 items-center justify-center gap-2 text-sm font-medium text-muted-foreground">
              {busy !== null && <Loader2 aria-hidden="true" className="size-4 animate-spin" />}
              {statusText}
            </p>
          </div>
        </div>
      </section>

      {/* Result area: skeleton while checking, then the result or an error; a friendly empty state before. */}
      <div className="relative mx-auto max-w-5xl scroll-mt-24 px-4 pt-8 sm:px-6">
          {busy !== null ? (
            <m.div key="loading" {...fade}>
              <ResultSkeleton />
            </m.div>
          ) : outcome?.kind === "error" ? (
            <m.div key="error" {...fade}>
              <ErrorNotice ref={errorHeadingRef} error={outcome.error} />
            </m.div>
          ) : outcome?.kind === "result" ? (
            <m.div key={`result-${outcome.result.prediction_id}`} {...fade}>
              <ResultCard
                ref={resultHeadingRef}
                result={outcome.result}
                demoDate={outcome.demo ? demoDate : null}
                sendFeedback={api.sendFeedback}
              />
            </m.div>
          ) : (
            <m.div key="empty" {...fade} className="flex flex-col items-center gap-2 rounded-2xl border border-dashed px-6 py-10 text-center">
              <span className="grid size-11 place-items-center rounded-full bg-secondary text-muted-foreground">
                <ScanSearch aria-hidden="true" className="size-5" />
              </span>
              <p className="font-semibold">{t.empty.title}</p>
              <p className="max-w-sm text-sm text-muted-foreground">{t.empty.body}</p>
            </m.div>
          )}
      </div>

      <div className="pt-16">
        <SamplePicker onPick={pickSample} disabled={samplesDisabled} />
      </div>
    </div>
  );
}
