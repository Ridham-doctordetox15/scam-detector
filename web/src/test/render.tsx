import { render, type RenderOptions } from "@testing-library/react";
import type { ReactElement } from "react";
import { Providers } from "@/components/Providers";
import type { UiLang } from "@/i18n/I18nProvider";
import { DEMO } from "@/lib/demo";
import type { AnalyzeResponse } from "@/lib/types";

/** Render inside the app's real providers (theme, i18n, motion, tooltips, toasts); English by default. */
export function renderWithI18n(ui: ReactElement, { lang = "en", ...options }: { lang?: UiLang } & RenderOptions = {}) {
  return render(<Providers initialLang={lang}>{ui}</Providers>, options);
}

/** A real recorded response (deep-copied so tests can modify it). */
export function recorded(id: string): AnalyzeResponse {
  const response = DEMO.responses[id];
  if (!response) throw new Error(`no recording for ${id}`);
  return structuredClone(response);
}

export const ALL_RECORDED: [string, AnalyzeResponse][] = Object.entries(DEMO.responses);
