/**
 * Clickable samples (data in samples.json, shared with scripts/record-demo.mjs). Text samples are
 * sent as-is; image samples are the screenshots generated in Phase 8 (src/ocr/sample_screenshots.py),
 * copied to public/samples/. `expected` is what the sample was written to be - the result shown is
 * whatever the real API returned, even when the two disagree.
 */
import data from "./samples.json";

export type SampleExpected = "scam" | "safe";

export type SampleTitleKey =
  | "enKycLink" | "enOtpCall" | "hinglishBijliLink" | "hinglishLottery" | "enLunch" | "hinglishViOffer"
  | "hindiKycLink" | "shotSmsKyc" | "shotWhatsappLottery" | "shotSmsLunch" | "shotDarkParcel" | "shotHindiKyc";

interface SampleBase {
  id: string;
  expected: SampleExpected;
  titleKey: SampleTitleKey;
}

export interface TextSample extends SampleBase {
  kind: "text";
  text: string;
}

export interface ImageSample extends SampleBase {
  kind: "image";
  file: string; // path under public/
}

export type Sample = TextSample | ImageSample;

export const TEXT_SAMPLES: TextSample[] = data.text.map((s) => ({ ...s, kind: "text" }) as TextSample);
export const IMAGE_SAMPLES: ImageSample[] = data.image.map((s) => ({ ...s, kind: "image" }) as ImageSample);
export const ALL_SAMPLES: Sample[] = [...TEXT_SAMPLES, ...IMAGE_SAMPLES];

export const findSample = (id: string): Sample | undefined => ALL_SAMPLES.find((s) => s.id === id);
