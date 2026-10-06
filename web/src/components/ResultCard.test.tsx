import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { en } from "@/i18n/en";
import type { RiskLevel, Verdict } from "@/lib/types";
import { ALL_RECORDED, recorded, renderWithI18n } from "@/test/render";
import { ResultCard } from "./ResultCard";

describe("ResultCard", () => {
  const verdicts: Verdict[] = ["safe", "suspicious", "scam"];
  const risks: RiskLevel[] = ["low", "medium", "high"];

  it.each(verdicts.flatMap((v) => risks.map((r) => [v, r] as const)))(
    "always puts words on the risk band (%s / %s), so colour is never the only signal",
    (verdict, risk) => {
      const result = { ...recorded("en_lunch"), verdict, risk_level: risk };
      renderWithI18n(<ResultCard result={result} />);
      const band = screen.getByTestId("risk-band");
      expect(band).toHaveTextContent(en.result.verdict[verdict]);
      expect(band).toHaveTextContent(en.result.risk[risk]);
    },
  );

  it.each(ALL_RECORDED)("never renders a probability-like number or timings for %s", (_id, response) => {
    // Inject a fake score field too: the card must not print fields it doesn't know.
    const result = { ...response, scam_probability: 0.9731 } as typeof response;
    const { container } = renderWithI18n(<ResultCard result={result} />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\b0?\.\d{2,}\b/); // 0.97, .973
    expect(text).not.toMatch(/\d+(\.\d+)?\s?%/); // 97%
    // Timings like 1661.6 would be caught here; tiny integers (0, 2) are too common to test this way
    // and are already covered by the decimal check above.
    for (const ms of Object.values(response.timings_ms).filter((v) => !Number.isInteger(v) || v >= 100)) {
      expect(text).not.toContain(String(ms));
    }
    expect(text).not.toContain(response.classifier_model);
  });

  it.each(ALL_RECORDED.filter(([, r]) => r.url_findings.length > 0))(
    "shows defanged links as plain text, never as anchors (%s)",
    (_id, response) => {
      const { container } = renderWithI18n(<ResultCard result={response} />);
      expect(container.querySelectorAll("a")).toHaveLength(0);
      const shown = screen.getAllByTestId("defanged-url").map((el) => el.textContent);
      expect(shown).toEqual(response.url_findings.map((f) => f.url_defanged));
      for (const url of shown) expect(url).toMatch(/^hxxps?:\/\/.*\[\.\]/);
    },
  );

  it.each([
    ["en_kyc_link", "en"],
    ["hindi_kyc_link", "hi"],
    ["hinglish_bijli_link", "hi-Latn"],
  ])("tags %s content with lang=%s", (id, lang) => {
    renderWithI18n(<ResultCard result={recorded(id)} />);
    for (const testId of ["red-flags", "explanation", "what-to-do"]) {
      expect(screen.getByTestId(testId)).toHaveAttribute("lang", lang);
    }
  });

  it("shows the matched pattern as a readable name and says whether it is a scam type", () => {
    renderWithI18n(<ResultCard result={recorded("en_kyc_link")} />);
    expect(screen.getByText("Fake KYC Update / Account Block Threat")).toBeInTheDocument();
    expect(screen.getByText(/a known scam type/)).toBeInTheDocument();
    expect(screen.queryByText(/fake_kyc_update/)).not.toBeInTheDocument();
  });

  it("labels a genuine-message pattern honestly even on a scam result", () => {
    // Real recording: the WhatsApp lottery screenshot matched a genuine pattern.
    const result = recorded("shot_whatsapp_lottery");
    expect(result.matched_pattern).toBe("genuine_bank_statement_notification");
    renderWithI18n(<ResultCard result={result} />);
    expect(screen.getByText(/a type of genuine message/)).toBeInTheDocument();
  });

  it("shows the OCR text (collapsible) and quality band for screenshots", async () => {
    const result = recorded("shot_dark_parcel");
    renderWithI18n(<ResultCard result={result} />);
    const toggle = screen.getByRole("button", { name: en.result.extractedText });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByTestId("extracted-text")).not.toBeInTheDocument();
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByTestId("extracted-text")).toHaveTextContent(result.ocr!.extracted_text.split("\n")[0]!);
    expect(screen.getByText(en.result.ocrQualityValue[result.ocr!.quality])).toBeInTheDocument();
    expect(screen.getByText(/Dark-mode screenshot detected/)).toBeInTheDocument();
  });

  it("marks recorded results and hides feedback in demo mode", () => {
    renderWithI18n(<ResultCard result={recorded("en_kyc_link")} demoDate="2026-09-30" />);
    expect(screen.getByText(/Recorded demo result/)).toHaveTextContent("2026-09-30");
    expect(screen.queryByText(en.feedback.question)).not.toBeInTheDocument();
  });

  it("offers feedback for live results", () => {
    renderWithI18n(<ResultCard result={recorded("en_kyc_link")} />);
    expect(screen.getByText(en.feedback.question)).toBeInTheDocument();
    expect(screen.queryByText(/Recorded demo result/)).not.toBeInTheDocument();
  });
});
