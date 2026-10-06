/**
 * Numbers shown on the About page. Every value is copied verbatim (as a string, never recomputed
 * or rounded) from results.md, and each block names the results.md section it came from.
 * A test checks that each value still appears in results.md.
 */

/** results.md section headings, shown next to each block as its source. */
export const SOURCES = {
  phase4Test: "Transformer fine-tuning (Phase 4) › Real test set, all systems",
  phase4Loso: "Transformer fine-tuning (Phase 4) › Leave-one-source-out",
  phase4Paired: "Transformer fine-tuning (Phase 4) › Real test set, all systems (paired difference)",
  rag: "Phase 6 RAG block (run 2026-09-28) › Top-1/top-3 hit rate",
  ocr: "Screenshot OCR (Phase 8) › Generated sample screenshots (synthetic, easier than real)",
  ocrReal: "Screenshot OCR (Phase 8) › Real phone screenshots (manual check)",
  indianTest: "Data (Phases 1 and 2) › Hand-collected real Indian test set",
} as const;

export type SourceKey = keyof typeof SOURCES;

export interface ClassifierRow {
  system: string;
  operatingPoint: "f1Tuned" | "recallFirst";
  f1: string;
  rocAuc: string;
  promoFlagged: string;
  /** ROC-AUC on the HF phishing-email source when it was left out of training. */
  unseenAuc: string;
  deployed: boolean;
}

/** Test set: 3,682 real messages, 26.1% scam, 153 legitimate promotion/service rows. */
export const TEST_SET = { rows: "3,682", scamShare: "26.1%", promoRows: "153" } as const;

export const CLASSIFIER_ROWS: ClassifierRow[] = [
  { system: "TF-IDF + Linear SVM", operatingPoint: "f1Tuned", f1: "0.9505", rocAuc: "0.9947", promoFlagged: "19%", unseenAuc: "0.5977", deployed: true },
  { system: "TF-IDF + Linear SVM", operatingPoint: "recallFirst", f1: "0.9473", rocAuc: "0.9947", promoFlagged: "22%", unseenAuc: "0.5977", deployed: false },
  { system: "TF-IDF + Logistic Regression", operatingPoint: "recallFirst", f1: "0.9448", rocAuc: "0.9948", promoFlagged: "20%", unseenAuc: "0.6019", deployed: false },
  { system: "DistilBERT (fine-tuned)", operatingPoint: "recallFirst", f1: "0.9477", rocAuc: "0.9955", promoFlagged: "22%", unseenAuc: "0.5487", deployed: false },
  { system: "MuRIL (fine-tuned)", operatingPoint: "recallFirst", f1: "0.9397", rocAuc: "0.9957", promoFlagged: "32%", unseenAuc: "0.5307", deployed: false },
];

/** DistilBERT minus TF-IDF + Linear SVM, both at the recall-first threshold, same test rows. */
export const PAIRED_F1 = { diff: "+0.0004", low: "-0.0085", high: "+0.0097" } as const;

export interface RagRow {
  split: "overall" | "written" | "real";
  n: string;
  top1: string;
  top3: string;
}

/** Chosen variant (phrases_how). Matched rows only. */
export const RAG_ROWS: RagRow[] = [
  { split: "overall", n: "57", top1: "68%", top3: "89%" },
  { split: "written", n: "40", top1: "80%", top3: "95%" },
  { split: "real", n: "17", top1: "41%", top3: "76%" },
];

export interface OcrRow {
  sample: string;
  cer: string;
  keywordRecall: string;
  verdict: string;
}

/** Final hybrid OCR on the 5 generated screenshots (development set: optimistic). */
export const OCR_ROWS: OcrRow[] = [
  { sample: "sms_kyc_scam_en", cer: "0.019", keywordRecall: "1.00", verdict: "scam / high" },
  { sample: "whatsapp_lottery_scam_hinglish", cer: "0.012", keywordRecall: "1.00", verdict: "scam / high" },
  { sample: "sms_lunch_safe_en", cer: "0.031", keywordRecall: "1.00", verdict: "safe / low" },
  { sample: "whatsapp_dark_parcel_scam_en", cer: "0.005", keywordRecall: "1.00", verdict: "scam / high" },
  { sample: "sms_kyc_scam_hi (Devanagari)", cer: "0.000", keywordRecall: "1.00", verdict: "scam / medium" },
];

/** Warm OCR time per 720x1280 image on the dev machine (not deployment hardware). */
export const OCR_SECONDS = { min: "3.2", max: "4.2" } as const;

/** Which results.md section each About "finding" is drawn from (keys match the dictionaries). */
export const FINDING_SOURCES = {
  transformer: "phase4Paired",
  unseen: "phase4Loso",
  promotions: "phase4Test",
  rag: "rag",
  ocr: "ocr",
  realScreenshots: "ocrReal",
  noIndianSet: "indianTest",
} as const satisfies Record<string, SourceKey>;

export type FindingKey = keyof typeof FINDING_SOURCES;
