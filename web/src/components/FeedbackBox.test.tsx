import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { en } from "@/i18n/en";
import { ApiError } from "@/lib/api";
import { renderWithI18n } from "@/test/render";
import { FeedbackBox } from "./FeedbackBox";

const buttons = () => [screen.getByRole("button", { name: en.feedback.yes }), screen.getByRole("button", { name: en.feedback.no })];
/** The permanent inline status inside the feedback group (toasts repeat the message elsewhere). */
const inlineStatus = () => within(screen.getByRole("group", { name: en.feedback.question })).getByRole("status");

describe("FeedbackBox", () => {
  it("thanks the user on 201 and disables both buttons", async () => {
    const send = vi.fn().mockResolvedValue(undefined);
    renderWithI18n(<FeedbackBox predictionId="p1" send={send} />);
    await userEvent.click(screen.getByRole("button", { name: en.feedback.yes }));
    await waitFor(() => expect(inlineStatus()).toHaveTextContent(en.feedback.thanks));
    expect(await screen.findByText(en.feedback.toastSaved)).toBeInTheDocument(); // toast
    expect(send).toHaveBeenCalledWith("p1", "correct");
    for (const b of buttons()) expect(b).toBeDisabled();
  });

  it("sends 'incorrect' for No", async () => {
    const send = vi.fn().mockResolvedValue(undefined);
    renderWithI18n(<FeedbackBox predictionId="p2" send={send} />);
    await userEvent.click(screen.getByRole("button", { name: en.feedback.no }));
    await waitFor(() => expect(send).toHaveBeenCalledWith("p2", "incorrect"));
  });

  it("explains a 404 (too old after a restart) and stays disabled", async () => {
    const send = vi.fn().mockRejectedValue(new ApiError("unknown_prediction", 404, "x"));
    renderWithI18n(<FeedbackBox predictionId="p" send={send} />);
    await userEvent.click(screen.getByRole("button", { name: en.feedback.yes }));
    await waitFor(() => expect(inlineStatus()).toHaveTextContent(en.errors.unknown_prediction));
    expect(await screen.findByText(en.feedback.toastFailed)).toBeInTheDocument(); // toast
    for (const b of buttons()) expect(b).toBeDisabled();
  });

  it("says feedback isn't available on 503 and stays disabled", async () => {
    const send = vi.fn().mockRejectedValue(new ApiError("feedback_not_configured", 503, "x"));
    renderWithI18n(<FeedbackBox predictionId="p" send={send} />);
    await userEvent.click(screen.getByRole("button", { name: en.feedback.no }));
    await waitFor(() => expect(inlineStatus()).toHaveTextContent(en.errors.feedback_not_configured));
    for (const b of buttons()) expect(b).toBeDisabled();
  });

  it.each([
    ["rate limit", new ApiError("rate_limited", 429, "x", null, 12), /12 seconds/],
    ["network error", new ApiError("network_error", 0, "x"), new RegExp(en.errors.network_error)],
  ])("offers a retry after a %s", async (_name, error, message) => {
    const send = vi.fn().mockRejectedValueOnce(error).mockResolvedValueOnce(undefined);
    renderWithI18n(<FeedbackBox predictionId="p" send={send} />);
    await userEvent.click(screen.getByRole("button", { name: en.feedback.yes }));
    await waitFor(() => expect(inlineStatus()).toHaveTextContent(message));
    expect(inlineStatus()).toHaveTextContent(en.feedback.retry);
    for (const b of buttons()) expect(b).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: en.feedback.yes }));
    await waitFor(() => expect(inlineStatus()).toHaveTextContent(en.feedback.thanks));
    expect(send).toHaveBeenCalledTimes(2);
  });

  it("sends only once on a double click", async () => {
    let resolve: () => void = () => undefined;
    const send = vi.fn(() => new Promise<void>((r) => (resolve = r)));
    renderWithI18n(<FeedbackBox predictionId="p" send={send} />);
    const yes = screen.getByRole("button", { name: en.feedback.yes });
    await userEvent.dblClick(yes);
    resolve();
    await waitFor(() => expect(inlineStatus()).toHaveTextContent(en.feedback.thanks));
    expect(send).toHaveBeenCalledTimes(1);
  });
});
