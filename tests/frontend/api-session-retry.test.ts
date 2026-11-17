import { authSession } from "$lib/stores/auth";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { createDeck, getDecks, streamAssistantReply } from "$lib/api/client";

const auth = vi.hoisted(() => ({
  getTokenIfValid: vi.fn(),
  ensureAccessToken: vi.fn(),
  refreshSession: vi.fn(),
  expireSession: vi.fn(),
  isCurrentToken: vi.fn(),
  getProfile: vi.fn(),
}));
vi.mock("$lib/auth", () => auth);
vi.mock("$env/dynamic/public", () => ({
  env: { PUBLIC_API_BASE_URL: "https://api.example.test" },
}));
const expired = () =>
  new Response(
    JSON.stringify({
      error: {
        code: "access_token_expired",
        message: "Expired",
        retryable: false,
        request_id: "test",
      },
    }),
    { status: 401 },
  );
const deck = {
  id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  title: "Deck",
  target_language: "en",
  explanation_language: "zh-TW",
  archived_at: null,
  version: 1,
  created_at: "2026-11-17T00:00:00Z",
  updated_at: "2026-11-17T00:00:00Z",
};
beforeEach(() => {
  vi.resetAllMocks();
  authSession.set({ kind: "initializing" });
  auth.getTokenIfValid.mockReturnValue("ela_old");
  auth.ensureAccessToken.mockResolvedValue("ela_old");
  auth.refreshSession.mockResolvedValue("ela_new");
  auth.isCurrentToken.mockReturnValue(true);
});
afterEach(() => vi.unstubAllGlobals());
it("refreshes once and retries a write once with the same Idempotency-Key and body", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(expired())
    .mockResolvedValueOnce(new Response(JSON.stringify(deck)));
  vi.stubGlobal("fetch", fetch);
  const payload = {
    title: "Deck",
    target_language: "en",
    explanation_language: "zh-TW",
  } as const;
  await expect(createDeck(payload, "fixed-key")).resolves.toEqual(deck);
  expect(auth.refreshSession).toHaveBeenCalledTimes(1);
  expect(fetch).toHaveBeenCalledTimes(2);
  const first = fetch.mock.calls[0][1];
  const second = fetch.mock.calls[1][1];
  expect(first.body).toBe(second.body);
  expect(first.headers["Idempotency-Key"]).toBe("fixed-key");
  expect(second.headers["Idempotency-Key"]).toBe("fixed-key");
  expect(second.headers.Authorization).toBe("Bearer ela_new");
});
it("does not loop when the retried access token is rejected", async () => {
  const fetch = vi.fn().mockImplementation(async () => expired());
  vi.stubGlobal("fetch", fetch);
  await expect(getDecks("en")).rejects.toMatchObject({
    kind: "authentication",
    status: 401,
  });
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(auth.refreshSession).toHaveBeenCalledTimes(1);
  expect(auth.expireSession).toHaveBeenCalledWith("ela_new");
});
it("known-expired preflight refresh consumes the single refresh budget", async () => {
  auth.getTokenIfValid.mockReturnValue(null);
  auth.ensureAccessToken.mockResolvedValue("ela_new");
  const fetch = vi.fn().mockImplementation(async () => expired());
  vi.stubGlobal("fetch", fetch);
  await expect(getDecks("en")).rejects.toMatchObject({ status: 401 });
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(auth.refreshSession).not.toHaveBeenCalled();
});
it("a delayed old-account 401 cannot expire or retry a new account", async () => {
  auth.isCurrentToken.mockReturnValue(false);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(expired()));
  await expect(getDecks("en")).rejects.toMatchObject({ status: 401 });
  expect(auth.expireSession).not.toHaveBeenCalled();
  expect(auth.refreshSession).not.toHaveBeenCalled();
});
it("SSE refreshes before starting and retries a pre-stream 401 only once", async () => {
  const done =
    'event: done\ndata: {"tool_calls":[],"stop_reason":"completed","usage":null}\n\n';
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response("{}", { status: 401 }))
    .mockResolvedValueOnce(
      new Response(done, { headers: { "Content-Type": "text/event-stream" } }),
    );
  vi.stubGlobal("fetch", fetch);
  await expect(
    streamAssistantReply(
      [{ role: "user", content: "Hello" }],
      () => {},
      new AbortController().signal,
    ),
  ).resolves.toEqual({ stop: "completed", tools: [] });
  expect(auth.ensureAccessToken).toHaveBeenCalledWith(30);
  expect(auth.refreshSession).toHaveBeenCalledTimes(1);
});

it("preserves the session and exact write when another-tab refresh remains superseded", async () => {
  authSession.set({
    kind: "authenticated",
    profile: { id: 1, email: "learner@example.test" },
  });
  auth.refreshSession.mockResolvedValue(null);
  const fetch = vi.fn().mockResolvedValue(expired());
  vi.stubGlobal("fetch", fetch);
  await expect(
    createDeck(
      { title: "Deck", target_language: "en", explanation_language: "zh-TW" },
      "fixed-key",
    ),
  ).rejects.toMatchObject({ code: "refresh_superseded", retryable: true });
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(auth.expireSession).not.toHaveBeenCalled();
});
