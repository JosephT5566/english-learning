import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";
import {
  createPendingAssistantProposal,
  savePendingAssistantProposal,
  PENDING_ASSISTANT_STORAGE_KEY,
} from "$lib/assistant/pending";
import { authSession } from "$lib/stores/auth";
import AssistantPage from "../../src/routes/assistant/+page.svelte";

const api = vi.hoisted(() => ({
  createCard: vi.fn(),
  getGenAIConsent: vi.fn(),
  grantGenAIConsent: vi.fn(),
  withdrawGenAIConsent: vi.fn(),
  streamAssistantReply: vi.fn(),
}));
vi.mock("$env/dynamic/public", () => ({ env: {} }));
vi.mock("$lib/auth", () => ({
  getProfile: () => {
    const session = get(authSession);
    return session.kind === "authenticated" ? session.profile : null;
  },
}));
vi.mock("$lib/api/client", async (original) => ({
  ...(await original<typeof import("$lib/api/client")>()),
  ...api,
}));

const granted = { genai_consent_at: "2026-11-12T00:00:00Z" };
describe("assistant page composer and consent", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
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

  it("remounts restored commands when switching directly between two owners", async () => {
    const a = pendingCommand("owner-a", "A private term", "A private meaning");
    const b = pendingCommand("owner-b", "B private term", "B private meaning");
    // Both commands use the legacy shared slot, as if another tab wrote B's command.
    localStorage.setItem(PENDING_ASSISTANT_STORAGE_KEY, JSON.stringify(a));
    render(AssistantPage);
    await screen.findByText("A private term");
    expect(screen.getByText("A private meaning")).toBeVisible();
    localStorage.setItem(PENDING_ASSISTANT_STORAGE_KEY, JSON.stringify(b));
    authSession.set({ kind: "authenticated", profile: { sub: "owner-b" } });
    await screen.findByRole("region", { name: "Card drafts for owner-b deck" });
    expect(screen.getByText("B private term")).toBeVisible();
    expect(screen.getByText("B private meaning")).toBeVisible();
    expect(screen.queryByText("A private term")).not.toBeInTheDocument();
    expect(screen.queryByText("A private meaning")).not.toBeInTheDocument();
    api.createCard.mockResolvedValue({ id: createdId, term: "B private term" });
    await fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(api.createCard).toHaveBeenCalledTimes(1));
    expect(api.createCard).toHaveBeenCalledWith(
      { ...b.drafts[0], deck_id: b.deck.id },
      b.idempotencyKeys[0],
    );
    await screen.findByRole("link", { name: "B private term" });
    expect(localStorage.getItem(PENDING_ASSISTANT_STORAGE_KEY)).toBeNull();
  });

  it("restores every unresolved command for the current owner", async () => {
    savePendingAssistantProposal(
      pendingCommand("owner-a", "first private", "first meaning"),
    );
    savePendingAssistantProposal({
      ...pendingCommand("owner-a", "second private", "second meaning"),
      proposal_id: createdId,
    });
    render(AssistantPage);
    await screen.findByText("first private");
    expect(screen.getByText("second private")).toBeVisible();
    expect(screen.getAllByRole("button", { name: "Retry" })).toHaveLength(2);
  });

  it.each(["committed", "pending", "dismissed"] as const)(
    "preserves %s proposal state after a stream fails before its first delta",
    async (status) => {
      const command = pendingCommand(
        "owner-a",
        "stream draft",
        "stream meaning",
      );
      let rejectStream: (error: Error) => void = () => {};
      api.streamAssistantReply.mockImplementationOnce(
        (_messages, _ontext, _signal, options) => {
          options.onPart({
            id: "proposal-part",
            type: "card_proposal",
            payload: { ...command, warnings: [] },
          });
          return new Promise((_resolve, reject) => {
            rejectStream = reject;
          });
        },
      );
      api.createCard.mockResolvedValue({ id: createdId, term: "created term" });
      render(AssistantPage);
      const input = await screen.findByLabelText("Ask the assistant");
      await fireEvent.input(input, {
        target: { value: "propose before failure" },
      });
      await fireEvent.click(
        screen.getByRole("button", { name: "Send message" }),
      );
      await screen.findByText("stream draft");
      if (status === "committed") {
        await fireEvent.click(
          screen.getByRole("button", { name: "Add to owner-a deck · 1 card" }),
        );
        await screen.findByRole("link", { name: "created term" });
      } else if (status === "dismissed") {
        await fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
      }
      expect(screen.getByRole("button", { name: "Replying…" })).toBeDisabled();
      rejectStream(new Error("stream broke"));
      await screen.findByRole("button", { name: "Send message" });
      expect(screen.getByText("propose before failure")).toBeVisible();
      expect(input).toHaveValue("");
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Could not get a reply.",
      );
      if (status === "committed")
        expect(
          screen.getByRole("link", { name: "created term" }),
        ).toBeVisible();
      if (status === "pending")
        expect(screen.getByText("stream draft")).toBeVisible();
      if (status === "dismissed")
        expect(screen.getByText("Skipped. No cards were added.")).toBeVisible();
      await fireEvent.input(input, { target: { value: "what happened" } });
      await fireEvent.click(
        screen.getByRole("button", { name: "Send message" }),
      );
      const messages = api.streamAssistantReply.mock.calls[1][0];
      expect(messages[0]).toEqual({
        role: "user",
        content: "propose before failure",
      });
      expect(messages[1].content.trim().length).toBeGreaterThan(0);
      expect(messages[1].parts).toEqual([
        {
          type: "proposal_state",
          proposal_id: command.proposal_id,
          status,
          created_card_ids: status === "committed" ? [createdId] : [],
        },
      ]);
    },
  );

  it("retains an unrendered clarification after interruption and echoes it on the next turn", async () => {
    const question = {
      question_id: "30000000-0000-0000-0000-000000000101",
      question: "Which meaning?",
      options: [
        { id: "40000000-0000-0000-0000-000000000101", label: "River bank" },
      ],
      allow_free_text: true,
      purpose: "term" as const,
    };
    api.streamAssistantReply.mockImplementationOnce(
      async (_messages, _ontext, _signal, options) => {
        options.onPart({
          id: "question-part",
          type: "clarification_question",
          payload: question,
        });
        throw new Error("stream broke");
      },
    );
    const view = render(AssistantPage);
    const input = await screen.findByLabelText("Ask the assistant");
    expect(document.documentElement).toHaveClass("assistant-route");
    expect(document.body).toHaveClass("assistant-route");
    await fireEvent.input(input, { target: { value: "Add bank" } });
    await fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByRole("alert");
    expect(screen.queryByText(question.question)).not.toBeInTheDocument();
    expect(screen.queryByText("River bank")).not.toBeInTheDocument();
    expect(screen.getByText("Add bank")).toBeVisible();
    await fireEvent.input(input, { target: { value: "River" } });
    await fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    expect(api.streamAssistantReply.mock.calls[1][0][1]).toEqual({
      role: "assistant",
      content: "The reply was interrupted.",
      parts: [{ type: "clarification_question", ...question }],
    });
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Send message" }),
      ).toBeInTheDocument(),
    );
    authSession.set({ kind: "authenticated", profile: { sub: "owner-b" } });
    await waitFor(() =>
      expect(screen.queryByText("Add bank")).not.toBeInTheDocument(),
    );
    await fireEvent.input(input, { target: { value: "Other owner" } });
    await fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    expect(api.streamAssistantReply.mock.calls[2][0]).toEqual([
      { role: "user", content: "Other owner" },
    ]);
    view.unmount();
    expect(document.documentElement).not.toHaveClass("assistant-route");
    expect(document.body).not.toHaveClass("assistant-route");
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

const createdId = "20000000-0000-4000-8000-000000000001";
function pendingCommand(ownerSubject: string, term: string, meaning: string) {
  return createPendingAssistantProposal({
    ownerSubject,
    proposal_id: "30000000-0000-4000-8000-000000000098",
    deck: {
      id: "10000000-0000-4000-8000-000000000098",
      title: `${ownerSubject} deck`,
      target_language: "en",
    },
    drafts: [{ term, meaning, synonyms: [], antonyms: [] }],
    idempotencyKeys: [createdId],
  });
}
