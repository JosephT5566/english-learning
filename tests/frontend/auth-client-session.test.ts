import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";
import { getDecks } from "$lib/api/client";
import { enterGuestSession, initializeSession, signOut } from "$lib/auth";
import { authSession } from "$lib/stores/auth";

vi.mock("$app/environment", () => ({ browser: true }));
vi.mock("$env/static/public", () => ({
  PUBLIC_GOOGLE_AUTH_CLIENT_ID: "test-client",
  PUBLIC_EMAIL_WHITE_LIST: "learner@example.test",
}));
vi.mock("$env/dynamic/public", () => ({
  env: { PUBLIC_API_BASE_URL: "https://api.example.test" },
}));

function login(subject: string) {
  const exp = Math.floor(Date.now() / 1000) + 3600;
  const token = `e30.${btoa(JSON.stringify({ exp, sub: subject }))}.signature`;
  localStorage.setItem("gid_id_token", token);
  localStorage.setItem("gid_exp", String(exp));
  initializeSession();
  return token;
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  authSession.set({ kind: "initializing" });
});
afterEach(() => vi.unstubAllGlobals());

describe("401 belongs to its requesting session with real auth state", () => {
  it.each(["new-account", "signed-out", "explicit-guest", "same-account"])(
    "only invalidates the requesting session after transition to %s",
    async (transition) => {
      login("old-account");
      let finish: (response: Response) => void = () => {
        throw new Error("Request not started");
      };
      vi.stubGlobal(
        "fetch",
        vi.fn(
          () =>
            new Promise<Response>((resolve) => {
              finish = resolve;
            }),
        ),
      );
      const request = getDecks("en");
      if (transition === "new-account") login("new-account");
      if (transition === "signed-out" || transition === "explicit-guest")
        signOut();
      if (transition === "explicit-guest")
        expect(enterGuestSession()).toEqual({ ok: true });
      const before = get(authSession);
      const tokenBefore = localStorage.getItem("gid_id_token");
      finish(new Response("{}", { status: 401 }));
      await expect(request).rejects.toMatchObject({
        kind: "authentication",
        status: 401,
      });
      if (transition === "same-account") {
        expect(get(authSession).kind).toBe("signed-out");
        expect(localStorage.getItem("gid_id_token")).toBeNull();
      } else {
        expect(get(authSession)).toEqual(before);
        expect(localStorage.getItem("gid_id_token")).toBe(tokenBefore);
      }
      if (transition === "explicit-guest")
        expect(
          Number(sessionStorage.getItem("learning_guest_session")),
        ).toBeGreaterThan(Date.now());
    },
  );
});
