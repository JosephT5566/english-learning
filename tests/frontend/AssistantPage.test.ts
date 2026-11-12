import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { authSession } from "$lib/stores/auth";
import AssistantPage from "../../src/routes/assistant/+page.svelte";

const api = vi.hoisted(() => ({
  getGenAIConsent: vi.fn(),
  grantGenAIConsent: vi.fn(),
  withdrawGenAIConsent: vi.fn(),
  streamAssistantReply: vi.fn(),
}));
vi.mock("$env/dynamic/public", () => ({ env: {} }));
vi.mock("$lib/auth", () => ({ getProfile: () => ({ sub: "owner-a" }) }));
vi.mock("$lib/api/client", async (original) => ({
  ...(await original<typeof import("$lib/api/client")>()),
  ...api,
}));

const granted = { genai_consent_at: "2026-11-12T00:00:00Z" };
describe("assistant page composer and consent", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
      },
    );
    authSession.set({ kind: "authenticated", profile: { sub: "owner-a" } });
    api.getGenAIConsent.mockResolvedValue(granted);
    api.grantGenAIConsent.mockResolvedValue(granted);
    api.withdrawGenAIConsent.mockResolvedValue({ genai_consent_at: null });
    api.streamAssistantReply.mockResolvedValue({
      stop: "completed",
      tools: [],
    });
  });
  it("replaces the composer until explicit grant without auto-send", async () => {
    api.getGenAIConsent.mockResolvedValue({ genai_consent_at: null });
    render(AssistantPage);
    await screen.findByRole("button", { name: "Grant consent" });
    expect(
      screen.queryByLabelText("Ask the assistant"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "Your messages and relevant card information are sent to Google Vertex AI. You can withdraw consent here at any time.",
      ),
    ).toBeVisible();
    await fireEvent.click(
      screen.getByRole("button", { name: "Grant consent" }),
    );
    await screen.findByLabelText("Ask the assistant");
    expect(api.streamAssistantReply).not.toHaveBeenCalled();
  });
  it("guards empty, IME, Shift+Enter and in-flight Enter without a Stop control", async () => {
    let finish: (value: { stop: "completed"; tools: [] }) => void = () => {};
    api.streamAssistantReply.mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    render(AssistantPage);
    const input = await screen.findByLabelText("Ask the assistant");
    await fireEvent.keyDown(input, { key: "Enter" });
    expect(api.streamAssistantReply).not.toHaveBeenCalled();
    await fireEvent.input(input, { target: { value: "help me" } });
    await fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    await fireEvent.keyDown(input, { key: "Enter", isComposing: true });
    await fireEvent.keyDown(input, { key: "Enter", keyCode: 229 });
    await fireEvent.compositionStart(input);
    await fireEvent.keyDown(input, { key: "Enter" });
    expect(api.streamAssistantReply).not.toHaveBeenCalled();
    await fireEvent.compositionEnd(input);
    await fireEvent.keyDown(input, { key: "Enter" });
    expect(api.streamAssistantReply).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Replying…" })).toBeDisabled();
    expect(input).toHaveAttribute("readonly");
    expect(
      screen.queryByRole("button", { name: /Stop/ }),
    ).not.toBeInTheDocument();
    await fireEvent.keyDown(input, { key: "Enter" });
    expect(api.streamAssistantReply).toHaveBeenCalledTimes(1);
    finish({ stop: "completed", tools: [] });
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Send message" }),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByText("Refreshing the page clears this conversation."),
    ).toBeVisible();
  });

  it("clears proposal state on an account change before the next request", async () => {
    const proposal = {
      id: "p1",
      type: "card_proposal" as const,
      payload: {
        proposal_id: "30000000-0000-4000-8000-000000000098",
        deck: {
          id: "10000000-0000-4000-8000-000000000098",
          title: "Travel English",
          target_language: "en" as const,
        },
        drafts: [
          { term: "wander", meaning: "walk", synonyms: [], antonyms: [] },
        ],
        warnings: [],
      },
    };
    api.streamAssistantReply.mockImplementation(
      async (_messages, ontext, _signal, options) => {
        ontext("Review your draft.");
        options.onPart(proposal);
        return { stop: "completed", tools: [] };
      },
    );
    render(AssistantPage);
    const input = await screen.findByLabelText("Ask the assistant");
    await fireEvent.input(input, { target: { value: "propose" } });
    await fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByRole("button", { name: "Dismiss" });
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Send message" }),
      ).toBeInTheDocument(),
    );
    await fireEvent.input(input, { target: { value: "explain" } });
    await fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    expect(api.streamAssistantReply.mock.calls[1][0][1].parts).toEqual([
      {
        type: "proposal_state",
        proposal_id: proposal.payload.proposal_id,
        status: "pending",
        created_card_ids: [],
      },
    ]);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Send message" }),
      ).toBeInTheDocument(),
    );
    authSession.set({ kind: "authenticated", profile: { sub: "owner-b" } });
    await waitFor(() =>
      expect(screen.queryByText("Review your draft.")).not.toBeInTheDocument(),
    );
    await screen.findByLabelText("Ask the assistant");
    await fireEvent.input(input, { target: { value: "new account" } });
    await fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    expect(api.streamAssistantReply.mock.calls[2][0]).toEqual([
      { role: "user", content: "new account" },
    ]);
  });
});
