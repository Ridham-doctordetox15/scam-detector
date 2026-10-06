"use client";

import { ShieldCheck } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useI18n } from "@/i18n/I18nProvider";
import { cn } from "@/lib/utils";
import { LanguageSwitch } from "./LanguageSwitch";
import { ThemeSwitch } from "./ThemeSwitch";

// prefetch is off: with Next 16.3's static export, the prefetch of a nested route's segment file
// (about/__next.about.__PAGE__.txt) 404s on plain static hosts. Two small pages don't need it.
export function SiteHeader() {
  const { t } = useI18n();
  const pathname = usePathname() ?? "/";
  const onAbout = pathname.replace(/\/+$/, "").endsWith("/about");

  const navLink = (active: boolean) =>
    cn(
      "inline-flex h-9 items-center rounded-md px-3 text-sm font-medium transition-colors",
      active ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-secondary hover:text-foreground",
    );

  return (
    <header className="sticky top-0 z-40 border-b bg-background/85 backdrop-blur supports-[backdrop-filter]:bg-background/70">
      <a
        href="#main"
        className="absolute left-4 top-[-100px] z-50 rounded-md bg-primary px-4 py-2 font-semibold text-primary-foreground focus:top-2"
      >
        {t.nav.skip}
      </a>
      {/* Phones: [logo + wordmark | language | theme] then the nav on its own row.
          sm and up: one row - logo, nav, language, theme (DOM order matches each layout's reading order). */}
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-2 gap-y-2 px-4 py-2.5 sm:gap-x-4 sm:px-6">
        <Link href="/" prefetch={false} className="mr-auto inline-flex min-h-10 items-center gap-2.5 rounded-md font-semibold tracking-tight">
          <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground shadow-soft">
            <ShieldCheck aria-hidden="true" className="size-[18px]" />
          </span>
          {/* Too wide for the narrowest phones; still read by screen readers there. */}
          <span className="max-[419px]:sr-only">{t.meta.title}</span>
        </Link>
        <nav aria-label={t.nav.label} className="order-last flex w-full gap-1 sm:order-none sm:w-auto">
          <Link href="/" prefetch={false} aria-current={onAbout ? undefined : "page"} className={navLink(!onAbout)}>
            {t.nav.analyze}
          </Link>
          <Link href="/about/" prefetch={false} aria-current={onAbout ? "page" : undefined} className={navLink(onAbout)}>
            {t.nav.about}
          </Link>
        </nav>
        <LanguageSwitch />
        <ThemeSwitch />
      </div>
    </header>
  );
}
