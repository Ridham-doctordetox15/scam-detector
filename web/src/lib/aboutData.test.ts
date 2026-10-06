import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { en } from "@/i18n/en";
import { CLASSIFIER_ROWS, OCR_ROWS, OCR_SECONDS, PAIRED_F1, RAG_ROWS, TEST_SET } from "./aboutData";

// The About page must never show a number that isn't in results.md.
const RESULTS = readFileSync(join(__dirname, "..", "..", "..", "results.md"), "utf-8");

/** True if `value` appears in results.md as a whole token (so "0.95" can't match "0.9505"). */
function inResults(value: string): boolean {
  const escaped = value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(^|[^\\d.])${escaped}(?![\\d])`).test(RESULTS);
}

describe("About page numbers", () => {
  it("classifier table values all appear in results.md", () => {
    for (const row of CLASSIFIER_ROWS) {
      for (const v of [row.f1, row.rocAuc, row.promoFlagged, row.unseenAuc]) expect(inResults(v), `${row.system}: ${v}`).toBe(true);
    }
  });

  it("each classifier row matches its results.md table row", () => {
    // The Phase 4 table row lists F1, ROC-AUC, ... and the promo rate for the same system/threshold.
    const deployed = CLASSIFIER_ROWS.find((r) => r.deployed)!;
    expect(RESULTS).toMatch(/TF-IDF \+ Linear SVM \(F1-tuned threshold, Phase 3\.5 protocol\) \| -0\.023 \|[^\n]*\| 0\.9505 \| 0\.9947 \|[^\n]*\| 19% \|/);
    expect(deployed.f1).toBe("0.9505");
    expect(RESULTS).toMatch(/\*\*distilbert-base-uncased\*\* \(recall-first threshold\)[^\n]*\| 0\.9477 \| 0\.9955 \|[^\n]*\| 22% \|/);
  });

  it("marks the model the API actually serves as deployed (the F1-tuned SVM)", () => {
    const deployed = CLASSIFIER_ROWS.filter((r) => r.deployed);
    expect(deployed).toHaveLength(1);
    expect(deployed[0]).toMatchObject({ system: "TF-IDF + Linear SVM", operatingPoint: "f1Tuned" });
  });

  it("RAG, OCR, test-set and paired-difference values all appear in results.md", () => {
    const values = [
      ...RAG_ROWS.flatMap((r) => [r.n, r.top1, r.top3]),
      ...OCR_ROWS.flatMap((r) => [r.cer, r.keywordRecall]),
      OCR_SECONDS.min,
      OCR_SECONDS.max,
      TEST_SET.rows,
      TEST_SET.scamShare,
      TEST_SET.promoRows,
      `${PAIRED_F1.diff} (${PAIRED_F1.low} to ${PAIRED_F1.high})`,
    ];
    for (const v of values) expect(inResults(v), v).toBe(true);
  });

  it("every decimal, percentage or thousands number in the English findings appears in results.md", () => {
    const text = [...Object.values(en.about.findings), en.about.resultsIntro].join(" ");
    const numbers = text.match(/[+-]?\d+\.\d+|\d+(?:\.\d+)?%|\d{1,3}(?:,\d{3})+/g) ?? [];
    expect(numbers.length).toBeGreaterThan(8);
    for (const n of numbers) expect(inResults(n), n).toBe(true);
  });

  it("states that the real-screenshot check and the real Indian test set are still pending", () => {
    expect(RESULTS).toMatch(/### Real phone screenshots \(manual check\)\s+\*\*Not yet run\.\*\*/);
    expect(RESULTS).toMatch(/### Hand-collected real Indian test set\s+Not built yet\./);
    expect(en.about.findings.realScreenshots).toMatch(/not been run yet/);
    expect(en.about.findings.noIndianSet).toMatch(/no real Indian test set yet/);
  });
});
