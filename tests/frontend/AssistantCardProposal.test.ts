import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/svelte";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CardDetail } from "$lib/api/contracts";
import {
  ApiClientError,
  type AssistantPart,
  createCards,
} from "$lib/api/client";
import AssistantCardProposal from "$lib/components/AssistantCardProposal.svelte";
import {
  createPendingAssistantProposal,
  savePendingAssistantProposal,
  loadPendingAssistantProposal,
} from "$lib/assistant/pending";

const api = vi.hoisted(() => ({
  createCard: vi.fn(),
  createCards: vi.fn<typeof createCards>(),
}));
vi.mock("$env/dynamic/public", () => ({ env: {} }));
vi.mock("$lib/auth", () => ({ getProfile: () => ({ sub: "owner-a" }) }));
vi.mock("$lib/api/client", async (original) => ({
  ...(await original<typeof import("$lib/api/client")>()),
  ...api,
}));
const id = "10000000-0000-4000-8000-000000000001";
const createdId = "20000000-0000-4000-8000-000000000001";
type Payload = Extract<AssistantPart, { type: "card_proposal" }>["payload"];
function proposal(): Payload {
  return {
    proposal_id: id,
    deck: { id, title: "Travel English", target_language: "en" },
    drafts: ["wander", "itinerary", "souvenir"].map((term) => ({
      term,
      meaning: `${term} meaning`,
      synonyms: [],
      antonyms: [],
    })),
    warnings: [
      {
        code: "duplicate_term",
        term: "itinerary",
        draft_index: 1,
        existing_card_ids: [createdId],
      },
    ],
  };
}
const card = (term = "wander", id = createdId): CardDetail => ({
  id,
  term,
  meaning: "meaning",
  deck: {
    id,
    title: "Travel English",
    target_language: "en",
    explanation_language: "zh-TW",
    archived_at: null,
  },
  synonyms: [],
  antonyms: [],
  reading: null,
  pronunciation: null,
  romanization: null,
  part_of_speech: null,
  part_of_speech_detail: null,
  target_language_definition: null,
  example_sentence: null,
  example_translation: null,
  example_source: null,
  note: null,
  supplementary_note: null,
  learned_on: null,
  archived_at: null,
  version: 1,
  updated_at: "2026-11-12T00:00:00Z",
  created_at: "2026-11-12T00:00:00Z",
  tags: [],
  review_state: null,
});
beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  api.createCard.mockResolvedValue(card());
  api.createCards.mockImplementation(async (_deck, body) =>
    body.cards.map((entry, i) =>
      card(entry.fields.term, `20000000-0000-4000-8000-00000000000${i + 1}`),
    ),
  );
});

