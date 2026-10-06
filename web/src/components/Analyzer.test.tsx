import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { en } from "@/i18n/en";
import { hi } from "@/i18n/hi";
import { ApiError } from "@/lib/api";
import { DEMO } from "@/lib/demo";
import { TEXT_SAMPLES } from "@/lib/samples";
import type { AnalyzeResponse, HealthResponse } from "@/lib/types";
import { recorded, renderWithI18n } from "@/test/render";
import { Analyzer, type AnalyzerApi } from "./Analyzer";
import { LanguageSwitch } from "./LanguageSwitch";

const OK: HealthResponse = { status: "ok", components: {} };

function fakeApi(overrides: Partial<AnalyzerApi> = {}) {
  return {
    analyzeText: vi.fn<AnalyzerApi["analyzeText"]>().mockResolvedValue(recorded("en_kyc_link")),
    analyzeImage: vi.fn<AnalyzerApi["analyzeImage"]>().mockResolvedValue(recorded("shot_dark_parcel")),
    sendFeedback: vi.fn<AnalyzerApi["sendFeedback"]>().mockResolvedValue(undefined),
    ...overrides,
  };
}

function setup({ health = OK as HealthResponse | null, apiUrl = "https://api.test", api = fakeApi(), fetchSample = vi.fn().mockResolvedValue(new Blob(["png"], { type: "image/png" })) } = {}) {
  const check = vi.fn().mockResolvedValue(health);
  const utils = renderWithI18n(<Analyzer api={api} backend={{ apiUrl, check }} fetchSample={fetchSample} />);
  return { ...utils, api, check, fetchSample };
}

const textarea = () => screen.getByLabelText(en.form.textLabel) as HTMLTextAreaElement;
const submitText = () => screen.getByRole("button", { name: en.form.submit });
const sampleButton = (id: string) => document.querySelector(`[data-sample-id="${id}"]`) as HTMLButtonElement;
const waitForLive = () => waitFor(() => expect(textarea()).toBeEnabled());

describe("demo mode: backend not hosted (no API URL at build time)", () => {
  it("says plainly that the backend isn't hosted and never calls the network", () => {
    const { check, api } = setup({ apiUrl: "" });
    const banner = screen.getByTestId("demo-banner");
    expect(within(banner).getByRole("heading")).toHaveTextContent(en.mode.notHostedTitle);
    expect(banner).toHaveTextContent("The live backend is not hosted yet");
    expect(banner).toHaveTextContent(DEMO.recorded_at.slice(0, 10));
    expect(within(banner).queryByRole("button")).not.toBeInTheDocument(); // nothing to retry
    expect(check).not.toHaveBeenCalled();
    expect(api.analyzeText).not.toHaveBeenCalled();
  });

  it("disables the text box and upload, with an explanation", () => {
    setup({ apiUrl: "" });
    expect(textarea()).toBeDisabled();
    expect(submitText()).toBeDisabled();
    expect(document.getElementById("screenshot-input")).toBeDisabled();
    expect(screen.getByText(en.form.demoDisabled)).toBeInTheDocument();
    expect(textarea()).toHaveAccessibleDescription(expect.stringContaining(en.form.demoDisabled));
  });

  it("shows the recorded response for a sample, clearly marked, without feedback", async () => {
    const { api } = setup({ apiUrl: "" });
    const sample = TEXT_SAMPLES.find((s) => s.id === "hinglish_bijli_link")!;
    await userEvent.click(sampleButton(sample.id));
    const card = await screen.findByTestId("result-card");
    expect(card).toHaveTextContent(/Recorded demo result/);
    expect(within(card).getByTestId("explanation")).toHaveTextContent(DEMO.responses[sample.id]!.explanation);
    expect(within(card).queryByText(en.feedback.question)).not.toBeInTheDocument();
    expect(textarea().value).toBe(sample.text);
    expect(api.analyzeText).not.toHaveBeenCalled();
  });

  it("shows recorded screenshot results too", async () => {
    const { api, fetchSample } = setup({ apiUrl: "" });
    await userEvent.click(sampleButton("shot_hindi_kyc"));
    const card = await screen.findByTestId("result-card");
    expect(card).toHaveTextContent(/Recorded demo result/);
    expect(within(card).getByTestId("red-flags")).toHaveAttribute("lang", "hi");
    expect(fetchSample).not.toHaveBeenCalled();
    expect(api.analyzeImage).not.toHaveBeenCalled();
  });

  it("refuses to 'analyze' new text even if the form is forced to submit", async () => {
    const { api } = setup({ apiUrl: "" });
    fireEvent.change(textarea(), { target: { value: "My own new message http://evil.tk" } });
    fireEvent.submit(textarea().closest("form")!);
    expect(await screen.findByText(en.errors.demo_unavailable)).toBeInTheDocument();
    expect(screen.queryByTestId("result-card")).not.toBeInTheDocument();
    expect(api.analyzeText).not.toHaveBeenCalled();
  });
});

