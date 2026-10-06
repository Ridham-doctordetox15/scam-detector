"use client";

/**
 * Interface-language state (EN | हिंदी). The choice is remembered in localStorage when storage
 * works and falls back to English when it doesn't. It updates <html lang> and every interface
 * string, but never touches analysis results - those keep the language the API returned.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { en, type Dictionary } from "./en";
import { hi } from "./hi";

export type UiLang = "en" | "hi";

export const DICTIONARIES: Record<UiLang, Dictionary> = { en, hi };
export const UI_LANG_STORAGE_KEY = "scam-checker.ui-lang";

export function readStoredLang(): UiLang {
  try {
    return window.localStorage.getItem(UI_LANG_STORAGE_KEY) === "hi" ? "hi" : "en";
  } catch {
    return "en";
  }
}

function storeLang(lang: UiLang): void {
  try {
    window.localStorage.setItem(UI_LANG_STORAGE_KEY, lang);
  } catch {
    /* storage blocked (private mode, disabled site data): the choice just isn't remembered */
  }
}

interface I18nValue {
  lang: UiLang;
  t: Dictionary;
  setLang: (lang: UiLang) => void;
}

const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({ children, initialLang }: { children: ReactNode; initialLang?: UiLang }) {
  // The static HTML is rendered in English; the stored choice is applied after hydration.
  const [lang, setLangState] = useState<UiLang>(initialLang ?? "en");

  useEffect(() => {
    if (!initialLang) setLangState(readStoredLang());
  }, [initialLang]);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((next: UiLang) => {
    setLangState(next);
    storeLang(next);
  }, []);

  const value = useMemo(() => ({ lang, t: DICTIONARIES[lang], setLang }), [lang, setLang]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used inside <I18nProvider>");
  return ctx;
}

/** Keep the tab title in the interface language (the static HTML title is English). */
export function useDocumentTitle(title: string): void {
  useEffect(() => {
    document.title = title;
  }, [title]);
}
