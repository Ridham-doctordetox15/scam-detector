import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { Clock, ImageOff, WifiOff } from "lucide-react";
import { describe, expect, it, vi } from "vitest";
import { en } from "@/i18n/en";
import { hi } from "@/i18n/hi";
import { API_ERROR_CODES, CLIENT_ERROR_CODES } from "@/lib/errors";
import type { AnalyzeResponse, RiskLevel } from "@/lib/types";
import { recorded, renderWithI18n } from "@/test/render";
import { Analyzer } from "./Analyzer";
import { ErrorNotice, errorIcon } from "./ErrorNotice";
import { THEME_STORAGE_KEY } from "./Providers";
import { RiskGauge } from "./RiskGauge";
import { ThemeSwitch } from "./ThemeSwitch";

async function violations(container: HTMLElement) {
  const results = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  return results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

describe("RiskGauge", () => {
  it.each<RiskLevel>(["low", "medium", "high"])("shows the %s band only: a labelled image, no numbers, no value attributes", (risk) => {
    const { container } = renderWithI18n(<RiskGauge risk={risk} />);
    const gauge = screen.getByRole("img", { name: `Risk level: ${en.result.gaugeBand[risk]}` });
    expect(gauge).toBe(screen.getByTestId("risk-gauge"));
    // Not a meter/progressbar, and no attribute that could carry a value.
    expect(container.querySelector('[role="meter"], [role="progressbar"], [aria-valuenow], [aria-valuetext]')).toBeNull();
    expect(container.textContent).not.toMatch(/\d/);
  });

  it("labels the band in Hindi too", () => {
    renderWithI18n(<RiskGauge risk="high" />, { lang: "hi" });
    expect(screen.getByRole("img", { name: `जोखिम का स्तर: ${hi.result.gaugeBand.high}` })).toBeInTheDocument();
  });
});

describe("ThemeSwitch", () => {
  it("defaults to System and remembers the choice", async () => {
    renderWithI18n(<ThemeSwitch />);
    const group = screen.getByRole("radiogroup", { name: en.theme.label });
    expect(within(group).getByRole("radio", { name: en.theme.system })).toHaveAttribute("aria-checked", "true");
    await userEvent.click(within(group).getByRole("radio", { name: en.theme.dark }));
    expect(within(group).getByRole("radio", { name: en.theme.dark })).toHaveAttribute("aria-checked", "true");
    await waitFor(() => expect(document.documentElement).toHaveClass("dark"));
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    await userEvent.click(within(group).getByRole("radio", { name: en.theme.light }));
    await waitFor(() => expect(document.documentElement).not.toHaveClass("dark"));
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  });

  it("still switches when storage is blocked", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    renderWithI18n(<ThemeSwitch />);
    await userEvent.click(screen.getByRole("radio", { name: en.theme.dark }));
    expect(screen.getByRole("radio", { name: en.theme.dark })).toHaveAttribute("aria-checked", "true");
  });
});

describe("states", () => {
  it("shows a friendly empty state before anything is checked", () => {
    renderWithI18n(<Analyzer backend={{ apiUrl: "" }} />);
    expect(screen.getByText(en.empty.title)).toBeInTheDocument();
    expect(screen.queryByTestId("result-card")).not.toBeInTheDocument();
  });

  it("shows a skeleton (hidden from screen readers) while checking, then the result", async () => {
    let resolve: (r: AnalyzeResponse) => void = () => undefined;
    const api = {
      analyzeText: vi.fn(() => new Promise<AnalyzeResponse>((r) => (resolve = r))),
      analyzeImage: vi.fn(),
      sendFeedback: vi.fn(),
    };
    const { container } = renderWithI18n(
      <Analyzer api={api} backend={{ apiUrl: "https://api.test", check: vi.fn().mockResolvedValue({ status: "ok", components: {} }) }} />,
    );
    await waitFor(() => expect(screen.getByLabelText(en.form.textLabel)).toBeEnabled());
    await userEvent.type(screen.getByLabelText(en.form.textLabel), "hello");
    await userEvent.click(screen.getByRole("button", { name: en.form.submit }));
    const skeleton = screen.getByTestId("result-skeleton");
    expect(skeleton).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByTestId("status")).toHaveTextContent(en.form.analyzingText);
    expect(await violations(container)).toEqual([]);
    await act(async () => resolve(recorded("en_lunch")));
    expect(await screen.findByTestId("result-card")).toBeInTheDocument();
  });

  it("gives every error code an icon, and shows the reference id", () => {
    expect(errorIcon("network_error")).toBe(WifiOff);
    expect(errorIcon("rate_limited")).toBe(Clock);
    expect(errorIcon("unsupported_type")).toBe(ImageOff);
    for (const code of [...API_ERROR_CODES, ...CLIENT_ERROR_CODES, "never_seen_before"]) expect(errorIcon(code)).toBeTruthy();
    renderWithI18n(<ErrorNotice error={{ code: "rate_limited", requestId: "req-7", retryAfterS: 9 }} />);
    expect(screen.getByText(/9 seconds/)).toBeInTheDocument();
    expect(screen.getByText("req-7")).toBeInTheDocument();
  });
});

describe("privacy dialog", () => {
  it("opens from the input card, lists every privacy point, and closes with Escape", async () => {
    const { container } = renderWithI18n(<Analyzer backend={{ apiUrl: "" }} />);
    await userEvent.click(screen.getByRole("button", { name: en.privacyDialog.trigger }));
    const dialog = await screen.findByRole("dialog", { name: en.privacyDialog.title });
    for (const item of en.about.privacy) expect(within(dialog).getByText(item)).toBeInTheDocument();
    expect(await violations(container.ownerDocument.body)).toEqual([]);
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});

describe("accessibility in the dark theme", () => {
  it("has no violations with a result shown", async () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "dark");
    const { container } = renderWithI18n(<Analyzer backend={{ apiUrl: "" }} />);
    await waitFor(() => expect(document.documentElement).toHaveClass("dark"));
    await userEvent.click(document.querySelector('[data-sample-id="en_otp_call"]') as HTMLElement);
    await screen.findByTestId("result-card");
    expect(await violations(container)).toEqual([]);
  });

  it("has no violations with an error shown", async () => {
    const { container } = renderWithI18n(<Analyzer backend={{ apiUrl: "" }} />);
    const form = (screen.getByLabelText(en.form.textLabel) as HTMLTextAreaElement).closest("form")!;
    await act(async () => form.requestSubmit());
    await screen.findByTestId("error-notice");
    expect(await violations(container)).toEqual([]);
  });
});