describe("demo mode: server unreachable", () => {
  it("appears only when /health fails, with a working retry", async () => {
    const { check } = setup({ health: null });
    const banner = await screen.findByTestId("demo-banner");
    expect(banner).toHaveTextContent(en.mode.unreachableTitle);
    expect(textarea()).toBeDisabled();

    check.mockResolvedValueOnce(OK);
    await userEvent.click(within(banner).getByRole("button", { name: en.mode.retry }));
    await waitForLive();
    expect(screen.queryByTestId("demo-banner")).not.toBeInTheDocument();
    expect(screen.getByText(en.mode.nowLive)).toBeInTheDocument();
  });

  it("announces when the server is still unreachable", async () => {
    setup({ health: null });
    const banner = await screen.findByTestId("demo-banner");
    await userEvent.click(within(banner).getByRole("button", { name: en.mode.retry }));
    expect(await screen.findByText(en.mode.stillUnreachable)).toBeInTheDocument();
    expect(screen.getByTestId("demo-banner")).toBeInTheDocument();
  });

  it("treats a 503 'unavailable' health answer as demo mode", async () => {
    setup({ health: { status: "unavailable", components: {} } });
    expect(await screen.findByTestId("demo-banner")).toBeInTheDocument();
  });

  it("does not appear when the server is up", async () => {
    setup();
    await waitForLive();
    expect(screen.queryByTestId("demo-banner")).not.toBeInTheDocument();
  });
});

describe("live mode", () => {
  it("checks typed text, announces it and moves focus to the result heading", async () => {
    const { api } = setup();
    await waitForLive();
    await userEvent.type(textarea(), "Your KYC is pending");
    await userEvent.click(submitText());
    const heading = await screen.findByRole("heading", { name: en.result.heading });
    expect(api.analyzeText).toHaveBeenCalledWith("Your KYC is pending");
    await waitFor(() => expect(heading).toHaveFocus());
    expect(screen.getByTestId("status")).toHaveTextContent(`${en.result.heading}: ${en.result.verdict.scam}, ${en.result.risk.high}`);
    expect(screen.getByText(en.feedback.question)).toBeInTheDocument();
  });

  it("shows a loading status while waiting and blocks double submits", async () => {
    let resolve: (r: AnalyzeResponse) => void = () => undefined;
    const api = fakeApi({ analyzeText: vi.fn(() => new Promise<AnalyzeResponse>((r) => (resolve = r))) });
    setup({ api });
    await waitForLive();
    await userEvent.type(textarea(), "hello");
    const form = textarea().closest("form")!;
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(screen.getByTestId("status")).toHaveTextContent(en.form.analyzingText);
    expect(submitText()).toBeDisabled();
    await act(async () => resolve(recorded("en_lunch")));
    await screen.findByTestId("result-card");
    expect(api.analyzeText).toHaveBeenCalledTimes(1);
  });

  it("validates empty and over-long text in the browser", async () => {
    const { api } = setup();
    await waitForLive();
    await userEvent.click(submitText());
    expect(await screen.findByText(en.errors.empty_text)).toBeInTheDocument();
    fireEvent.change(textarea(), { target: { value: "a".repeat(5001) } });
    expect(screen.getByText(/5001 \/ 5000 characters/)).toBeInTheDocument();
    expect(textarea()).toHaveAttribute("aria-invalid", "true");
    await userEvent.click(submitText());
    expect(api.analyzeText).not.toHaveBeenCalled();
  });

  it("counts characters the way the API does (emoji count once)", async () => {
    setup();
    await waitForLive();
    fireEvent.change(textarea(), { target: { value: "😀😀" } });
    expect(screen.getByText("2 / 5000 characters")).toBeInTheDocument();
  });

  it("shows a friendly API error with the request id", async () => {
    const api = fakeApi({ analyzeText: vi.fn().mockRejectedValue(new ApiError("busy", 503, "x", "req-42")) });
    setup({ api });
    await waitForLive();
    await userEvent.type(textarea(), "hello");
    await userEvent.click(submitText());
    expect(await screen.findByText(en.errors.busy)).toBeInTheDocument();
    expect(screen.getByText("req-42")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("heading", { name: en.errors.heading })).toHaveFocus());
  });

  it("fills and checks a text sample on click", async () => {
    const { api } = setup();
    await waitForLive();
    const sample = TEXT_SAMPLES[0]!;
    await userEvent.click(sampleButton(sample.id));
    await screen.findByTestId("result-card");
    expect(api.analyzeText).toHaveBeenCalledWith(sample.text);
    expect(textarea().value).toBe(sample.text);
  });

  it("uploads a screenshot sample on click", async () => {
    const { api, fetchSample } = setup();
    await waitForLive();
    await userEvent.click(sampleButton("shot_dark_parcel"));
    await screen.findByTestId("result-card");
    expect(fetchSample).toHaveBeenCalledWith("/samples/whatsapp_dark_parcel_scam_en.png");
    expect(api.analyzeImage).toHaveBeenCalledWith(expect.any(Blob), "whatsapp_dark_parcel_scam_en.png");
    expect(screen.getByTestId("status")).toHaveTextContent(en.result.heading);
  });

  it("rejects an unsupported file in the browser and uploads a valid one", async () => {
    const { api } = setup();
    await waitForLive();
    const user = userEvent.setup({ applyAccept: false });
    await user.click(screen.getByRole("tab", { name: en.form.tabImage }));
    const input = document.getElementById("screenshot-input") as HTMLInputElement;

    await user.upload(input, new File(["gif"], "a.gif", { type: "image/gif" }));
    expect(await screen.findByText(en.errors.unsupported_type)).toBeInTheDocument();

    await user.upload(input, new File(["x".repeat(6 * 1024 * 1024)], "big.png", { type: "image/png" }));
    expect(await screen.findByText(en.errors.too_large)).toBeInTheDocument();

    await user.upload(input, new File(["png"], "shot.png", { type: "image/png" }));
    expect(screen.getByAltText(en.form.previewAlt)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: en.form.submitImage }));
    await screen.findByTestId("result-card");
    expect(api.analyzeImage).toHaveBeenCalledWith(expect.any(File), "shot.png");
  });

  it("accepts a dropped screenshot", async () => {
    setup();
    await waitForLive();
    await userEvent.click(screen.getByRole("tab", { name: en.form.tabImage }));
    const file = new File(["png"], "drop.png", { type: "image/png" });
    fireEvent.drop(screen.getByTestId("dropzone"), { dataTransfer: { files: [file] } });
    expect(await screen.findByText("Selected: drop.png")).toBeInTheDocument();
  });

  it("supports arrow keys on the tabs", async () => {
    setup();
    await waitForLive();
    const textTab = screen.getByRole("tab", { name: en.form.tabText });
    textTab.focus();
    await userEvent.keyboard("{ArrowRight}");
    const imageTab = screen.getByRole("tab", { name: en.form.tabImage });
    expect(imageTab).toHaveFocus();
    expect(imageTab).toHaveAttribute("aria-selected", "true");
    // The visible panel is the one labelled by the Screenshot tab (Radix generates the ids).
    expect(screen.getByRole("tabpanel")).toHaveAccessibleName(en.form.tabImage);
  });
});

