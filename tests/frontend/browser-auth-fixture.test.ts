import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { get } from "svelte/store";
import type { Page } from "@playwright/test";

vi.mock("$app/environment", () => ({ browser: true }));
vi.mock("$env/static/public", () => ({
  PUBLIC_GOOGLE_AUTH_CLIENT_ID: "test-client",
  PUBLIC_EMAIL_WHITE_LIST: "browser-test@example.com",
}));
vi.mock("$env/dynamic/public", () => ({
  env: { PUBLIC_API_BASE_URL: "http://127.0.0.1:8001" },
}));
vi.mock("@playwright/test", async () => ({
  expect: (await import("vitest")).expect,
}));

beforeEach(() => {
  vi.resetModules();
  localStorage.clear();
  sessionStorage.clear();
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("the browser account fixture adopts the new internal owner and clears only that owner's pending predecessor", async () => {
  const auth = await import("$lib/auth");
  const stores = await import("$lib/stores/auth");
  const pending = await import("$lib/review/pending");
  const { signInAs, fixtureUserId } = await import("../browser/auth-fixture");
  const firstId = fixtureUserId("success");
  const nextId = fixtureUserId("other-account");
  const tokenResponse = (id: number, suffix: string) => ({
    access_token: `ela_${suffix}`,
    access_expires_at: new Date(Date.now() + 900_000).toISOString(),
    refresh_token: `elr_${suffix}`,
    refresh_expires_at: new Date(Date.now() + 604_800_000).toISOString(),
    user: { id, email: "browser-test@example.com" },
    profile: { name: "Browser Test", picture: null },
  });
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify(tokenResponse(firstId, "first"))),
      ),
  );
  await auth.exchangeCredential("synthetic-google-credential");
  const command = pending.createPendingSubmission(firstId, {
    items: [
      {
        card_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        decision: "yes",
        expected_version: 1,
      },
    ],
  });
  pending.savePendingSubmission(command);
  const stop = auth.watchSession();
  const next = tokenResponse(nextId, "next");
  vi.mocked(fetch)
    .mockClear()
    .mockImplementation(async () => new Response(JSON.stringify(next)));
  // Run the actual fixture callback against jsdom; no browser or server is started.
  const page = {
    request: {
      post: async () => ({ status: () => 200, json: async () => next }),
    },
    evaluate: async (callback: (session: unknown) => void, session: unknown) =>
      callback(session),
  } as unknown as Page;
  try {
    await signInAs(page, "other-account");
    await vi.waitFor(() => expect(auth.getProfile()?.id).toBe(nextId));
    expect(JSON.parse(localStorage.getItem("el_auth_profile_v1")!)).toEqual({
      id: nextId,
      email: "browser-test@example.com",
      name: "Browser Test",
    });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(
      JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string),
    ).toEqual({ refresh_token: "elr_next" });
    expect(auth.getTokenIfValid()).toBe("ela_next");
    expect(localStorage.getItem(pending.PENDING_REVIEW_STORAGE_KEY)).toBeNull();
    expect(get(stores.authNotice)).toMatchObject({
      kind: "account-changed",
      count: 1,
    });
  } finally {
    stop();
  }
});
