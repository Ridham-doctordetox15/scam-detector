"use client";

import { ArrowRight, Database, EyeOff, ImageOff, KeyRound, Lock, Send, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { useI18n } from "@/i18n/I18nProvider";

/** One icon per privacy point, in the order of `about.privacy`. */
export const PRIVACY_ICONS: LucideIcon[] = [Send, EyeOff, ImageOff, Database, KeyRound];

export function PrivacyList({ items }: { items: string[] }) {
  return (
    <ul className="space-y-3">
      {items.map((item, i) => {
        const Icon = PRIVACY_ICONS[i] ?? Lock;
        return (
          <li key={i} className="flex gap-3">
            <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground">
              <Icon aria-hidden="true" className="size-4" />
            </span>
            <span className="text-sm">{item}</span>
          </li>
        );
      })}
    </ul>
  );
}

/** "What happens to my message?" - the privacy summary, one click away from the input. */
export function PrivacyDialog() {
  const { t } = useI18n();
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button type="button" variant="link" className="h-auto gap-1.5 p-0 text-sm font-medium">
          <Lock aria-hidden="true" className="size-3.5" />
          {t.privacyDialog.trigger}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t.privacyDialog.title}</DialogTitle>
          <DialogDescription>{t.privacyDialog.description}</DialogDescription>
        </DialogHeader>
        <PrivacyList items={t.about.privacy} />
        <DialogFooter className="gap-2 sm:justify-between">
          <Button asChild variant="link" className="px-0">
            <Link href="/about/" prefetch={false}>
              {t.privacyDialog.more}
              <ArrowRight aria-hidden="true" />
            </Link>
          </Button>
          <DialogClose asChild>
            <Button type="button" variant="outline">
              {t.privacyDialog.close}
            </Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
