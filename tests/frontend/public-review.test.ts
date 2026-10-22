import { afterEach, describe, expect, it, vi } from "vitest";
vi.mock("$env/dynamic/public", () => ({
  env: { PUBLIC_API_BASE_URL: "https://public.test" },
}));
import { getPublicReviewCards } from "$lib/api/public-review";
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

const japaneseCard = {
  ...publicCard,
  id: "00000000-0000-4000-8000-000000000002",
  target_language: "ja",
  term: "覚える",
  meaning: "memorize",
  pronunciation: null,
  reading: "おぼえる",
  romanization: "oboeru",
  example_sentence: "単語を覚える。",
  example_translation: "Memorize a word.",
  target_language_definition: null,
  synonyms: [],
  antonyms: [],
} satisfies PublicReviewCard;

const tenCards = Array.from({ length: 10 }, (_, index) => ({
  ...(index % 2 === 0 ? publicCard : japaneseCard),
  id: `00000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
}));

afterEach(() => vi.unstubAllGlobals());

describe("public transport", () => {
  it("omits browser credentials and authorization", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('{"items":[]}'));
    vi.stubGlobal("fetch", fetcher);
    await expect(getPublicReviewCards()).resolves.toEqual({ items: [] });
    expect(fetcher).toHaveBeenCalledWith(
      "https://public.test/v1/public/review-cards",
      expect.objectContaining({
        method: "GET",
        credentials: "omit",
        cache: "no-store",
      }),
    );
    expect(fetcher.mock.calls[0][1].headers).toBeUndefined();
  });
  for (const status of [429, 503]) {
    for (const header of [
      null,
      "",
      "bad",
      "0",
      "-1",
      "999999999999999999999",
    ]) {
      it(`uses one second for unusable ${status} Retry-After ${header}`, async () => {
        vi.stubGlobal(
          "fetch",
          vi.fn().mockResolvedValue(
            new Response("{}", {
              status,
              headers: header === null ? {} : { "Retry-After": header },
            }),
          ),
        );
        await expect(getPublicReviewCards()).rejects.toMatchObject({
          status,
          retryAfterSeconds: 1,
        });
      });
    }
  }
  it("reads integer retry seconds and never retries itself", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(
        new Response("{}", { status: 429, headers: { "Retry-After": "10" } }),
      );
    vi.stubGlobal("fetch", fetcher);
    await expect(getPublicReviewCards()).rejects.toMatchObject({
      retryAfterSeconds: 10,
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("does not clear authentication on public 401", async () => {
    localStorage.setItem("gid_id_token", "keep");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("{}", { status: 401 })),
    );
    await expect(getPublicReviewCards()).rejects.toMatchObject({ status: 401 });
    expect(localStorage.getItem("gid_id_token")).toBe("keep");
  });
  it("rejects malformed cards", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response('{"items":[{"id":"a"}]}')),
    );
    await expect(getPublicReviewCards()).rejects.toThrow("invalid");
  });
  for (const [label, items] of [
    ["a single valid card", [publicCard]],
    ["ten distinct valid English and Japanese cards", tenCards],
  ] satisfies [string, PublicReviewCard[]][]) {
    it(`accepts ${label}`, async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(new Response(JSON.stringify({ items }))),
      );
      await expect(getPublicReviewCards()).resolves.toEqual({ items });
    });
  }
  it("rejects two valid cards with the same ID", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ items: [publicCard, publicCard] })),
        ),
    );
    await expect(getPublicReviewCards()).rejects.toThrow("invalid");
  });
  it("rejects eleven distinct valid cards", async () => {
    const items = [
      ...tenCards,
      { ...publicCard, id: "00000000-0000-4000-8000-000000000011" },
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ items }))),
    );
    await expect(getPublicReviewCards()).rejects.toThrow("invalid");
  });
  it("passes cancellation to fetch without retry", async () => {
    const controller = new AbortController();
    controller.abort();
    const fetcher = vi
      .fn()
      .mockRejectedValue(new DOMException("aborted", "AbortError"));
    vi.stubGlobal("fetch", fetcher);
    await expect(getPublicReviewCards(controller.signal)).rejects.toMatchObject(
      { name: "AbortError" },
    );
    expect(fetcher.mock.calls[0][1].signal).toBe(controller.signal);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
