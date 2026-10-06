"use client";

import { Expand, ImageUp, X } from "lucide-react";
import { useState, type DragEvent } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { useI18n } from "@/i18n/I18nProvider";
import { fmt } from "@/lib/format";
import { ACCEPTED_IMAGE_TYPES } from "@/lib/validateImage";
import { cn } from "@/lib/utils";

export interface UploadPreview {
  url: string;
  name: string;
  alt: string;
}

export interface UploadZoneProps {
  disabled: boolean;
  busy: boolean;
  preview: UploadPreview | null;
  describedBy: string;
  onFile: (file: File | undefined) => void;
  onRemove: () => void;
}

/**
 * Drag-and-drop area plus a real file input. The input is visually hidden but focusable; its
 * label is the visible button, so keyboard users get the native file picker and a focus ring.
 */
export function UploadZone({ disabled, busy, preview, describedBy, onFile, onRemove }: UploadZoneProps) {
  const { t } = useI18n();
  const [dragOver, setDragOver] = useState(false);

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragOver(false);
    if (!disabled) onFile(event.dataTransfer.files[0]);
  }

  return (
    <div
      data-testid="dropzone"
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={onDrop}
      className={cn(
        "relative rounded-2xl border-2 border-dashed border-input bg-subtle p-5 transition-colors",
        dragOver && "border-primary bg-accent",
        disabled && "opacity-70",
      )}
    >
      {!preview ? (
        <div className="flex flex-col items-center gap-3 py-4 text-center">
          <span className={cn("grid size-12 place-items-center rounded-2xl bg-card text-primary shadow-soft transition-transform", dragOver && "scale-110")}>
            <ImageUp aria-hidden="true" className="size-6" />
          </span>
          <p id="drop-hint" className="max-w-sm text-sm text-muted-foreground">
            {dragOver ? t.form.dropActive : t.form.dropHint}
          </p>
          <FileInput disabled={disabled} describedBy={describedBy} onFile={onFile} label={t.form.chooseFile} />
        </div>
      ) : (
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
          <Dialog>
            <DialogTrigger asChild>
              <button type="button" className="group relative w-fit overflow-hidden rounded-xl border bg-card" aria-label={t.form.viewFullSize}>
                {/* eslint-disable-next-line @next/next/no-img-element -- local preview, no optimizer */}
                <img src={preview.url} alt={preview.alt} className="h-44 w-auto max-w-[9rem] object-cover object-top" />
                <span className="absolute inset-x-0 bottom-0 flex items-center justify-center gap-1 bg-foreground/70 py-1 text-xs font-medium text-background opacity-0 transition group-hover:opacity-100 group-focus-visible:opacity-100">
                  <Expand aria-hidden="true" className="size-3" />
                </span>
              </button>
            </DialogTrigger>
            <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-md">
              <DialogTitle>{t.form.fullSizeTitle}</DialogTitle>
              <DialogDescription className="break-all">{preview.name}</DialogDescription>
              {/* eslint-disable-next-line @next/next/no-img-element -- local preview, no optimizer */}
              <img src={preview.url} alt={preview.alt} className="w-full rounded-lg border" />
            </DialogContent>
          </Dialog>
          <div className="min-w-0 space-y-3">
            <p id="drop-hint" className="break-all text-sm font-medium">
              {fmt(t.form.selectedFile, { name: preview.name })}
            </p>
            <div className="flex flex-wrap gap-2">
              <FileInput disabled={disabled} describedBy={describedBy} onFile={onFile} label={t.form.chooseFile} subtle />
              <Button type="button" variant="ghost" size="sm" onClick={onRemove} disabled={busy}>
                <X aria-hidden="true" />
                {t.form.removeImage}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function FileInput({ disabled, describedBy, onFile, label, subtle = false }: { disabled: boolean; describedBy: string; onFile: (f: File | undefined) => void; label: string; subtle?: boolean }) {
  return (
    <span>
      <input
        id="screenshot-input"
        type="file"
        accept={ACCEPTED_IMAGE_TYPES.join(",")}
        className="peer visually-hidden"
        disabled={disabled}
        aria-describedby={`drop-hint ${describedBy}`}
        onChange={(event) => {
          onFile(event.target.files?.[0]);
          event.target.value = ""; // allow re-selecting the same file
        }}
      />
      <label
        htmlFor="screenshot-input"
        className={cn(
          "inline-flex h-9 cursor-pointer items-center justify-center gap-2 rounded-md px-4 text-sm font-medium shadow-xs transition",
          "peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-ring",
          "peer-disabled:cursor-not-allowed peer-disabled:opacity-50",
          subtle ? "border bg-card hover:bg-secondary" : "bg-primary text-primary-foreground hover:bg-primary/90",
        )}
      >
        {label}
      </label>
    </span>
  );
}
