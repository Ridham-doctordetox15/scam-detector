"use client";

import { ShieldCheck } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";

export function SiteFooter() {
  const { t } = useI18n();
  return (
    <footer className="mt-20 border-t bg-subtle">
      <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-8 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p className="flex items-center gap-2">
          <ShieldCheck aria-hidden="true" className="size-4 shrink-0" />
          {t.footer.disclaimer}
        </p>
        <p>{t.footer.project}</p>
      </div>
    </footer>
  );
}