describe("interface language switch", () => {
  it("changes interface labels and <html lang> but never the result content", async () => {
    renderWithI18n(
      <>
        <LanguageSwitch />
        <Analyzer backend={{ apiUrl: "" }} />
      </>,
    );
    await userEvent.click(sampleButton("en_kyc_link"));
    const explanation = (await screen.findByTestId("explanation")).textContent;
    const flags = screen.getByTestId("red-flags").textContent;

    // A Radix single-choice toggle group: options are radio items with aria-checked.
    const hindiButton = screen.getByRole("radio", { name: "हिंदी" });
    expect(hindiButton).toHaveAttribute("aria-checked", "false");
    await userEvent.click(hindiButton);

    expect(hindiButton).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "EN" })).toHaveAttribute("aria-checked", "false");
    expect(document.documentElement.lang).toBe("hi");
    expect(screen.getByRole("heading", { name: hi.result.redFlags })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: en.result.redFlags })).not.toBeInTheDocument();
    expect(screen.getByTestId("explanation").textContent).toBe(explanation);
    expect(screen.getByTestId("red-flags").textContent).toBe(flags);
    expect(screen.getByTestId("explanation")).toHaveAttribute("lang", "en");
    expect(window.localStorage.getItem("scam-checker.ui-lang")).toBe("hi");
  });

  it("falls back to English when storage is blocked", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    const { I18nProvider } = await import("@/i18n/I18nProvider");
    const { render } = await import("@testing-library/react");
    render(
      <I18nProvider>
        <LanguageSwitch />
      </I18nProvider>,
    );
    expect(screen.getByRole("radio", { name: "EN" })).toHaveAttribute("aria-checked", "true");
    await userEvent.click(screen.getByRole("radio", { name: "हिंदी" }));
    expect(screen.getByRole("radio", { name: "हिंदी" })).toHaveAttribute("aria-checked", "true");
  });
});
