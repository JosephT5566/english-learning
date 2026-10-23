import { afterEach, describe, expect, it, vi } from "vitest";
vi.mock("$app/paths", () => ({ base: "/english-learning" }));
import { getPublicReviewCards, sampleGuestCards } from "$lib/api/public-review";
import type { PublicReviewCard } from "$lib/api/contracts";

const publicCard = {
  id: "00000000-0000-4000-8000-000000000001",
  target_language: "en",
  term: "remember",
  meaning: "keep in memory",
  pronunciation: "/rɪˈmembər/",
  reading: null,
  romanization: null,
  part_of_speech: "verb",
  part_of_speech_detail: null,
  target_language_definition: "to keep information in your mind",
  example_sentence: "I remember the answer.",
  example_translation: null,
  synonyms: ["recall"],
  antonyms: ["forget"],
} satisfies PublicReviewCard;

const snapshot = (items: PublicReviewCard[]) => ({
  schema_version: 1,
  generated_at: "2026-10-23T00:00:00Z",
  items,
});
const fiftyCards: PublicReviewCard[] = Array.from(
  { length: 50 },
  (_, index) => ({
    ...publicCard,
    id: `00000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
  }),
);
afterEach(() => vi.unstubAllGlobals());

describe("static guest cards", () => {
  it("loads the base-aware asset without credentials and accepts 50 cards", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(snapshot(fiftyCards))));
    vi.stubGlobal("fetch", fetcher);
    await expect(getPublicReviewCards()).resolves.toEqual(snapshot(fiftyCards));
    expect(fetcher).toHaveBeenCalledWith(
      "/english-learning/guest/cards.json",
      expect.objectContaining({ credentials: "omit", redirect: "error" }),
    );
    expect(fetcher.mock.calls[0][1].headers).toBeUndefined();
  });
  it("samples at most ten unique cards without mutating the pool or fetching", () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    for (let round = 0; round < 5; round++) {
      const cards = sampleGuestCards(fiftyCards);
      expect(cards).toHaveLength(10);
      expect(new Set(cards.map((card) => card.id)).size).toBe(10);
      expect(cards.every((card) => fiftyCards.includes(card))).toBe(true);
    }
    expect(fiftyCards).toHaveLength(50);
    expect(sampleGuestCards([])).toEqual([]);
    expect(sampleGuestCards([publicCard])).toEqual([publicCard]);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("rejects invalid data without disclosing the response body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("private-invalid-json")),
    );
    await expect(getPublicReviewCards()).rejects.toThrow("invalid");
  });
  it("cancels on session disposal without retrying", async () => {
    const controller = new AbortController();
    controller.abort();
    const fetcher = vi
      .fn()
      .mockRejectedValue(new DOMException("aborted", "AbortError"));
    vi.stubGlobal("fetch", fetcher);
    await expect(getPublicReviewCards(controller.signal)).rejects.toMatchObject(
      { name: "AbortError" },
    );
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
