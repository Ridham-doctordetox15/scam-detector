"use client";

import { LazyMotion, MotionConfig } from "motion/react";
import { ThemeProvider } from "next-themes";
import dynamic from "next/dynamic";
import type { ReactNode } from "react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { I18nProvider, type UiLang } from "@/i18n/I18nProvider";

export const THEME_STORAGE_KEY = "scam-checker.theme";

// Motion's animation features load after first paint (elements render normally meanwhile), and the
// toast renderer loads on its own: both stay out of the first-load JavaScript.
const loadMotionFeatures = () => import("@/lib/motionFeatures").then((mod) => mod.default);
const Toaster = dynamic(() => import("@/components/ui/sonner").then((mod) => mod.Toaster), { ssr: false });

/**
 * App-wide providers.
 * - Theme: System / Light / Dark, default System, remembered in localStorage by next-themes, which
 *   sets the `dark` class before first paint (one small inline script; our CSP doesn't restrict
 *   scripts, and it contacts nothing).
 * - Motion: the small `domAnimation` feature set only, loaded asynchronously, and
 *   `reducedMotion="user"` so every animation is skipped when the system asks for reduced motion.
 */
export function Providers({ children, initialLang }: { children: ReactNode; initialLang?: UiLang }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem storageKey={THEME_STORAGE_KEY} disableTransitionOnChange>
      <I18nProvider initialLang={initialLang}>
        <LazyMotion features={loadMotionFeatures} strict>
          <MotionConfig reducedMotion="user">
            <TooltipProvider delayDuration={250}>
              {children}
              <Toaster position="bottom-center" closeButton />
            </TooltipProvider>
          </MotionConfig>
        </LazyMotion>
      </I18nProvider>
    </ThemeProvider>
  );
}
