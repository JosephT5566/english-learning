import { afterEach, describe, expect, it, vi } from "vitest";
vi.mock("$app/paths", () => ({ base: "/english-learning" }));
import { getPublicReviewCards, sampleGuestCards } from "$lib/api/public-review";
import { guestLastGoodKey } from "$lib/pwa/policy";
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

const mainKey = "/english-learning/guest/cards.json";
const lastGoodKey = guestLastGoodKey("/english-learning");
const unavailable =
  "The card snapshot was unavailable or invalid. Please try again.";

function guestCache() {
  const entries = new Map<string, Response>();
  const cache = {
    match: vi.fn(async (key: string) => entries.get(key)?.clone()),
    put: vi.fn(async (key: string, response: Response) => {
      entries.set(key, response.clone());
    }),
    delete: vi.fn(async (key: string) => entries.delete(key)),
  };
  const open = vi.fn().mockResolvedValue(cache);
  vi.stubGlobal("caches", { open });
  return { entries, cache, open };
}
function respond(value: unknown, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockImplementation(
        async () => new Response(JSON.stringify(value), { status }),
      ),
  );
}
const duplicateSnapshot = () => snapshot([publicCard, publicCard]);

describe("last good guest snapshot", () => {
  it("restores the previous good main copy after strict rejection", async () => {
    const { entries, cache, open } = guestCache();
    entries.set(
      lastGoodKey,
      new Response(JSON.stringify(snapshot([publicCard]))),
    );
    entries.set(mainKey, new Response(JSON.stringify(duplicateSnapshot())));
    respond(duplicateSnapshot());
    await expect(getPublicReviewCards()).rejects.toThrow(unavailable);
    expect(open).toHaveBeenCalledWith("english-learning-guest-v1");
    expect(await entries.get(mainKey)?.json()).toEqual(snapshot([publicCard]));
    expect(cache.delete).not.toHaveBeenCalled();
    expect(await entries.get(lastGoodKey)?.json()).toEqual(
      snapshot([publicCard]),
    );
  });
  it("saves validated responses and replaces last good with an empty withdrawal", async () => {
    const { entries } = guestCache();
    respond(snapshot([publicCard]));
    await expect(getPublicReviewCards()).resolves.toEqual(
      snapshot([publicCard]),
    );
    expect(await entries.get(lastGoodKey)?.clone().json()).toEqual(
      snapshot([publicCard]),
    );
    respond(snapshot([]));
    await expect(getPublicReviewCards()).resolves.toEqual(snapshot([]));
    expect(await entries.get(lastGoodKey)?.json()).toEqual(snapshot([]));
  });
  it("deletes a rejected 200 main copy when no last good exists", async () => {
    const { entries, cache } = guestCache();
    entries.set(mainKey, new Response(JSON.stringify(duplicateSnapshot())));
    respond(duplicateSnapshot());
    await expect(getPublicReviewCards()).rejects.toThrow(unavailable);
    expect(entries.has(mainKey)).toBe(false);
    expect(cache.delete).toHaveBeenCalledWith(mainKey);
  });
  it("leaves the main copy untouched on a rejected non-200 without last good", async () => {
    const { entries, cache } = guestCache();
    entries.set(mainKey, new Response(JSON.stringify(snapshot([publicCard]))));
    respond({ error: "unavailable" }, 503);
    await expect(getPublicReviewCards()).rejects.toThrow(unavailable);
    expect(await entries.get(mainKey)?.json()).toEqual(snapshot([publicCard]));
    expect(cache.put).not.toHaveBeenCalled();
    expect(cache.delete).not.toHaveBeenCalled();
  });
  for (const operation of ["open", "match", "put", "delete"] as const) {
    it(`ignores cache ${operation} failures on success and rejection`, async () => {
      const { cache, open, entries } = guestCache();
      (operation === "open" ? open : cache[operation]).mockRejectedValue(
        new Error("cache failure"),
      );
      if (operation === "put")
        entries.set(
          lastGoodKey,
          new Response(JSON.stringify(snapshot([publicCard]))),
        );
      respond(snapshot([]));
      await expect(getPublicReviewCards()).resolves.toEqual(snapshot([]));
      if (operation === "delete") entries.delete(lastGoodKey);
      respond(duplicateSnapshot());
      await expect(getPublicReviewCards()).rejects.toThrow(unavailable);
      expect(operation === "open" ? open : cache[operation]).toHaveBeenCalled();
      const controller = new AbortController();
      controller.abort();
      await expect(getPublicReviewCards(controller.signal)).rejects.toThrow(
        "Invalid snapshot",
      );
    });
  }
  it("works without Cache Storage on success and rejection", async () => {
    vi.stubGlobal("caches", undefined);
    respond(snapshot([]));
    await expect(getPublicReviewCards()).resolves.toEqual(snapshot([]));
    respond(duplicateSnapshot());
    await expect(getPublicReviewCards()).rejects.toThrow(unavailable);
  });
});
