"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useI18n } from "@/i18n/I18nProvider";

const OPTIONS = [
  { value: "system", Icon: Monitor },
  { value: "light", Icon: Sun },
  { value: "dark", Icon: Moon },
] as const;

/** System / Light / Dark. Icon buttons with accessible names and tooltips; default System. */
export function ThemeSwitch() {
  const { t } = useI18n();
  const { theme, setTheme } = useTheme();
  // The stored theme is only known in the browser; render "system" until mounted to match the HTML.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const value = mounted ? (theme ?? "system") : "system";

  return (
    <ToggleGroup
      type="single"
      value={value}
      onValueChange={(next) => next && setTheme(next)}
      aria-label={t.theme.label}
      variant="outline"
      size="sm"
      className="rounded-lg bg-card"
    >
      {OPTIONS.map(({ value: option, Icon }) => (
        <Tooltip key={option}>
          <TooltipTrigger asChild>
            <ToggleGroupItem value={option} aria-label={t.theme[option]} className="w-9 px-0 data-[state=on]:bg-accent data-[state=on]:text-accent-foreground">
              <Icon aria-hidden="true" className="size-4" />
            </ToggleGroupItem>
          </TooltipTrigger>
          <TooltipContent>{t.theme[option]}</TooltipContent>
        </Tooltip>
      ))}
    </ToggleGroup>
  );
}
