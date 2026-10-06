import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { describe, expect, it } from "vitest";
import type { UiLang } from "@/i18n/I18nProvider";
import { renderWithI18n } from "@/test/render";
import { AboutContent } from "./AboutContent";
import { Analyzer } from "./Analyzer";
import { SiteFooter } from "./SiteFooter";
import { SiteHeader } from "./SiteHeader";

// jsdom has no layout engine, so colour contrast is checked separately (contrast.test.ts).
async function violations(container: HTMLElement) {
  const results = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  return results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

function Page({ children }: { children: React.ReactNode }) {
  return (
    <>
      <SiteHeader />
      <main id="main" tabIndex={-1}>
        {children}
      </main>
      <SiteFooter />
    </>
  );
}

describe.each<UiLang>(["en", "hi"])("accessibility (axe) in %s", (lang) => {
  it("analyze page (demo mode) has no violations", async () => {
    const { container } = renderWithI18n(<Page><Analyzer backend={{ apiUrl: "" }} /></Page>, { lang });
    expect(await violations(container)).toEqual([]);
  });

  it("analyze page with a text result has no violations", async () => {
    const { container } = renderWithI18n(<Page><Analyzer backend={{ apiUrl: "" }} /></Page>, { lang });
    await userEvent.click(document.querySelector('[data-sample-id="hindi_kyc_link"]') as HTMLElement);
    await screen.findByTestId("result-card");
    expect(await violations(container)).toEqual([]);
  });

  it("analyze page with a screenshot result has no violations", async () => {
    const { container } = renderWithI18n(<Page><Analyzer backend={{ apiUrl: "" }} /></Page>, { lang });
    await userEvent.click(document.querySelector('[data-sample-id="shot_dark_parcel"]') as HTMLElement);
    await screen.findByTestId("result-card");
    expect(await violations(container)).toEqual([]);
  });

  it("about page has no violations", async () => {
    const { container } = renderWithI18n(<Page><AboutContent /></Page>, { lang });
    expect(await violations(container)).toEqual([]);
  });
});
