import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { authSession } from "$lib/stores/auth";
import type { CardDetail, Deck } from "$lib/api/contracts";
import DeckList from "../../src/routes/decks/+page.svelte";
import DeckPage from "../../src/routes/decks/[deckId]/+page.svelte";
import CardPage from "../../src/routes/cards/[cardId]/+page.svelte";

const api = vi.hoisted(() => ({
  getDecks: vi.fn(),
  getDeck: vi.fn(),
  getCards: vi.fn(),
  getCard: vi.fn(),
  createDeck: vi.fn(),
  updateDeck: vi.fn(),
  archiveDeck: vi.fn(),
  createCard: vi.fn(),
  updateCard: vi.fn(),
  archiveCard: vi.fn(),
}));
const route = vi.hoisted(() => ({
  page: {
    url: new URL("http://localhost/decks?language=en"),
    params: { deckId: "deck", cardId: "card" },
  },
}));
vi.mock("$app/state", () => route);
vi.mock("$app/navigation", () => ({
  goto: vi.fn().mockResolvedValue(undefined),
}));
vi.mock("$env/dynamic/public", () => ({ env: {} }));
vi.mock("$lib/api/client", async (original) => ({
  ...(await original<typeof import("$lib/api/client")>()),
  ...api,
}));

const profile = { id: 1, email: "owner@example.test" };
const deck: Deck = {
  id: "deck",
  title: "My kept deck",
  target_language: "en",
  explanation_language: "zh-TW",
  archived_at: null,
  version: 1,
  created_at: "2026-11-17T00:00:00Z",
  updated_at: "2026-11-17T00:00:00Z",
};
const card: CardDetail = {
  id: "card",
  term: "Kept card",
  meaning: "Kept meaning",
  deck,
  reading: null,
  romanization: null,
  pronunciation: null,
  part_of_speech: null,
  part_of_speech_detail: null,
  archived_at: null,
  version: 1,
  target_language_definition: null,
  example_sentence: null,
  example_translation: null,
  example_source: null,
  synonyms: [],
  antonyms: [],
  note: null,
  supplementary_note: null,
  learned_on: null,
  created_at: deck.created_at,
  updated_at: deck.updated_at,
  tags: [],
  review_state: null,
};
beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  authSession.set({ kind: "authenticated", profile });
  api.getDecks.mockResolvedValue({ items: [deck], next_cursor: null });
  api.getDeck.mockResolvedValue(deck);
  api.getCards.mockResolvedValue({ items: [], next_cursor: null });
  api.getCard.mockResolvedValue(card);
});

describe("management expiry preserves work and blocks writes", () => {
  it("keeps the deck list and unsent creation fields while disabling save", async () => {
    render(DeckList);
    await screen.findByRole("heading", { name: deck.title });
    await fireEvent.click(screen.getByRole("button", { name: "New deck" }));
    const title = screen.getByLabelText("Deck title");
    await fireEvent.input(title, { target: { value: "Unsent deck title" } });
    authSession.set({ kind: "expired", profile });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Save deck" })).toBeDisabled(),
    );
    expect(title).toHaveValue("Unsent deck title");
    expect(screen.getByRole("heading", { name: deck.title })).toBeVisible();
    await fireEvent.submit(title.closest("form")!);
    expect(api.createDeck).not.toHaveBeenCalled();
    authSession.set({ kind: "authenticated", profile });
    await waitFor(() => expect(title).toBeEnabled());
    expect(title).toHaveValue("Unsent deck title");
    expect(api.getDecks).toHaveBeenCalledTimes(1);
  });

  it("keeps deck details and blocks new card, edit, archive and an open edit form", async () => {
    render(DeckPage);
    await screen.findByRole("heading", { name: deck.title });
    await fireEvent.click(screen.getByRole("button", { name: "Edit deck" }));
    const title = screen.getByLabelText("Deck title");
    await fireEvent.input(title, { target: { value: "Unsent edit" } });
    authSession.set({ kind: "expired", profile });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Save deck" })).toBeDisabled(),
    );
    expect(title).toHaveValue("Unsent edit");
    await fireEvent.submit(title.closest("form")!);
    expect(api.updateDeck).not.toHaveBeenCalled();
    authSession.set({ kind: "authenticated", profile });
    await waitFor(() => expect(title).toBeEnabled());
    expect(title).toHaveValue("Unsent edit");
    expect(api.getDeck).toHaveBeenCalledTimes(1);
    expect(api.getCards).toHaveBeenCalledTimes(1);
  });

  it("keeps card edits on expiry and ignores direct form submission", async () => {
    render(CardPage);
    await screen.findByRole("heading", { name: card.term });
    await fireEvent.click(screen.getByRole("button", { name: "Edit card" }));
    const term = screen.getByLabelText("Term", { exact: false });
    await fireEvent.input(term, { target: { value: "Unsent term" } });
    authSession.set({ kind: "expired", profile });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Save card" })).toBeDisabled(),
    );
    expect(term).toHaveValue("Unsent term");
    await fireEvent.submit(term.closest("form")!);
    expect(api.updateCard).not.toHaveBeenCalled();
    authSession.set({ kind: "authenticated", profile });
    await waitFor(() => expect(term).toBeEnabled());
    expect(term).toHaveValue("Unsent term");
    expect(api.getCard).toHaveBeenCalledTimes(1);
  });

  it("disables archive confirmation after expiry but keeps cancellation available", async () => {
    render(CardPage);
    await screen.findByRole("heading", { name: card.term });
    await fireEvent.click(screen.getByRole("button", { name: "Archive card" }));
    authSession.set({ kind: "expired", profile });
    await waitFor(() =>
      expect(
        screen
          .getAllByRole("button", { name: "Archive card" })
          .every((button) => button.hasAttribute("disabled")),
      ).toBe(true),
    );
    expect(screen.getByRole("button", { name: "Keep card" })).toBeEnabled();
    await fireEvent.click(screen.getByRole("button", { name: "Keep card" }));
    expect(api.archiveCard).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: card.term })).toBeVisible();
  });
});
