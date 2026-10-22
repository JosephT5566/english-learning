import { afterEach, describe, expect, it, vi } from "vitest";
vi.mock("$env/dynamic/public", () => ({
  env: { PUBLIC_API_BASE_URL: "https://public.test" },
}));
import { getPublicReviewCards } from "$lib/api/public-review";

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
  it("rejects malformed and duplicate batches", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response('{"items":[{"id":"a"}]}')),
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
