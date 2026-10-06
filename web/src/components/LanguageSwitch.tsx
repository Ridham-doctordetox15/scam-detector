"use client";

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useI18n, type UiLang } from "@/i18n/I18nProvider";

/**
 * EN | हिंदी as a single-choice toggle group (Radix: role="radio" items with aria-checked inside a
 * labelled group, arrow-key navigation). Each label has its own lang so "हिंदी" is read as Hindi.
 */
export function LanguageSwitch() {
  const { lang, t, setLang } = useI18n();
  return (
    <ToggleGroup
      type="single"
      value={lang}
      onValueChange={(value) => value && setLang(value as UiLang)}
      aria-label={t.langSwitch.label}
      variant="outline"
      size="sm"
      className="rounded-lg bg-card"
    >
      <ToggleGroupItem value="en" lang="en" className="min-w-11 px-2.5 font-semibold data-[state=on]:bg-primary data-[state=on]:text-primary-foreground">
        {t.langSwitch.en}
      </ToggleGroupItem>
      <ToggleGroupItem value="hi" lang="hi" className="min-w-11 px-2.5 font-semibold data-[state=on]:bg-primary data-[state=on]:text-primary-foreground">
        {t.langSwitch.hi}
      </ToggleGroupItem>
    </ToggleGroup>
  );
}