describe("assistant card proposal", () => {
  it("renders selected compact drafts and stable duplicate warnings without writes or storage", async () => {
    render(AssistantCardProposal, { proposal: proposal() });
    expect(screen.getAllByRole("checkbox")).toHaveLength(3);
    for (const checkbox of screen.getAllByRole("checkbox"))
      expect(checkbox).toBeChecked();
    expect(screen.getByText("duplicate term")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await fireEvent.click(
      screen.getByRole("button", { name: "Remove wander" }),
    );
    const row = screen
      .getByText("itinerary", { selector: "strong" })
      .closest("li")!;
    expect(within(row).getByText("duplicate term")).toBeInTheDocument();
    await fireEvent.click(
      screen.getByRole("button", { name: "Undo remove wander" }),
    );
    expect(screen.getAllByRole("checkbox")).toHaveLength(3);
    expect(api.createCard).not.toHaveBeenCalled();
    expect(api.createCards).not.toHaveBeenCalled();
    expect(localStorage.length).toBe(0);
  });
  it("deselects and applies local CardForm edits before one bulk confirm", async () => {
    const onstate = vi.fn();
    render(AssistantCardProposal, { proposal: proposal(), onstate });
    await fireEvent.click(
      screen.getByRole("checkbox", { name: "Select souvenir" }),
    );
    await fireEvent.click(screen.getByRole("button", { name: "Edit wander" }));
    await fireEvent.input(screen.getByLabelText("Term"), {
      target: { value: "roam" },
    });
    await fireEvent.input(screen.getByLabelText("Meaning"), {
      target: { value: "walk freely" },
    });
    await fireEvent.click(
      screen.getByRole("button", { name: "Apply draft edits" }),
    );
    expect(api.createCards).not.toHaveBeenCalled();
    await fireEvent.click(
      screen.getByRole("button", { name: "Add to Travel English · 2 cards" }),
    );
    await waitFor(() => expect(api.createCards).toHaveBeenCalledTimes(1));
    const [deck, body] = api.createCards.mock.calls[0];
    expect(deck).toBe(id);
    expect(body.cards.map((entry) => entry.fields.term)).toEqual([
      "roam",
      "itinerary",
    ]);
    expect(new Set(body.cards.map((entry) => entry.idempotency_key)).size).toBe(
      2,
    );
    expect(body.cards[0].fields.meaning).toBe("walk freely");
    expect(api.createCard).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(onstate).toHaveBeenCalledWith({
        proposal_id: id,
        status: "committed",
        created_card_ids: [createdId, "20000000-0000-4000-8000-000000000002"],
      }),
    );
    expect(screen.getByRole("link", { name: "roam" })).toHaveAttribute(
      "href",
      `/cards/${createdId}`,
    );
    expect(
      screen.queryByRole("button", { name: /^Add to/ }),
    ).not.toBeInTheDocument();
    expect(localStorage.length).toBe(0);
  });
  it("locks unknown results and retries the identical single-card payload and key", async () => {
    const p = proposal();
    p.drafts = p.drafts.slice(0, 1);
    p.warnings = [];
    api.createCard.mockRejectedValueOnce(
      new ApiClientError("network", "network", true),
    );
    render(AssistantCardProposal, { proposal: p });
    await fireEvent.click(
      screen.getByRole("button", { name: "Add to Travel English · 1 card" }),
    );
    expect(await screen.findByText("Result not confirmed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit wander" })).toBeDisabled();
    expect(screen.getByRole("checkbox")).toBeDisabled();
    const command = loadPendingAssistantProposal("owner-a");
    expect(command).not.toBeNull();
    expect(command!.idempotencyKeys).toHaveLength(1);
    await fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(api.createCard).toHaveBeenCalledTimes(2));
    expect(api.createCard.mock.calls[1]).toEqual(api.createCard.mock.calls[0]);
    expect(api.createCard.mock.calls[0][0].deck_id).toBe(id);
    expect(api.createCards).not.toHaveBeenCalled();
  });
  it("keeps archived drafts and retries the same bulk command", async () => {
    api.createCards.mockRejectedValueOnce(
      new ApiClientError("archived", "api", false, 409, "deck_archived"),
    );
    render(AssistantCardProposal, { proposal: proposal() });
    await fireEvent.click(
      screen.getByRole("button", { name: "Add to Travel English · 3 cards" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This deck is archived. Cards cannot be added. Your drafts are still here.",
    );
    expect(
      screen.getByRole("link", { name: "Open deck management" }),
    ).toHaveAttribute("href", "/decks?language=en&status=archived");
    await fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(api.createCards).toHaveBeenCalledTimes(2));
    expect(api.createCards.mock.calls[1]).toEqual(
      api.createCards.mock.calls[0],
    );
  });
  it("locates a validation error then allows deselection with the remaining original key", async () => {
    const p = proposal();
    p.drafts = p.drafts.slice(0, 2);
    api.createCards.mockRejectedValueOnce(
      new ApiClientError(
        "validation",
        "api",
        false,
        422,
        "validation_failed",
        undefined,
        {
          fields: [
            {
              path: ["body", "cards", 0, "fields", "meaning"],
              message: "Check meaning.",
            },
          ],
        },
      ),
    );
    render(AssistantCardProposal, { proposal: p });
    await fireEvent.click(
      screen.getByRole("button", { name: "Add to Travel English · 2 cards" }),
    );
    expect(await screen.findByLabelText("Meaning")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    await fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await fireEvent.click(
      screen.getByRole("checkbox", { name: "Select wander" }),
    );
    await fireEvent.click(
      screen.getByRole("button", { name: /Add to Travel English/ }),
    );
    await waitFor(() => expect(api.createCard).toHaveBeenCalledTimes(1));
    expect(api.createCard.mock.calls[0][1]).toBe(
      api.createCards.mock.calls[0][1].cards[1].idempotency_key,
    );
  });
  it("dismisses without writes and reports only a dismissed state", async () => {
    const onstate = vi.fn();
    render(AssistantCardProposal, { proposal: proposal(), onstate });
    await fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(
      await screen.findByRole("heading", {
        name: "Skipped. No cards were added.",
      }),
    ).toHaveFocus();
    expect(onstate).toHaveBeenCalledWith({
      proposal_id: id,
      status: "dismissed",
      created_card_ids: [],
    });
    expect(api.createCard).not.toHaveBeenCalled();
    expect(api.createCards).not.toHaveBeenCalled();
  });
  it("disables confirm with zero selection and discards cancelled edits", async () => {
    const p = proposal();
    p.drafts = p.drafts.slice(0, 1);
    p.warnings = [];
    render(AssistantCardProposal, { proposal: p });
    await fireEvent.click(screen.getByRole("button", { name: "Edit wander" }));
    await fireEvent.input(screen.getByLabelText("Term"), {
      target: { value: "unsaved" },
    });
    await fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Edit wander" })).toHaveFocus();
    expect(screen.queryByText("unsaved")).not.toBeInTheDocument();
    await fireEvent.click(screen.getByRole("checkbox"));
    expect(
      screen.getByRole("button", { name: "Add to Travel English · 0 cards" }),
    ).toBeDisabled();
  });
});

