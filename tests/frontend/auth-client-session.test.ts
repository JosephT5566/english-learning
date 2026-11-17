import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";

vi.mock("$app/environment", () => ({ browser: true }));
vi.mock("$env/static/public", () => ({
  PUBLIC_GOOGLE_AUTH_CLIENT_ID: "test-client",
  PUBLIC_EMAIL_WHITE_LIST: "learner@example.test",
}));
vi.mock("$env/dynamic/public", () => ({
  env: { PUBLIC_API_BASE_URL: "https://api.example.test" },
}));
let auth: typeof import("$lib/auth");
let stores: typeof import("$lib/stores/auth");
let client: typeof import("$lib/api/client");
const tokenResponse = (id: number) => ({
  access_token: `ela_${id}`,
  refresh_token: `elr_${id}`,
  access_expires_at: new Date(Date.now() + 900_000).toISOString(),
  refresh_expires_at: new Date(Date.now() + 604800_000).toISOString(),
  user: { id, email: `learner${id}@example.test` },
  profile: { name: null, picture: null },
});
async function login(id: number) {
  localStorage.setItem("el_auth_refresh_v1", `elr_seed_${id}`);
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response(JSON.stringify(tokenResponse(id)))),
  );
  await auth.refreshSession();
}
beforeEach(async () => {
  vi.resetModules();
  localStorage.clear();
  sessionStorage.clear();
  stores = await import("$lib/stores/auth");
  auth = await import("$lib/auth");
  client = await import("$lib/api/client");
});
afterEach(() => vi.unstubAllGlobals());

describe("401 belongs to its requesting app session", () => {
  it.each(["new-account", "signed-out", "explicit-guest", "same-account"])(
    "a delayed 401 is isolated after transition to %s",
    async (transition) => {
      await login(7);
      let finish!: (response: Response) => void;
      vi.stubGlobal(
        "fetch",
        vi.fn((url) =>
          String(url).endsWith("/auth/logout")
            ? Promise.resolve(new Response(null, { status: 204 }))
            : new Promise<Response>((resolve) => {
                finish = resolve;
              }),
        ),
      );
      const request = client.getDecks("en");
      await vi.waitFor(() => expect(finish).toBeTypeOf("function"));
      if (transition === "new-account") await login(8);
      if (transition === "signed-out" || transition === "explicit-guest")
        await auth.signOut();
      if (transition === "explicit-guest")
        expect(auth.enterGuestSession()).toEqual({ ok: true });
      const before = get(stores.authSession);
      const tokenBefore = localStorage.getItem("el_auth_refresh_v1");
      finish(new Response("{}", { status: 401 }));
      await expect(request).rejects.toMatchObject({
        kind: "authentication",
        status: 401,
      });
      if (transition === "same-account") {
        expect(get(stores.authSession).kind).toBe("expired");
        expect(localStorage.getItem("el_auth_refresh_v1")).toBeNull();
      } else {
        expect(get(stores.authSession)).toEqual(before);
        expect(localStorage.getItem("el_auth_refresh_v1")).toBe(tokenBefore);
      }
    },
  );
});

it.each([
  "new-account",
  "signed-out",
  "explicit-guest",
  "same-owner-new-login",
])("a delayed expired 401 does not retry across %s", async (transition) => {
  await login(7);
  let finish!: (response: Response) => void;
  const fetch = vi.fn((url) =>
    String(url).endsWith("/auth/logout")
      ? Promise.resolve(new Response(null, { status: 204 }))
      : new Promise<Response>((resolve) => {
          finish = resolve;
        }),
  );
  vi.stubGlobal("fetch", fetch);
  const request = client.getDecks("en");
  const result = request.then(
    (value) => ({ value }),
    (error) => ({ error }),
  );
  await vi.waitFor(() => expect(finish).toBeTypeOf("function"));
  if (transition !== "new-account") await auth.signOut();
  if (transition === "new-account") await login(8);
  if (transition === "same-owner-new-login") await login(7);
  if (transition === "explicit-guest") auth.enterGuestSession();
  const before = get(stores.authSession);
  const stored = localStorage.getItem("el_auth_refresh_v1");
  finish(
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
    ),
  );
  expect(await result).toMatchObject({
    error: { status: 401, code: "access_token_expired" },
  });
  expect(
    fetch.mock.calls.filter(([url]) => String(url).includes("/v1/decks")),
  ).toHaveLength(1);
  expect(get(stores.authSession)).toEqual(before);
  expect(localStorage.getItem("el_auth_refresh_v1")).toBe(stored);
});