describe("assistant recovery boundaries", () => {
  it("blocks Confirm when storage reservation fails and never claims a safe save", async () => {
    const store = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        throw new Error("quota");
      });
    try {
      const p = proposal();
      p.drafts = p.drafts.slice(0, 1);
      p.warnings = [];
      render(AssistantCardProposal, { proposal: p });
      expect(api.createCard).not.toHaveBeenCalled();
      await fireEvent.click(
        screen.getByRole("button", { name: "Add to Travel English · 1 card" }),
      );
      expect(
        await screen.findByText(
          "Could not safely save this request. No cards were sent. Please retry.",
        ),
      ).toBeInTheDocument();
      expect(api.createCard).not.toHaveBeenCalled();
    } finally {
      store.mockRestore();
    }
  });
  it("preserves an uncertain visible proposal after another visible proposal succeeds", async () => {
    const a = {
      ...proposal(),
      drafts: proposal().drafts.slice(0, 1),
      warnings: [],
    };
    const b = {
      ...a,
      proposal_id: createdId,
      deck: { ...a.deck, title: "Second deck" },
    };
    api.createCard.mockRejectedValueOnce(
      new ApiClientError("network", "network", true),
    );
    render(AssistantCardProposal, { proposal: a });
    render(AssistantCardProposal, { proposal: b });
    await fireEvent.click(
      screen.getByRole("button", { name: "Add to Travel English · 1 card" }),
    );
    await screen.findByText("Result not confirmed");
    const saved = loadPendingAssistantProposal("owner-a");
    expect(saved).not.toBeNull();
    await fireEvent.click(
      screen.getByRole("button", { name: "Add to Second deck · 1 card" }),
    );
    await screen.findByRole("link", { name: "wander" });
    expect(api.createCard).toHaveBeenCalledTimes(2);
    expect(loadPendingAssistantProposal("owner-a")).toEqual(saved);
    await fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(api.createCard).toHaveBeenCalledTimes(3));
    expect(api.createCard.mock.calls[2]).toEqual(api.createCard.mock.calls[0]);
  });
  it.each(["owner-a", "owner-b"])(
    "blocks a competing POST on reservation failure without erasing %s's command",
    async (ownerSubject) => {
      const p = {
        ...proposal(),
        drafts: proposal().drafts.slice(0, 1),
        warnings: [],
      };
      const saved = createPendingAssistantProposal({
        ownerSubject,
        proposal_id: createdId,
        deck: p.deck,
        drafts: p.drafts,
        idempotencyKeys: [createdId],
      });
      savePendingAssistantProposal(saved);
      const store = vi
        .spyOn(Storage.prototype, "setItem")
        .mockImplementation(() => {
          throw new Error("quota");
        });
      try {
        render(AssistantCardProposal, { proposal: p });
        await fireEvent.click(
          screen.getByRole("button", {
            name: "Add to Travel English · 1 card",
          }),
        );
        await screen.findByRole("alert");
        expect(api.createCard).not.toHaveBeenCalled();
        expect(api.createCards).not.toHaveBeenCalled();
        expect(loadPendingAssistantProposal(ownerSubject)).toEqual(saved);
      } finally {
        store.mockRestore();
      }
    },
  );
  it("shows the server idempotency conflict message without replacing the keys", async () => {
    api.createCards.mockRejectedValueOnce(
      new ApiClientError(
        "This key was already used for different content.",
        "api",
        false,
        409,
        "idempotency_key_reused",
      ),
    );
    render(AssistantCardProposal, { proposal: proposal() });
    await fireEvent.click(
      screen.getByRole("button", { name: "Add to Travel English · 3 cards" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This key was already used for different content.",
    );
    await fireEvent.click(
      screen.getByRole("button", { name: "Add to Travel English · 3 cards" }),
    );
    await waitFor(() => expect(api.createCards).toHaveBeenCalledTimes(2));
    expect(api.createCards.mock.calls[1]).toEqual(
      api.createCards.mock.calls[0],
    );
  });
  it("keeps an unlocatable 422 in an alert without opening an unrelated draft", async () => {
    api.createCards.mockRejectedValueOnce(
      new ApiClientError(
        "Check the batch.",
        "api",
        false,
        422,
        "validation_failed",
        undefined,
        { fields: [{ path: ["body", "cards"], message: "Check the batch." }] },
      ),
    );
    render(AssistantCardProposal, { proposal: proposal() });
    await fireEvent.click(
      screen.getByRole("button", { name: "Add to Travel English · 3 cards" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Check the batch.",
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
