import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";
import { authSession, isSignedIn } from "$lib/stores/auth";
import {
  enterGuestSession,
  getTokenIfValid,
  initializeSession,
  initGsiOnce,
  onSignInError,
  renderGoogleButton,
  signOut,
  watchSession,
} from "$lib/auth";

vi.mock("$app/environment", () => ({ browser: true }));
vi.mock("$env/static/public", () => ({
  PUBLIC_GOOGLE_AUTH_CLIENT_ID: "test-client",
  PUBLIC_EMAIL_WHITE_LIST: "learner@example.test",
}));

function storedLogin(exp = Math.floor(Date.now() / 1000) + 3600) {
  const token = `header.${btoa(JSON.stringify({ exp, sub: "learner", email: "learner@example.test" }))}.signature`;
  localStorage.setItem("gid_id_token", token);
  localStorage.setItem("gid_exp", String(exp));
  return token;
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  authSession.set({ kind: "initializing" });
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("explicit tab guest session", () => {
  it.each(["corrupted", "missing-subject", "empty-subject", "expired-payload"])(
    "recovers explicit guest entry from unusable %s stored identity",
    (kind) => {
      const exp = Math.floor(Date.now() / 1000) + 3600;
      const payload =
        kind === "expired-payload"
          ? { exp: 1, sub: "learner" }
          : { exp, ...(kind === "empty-subject" ? { sub: "  " } : {}) };
      const token =
        kind === "corrupted"
          ? "corrupted-token"
          : `e30.${btoa(JSON.stringify(payload))}.signature`;
      localStorage.setItem("gid_id_token", token);
      localStorage.setItem("gid_exp", String(exp));
      initializeSession();
      expect(get(authSession).kind).toBe("signed-out");
      expect(enterGuestSession()).toEqual({ ok: true });
      initializeSession();
      expect(get(authSession).kind).toBe("guest");
    },
  );

  it("decodes multilingual Google profile names as UTF-8", () => {
    const exp = Math.floor(Date.now() / 1000) + 3600;
    const bytes = new TextEncoder().encode(
      JSON.stringify({ exp, sub: "learner", name: "王小明" }),
    );
    const payload = btoa(
      Array.from(bytes, (byte) => String.fromCharCode(byte)).join(""),
    );
    localStorage.setItem("gid_id_token", `header.${payload}.signature`);
    localStorage.setItem("gid_exp", String(exp));
    initializeSession();
    expect(get(authSession)).toMatchObject({
      kind: "authenticated",
      profile: { name: "王小明" },
    });
  });

  it("requires a choice and retains that choice on reload hydration", () => {
    initializeSession();
    expect(get(authSession).kind).toBe("signed-out");
    expect(enterGuestSession()).toEqual({ ok: true });
    authSession.set({ kind: "initializing" });
    initializeSession();
    expect(get(authSession).kind).toBe("guest");
    expect(get(isSignedIn)).toBe(false);
  });
  it("expires exactly 30 minutes after selection without renewing on hydration", () => {
    vi.useFakeTimers();
    const started = Date.now();
    enterGuestSession();
    const deadline = String(started + 30 * 60_000);
    expect(sessionStorage.getItem("learning_guest_session")).toBe(deadline);
    vi.setSystemTime(started + 30 * 60_000 - 1);
    initializeSession();
    expect(get(authSession).kind).toBe("guest");
    expect(sessionStorage.getItem("learning_guest_session")).toBe(deadline);
    vi.setSystemTime(started + 30 * 60_000);
    initializeSession();
    expect(get(authSession).kind).toBe("signed-out");
    expect(sessionStorage.getItem("learning_guest_session")).toBeNull();
    expect(enterGuestSession()).toEqual({ ok: true });
    expect(get(authSession).kind).toBe("guest");
  });
  it.each(["1", "invalid", "NaN", "Infinity", "", "{}", "1.5", "-1"])(
    "clears legacy or invalid deadline %s without granting guest access",
    (value) => {
      sessionStorage.setItem("learning_guest_session", value);
      initializeSession();
      expect(get(authSession).kind).toBe("signed-out");
      expect(sessionStorage.getItem("learning_guest_session")).toBeNull();
    },
  );
  it("expires on focus after suspended timers and preserves private storage", () => {
    vi.useFakeTimers();
    enterGuestSession();
    const stop = watchSession();
    localStorage.setItem("pending_review_submission_v1", "exact-command");
    localStorage.setItem("isTestedToday", "daily-bytes");
    vi.setSystemTime(Date.now() + 30 * 60_000);
    window.dispatchEvent(new Event("focus"));
    expect(get(authSession).kind).toBe("signed-out");
    expect(localStorage.getItem("pending_review_submission_v1")).toBe(
      "exact-command",
    );
    expect(localStorage.getItem("isTestedToday")).toBe("daily-bytes");
    stop();
  });
  it("expires active guest through the session watcher", () => {
    vi.useFakeTimers();
    enterGuestSession();
    const stop = watchSession();
    vi.advanceTimersByTime(30 * 60_000);
    expect(get(authSession).kind).toBe("signed-out");
    stop();
  });
  it("keeps valid authentication when a guest deadline has elapsed", () => {
    sessionStorage.setItem("learning_guest_session", String(Date.now() - 1));
    storedLogin();
    initializeSession();
    expect(get(authSession).kind).toBe("authenticated");
    expect(sessionStorage.getItem("learning_guest_session")).toBeNull();
  });
  it("does not carry guest selection to a fresh session storage", () => {
    enterGuestSession();
    sessionStorage.clear();
    initializeSession();
    expect(get(authSession).kind).toBe("signed-out");
  });
  it("reports unavailable session storage without entering guest", () => {
    initializeSession();
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("disabled");
    });
    expect(enterGuestSession().ok).toBe(false);
    expect(get(authSession).kind).toBe("signed-out");
  });
  it("fails closed when session storage cannot be read or cleared", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("disabled");
    });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("disabled");
    });
    expect(() => initializeSession()).not.toThrow();
    expect(get(authSession).kind).toBe("signed-out");
  });
  it("hydrates private identity before guest and clears the guest preference", () => {
    enterGuestSession();
    storedLogin();
    initializeSession();
    expect(get(authSession)).toMatchObject({
      kind: "authenticated",
      profile: { sub: "learner" },
    });
    expect(sessionStorage.getItem("learning_guest_session")).toBeNull();
    expect(enterGuestSession().ok).toBe(false);
  });
  it("sign-out preserves exact pending work and requires a new guest choice", () => {
    storedLogin();
    initializeSession();
    localStorage.setItem("pending_review_submission_v1", "exact-command");
    signOut();
    initializeSession();
    expect(get(authSession).kind).toBe("signed-out");
    expect(localStorage.getItem("pending_review_submission_v1")).toBe(
      "exact-command",
    );
  });
  it("updates cross-tab auth and expires private identity without entering guest", () => {
    vi.useFakeTimers();
    const stop = watchSession();
    storedLogin();
    window.dispatchEvent(new StorageEvent("storage", { key: "gid_exp" }));
    expect(get(isSignedIn)).toBe(true);
    vi.advanceTimersByTime(3600_000);
    expect(get(authSession).kind).toBe("signed-out");
    expect(getTokenIfValid()).toBeNull();
    stop();
  });
  it("renders GIS for every new container and error subscriptions follow mounted controls", () => {
    const initialize = vi.fn();
    const renderButton = vi.fn();
    Object.defineProperty(window, "google", {
      configurable: true,
      value: { accounts: { id: { initialize, renderButton } } },
    });
    const stale = vi.fn();
    const current = vi.fn();
    const remove = onSignInError(stale);
    initGsiOnce();
    remove();
    const dispose = onSignInError(current);
    initGsiOnce();
    initialize.mock.calls[0][0].callback({});
    expect(stale).not.toHaveBeenCalled();
    expect(current).toHaveBeenCalledOnce();
    const first = document.createElement("div");
    renderGoogleButton(first);
    renderGoogleButton(first);
    const narrow = document.createElement("div");
    Object.defineProperty(narrow, "clientWidth", { value: 240 });
    renderGoogleButton(narrow);
    expect(renderButton.mock.calls[1][1].width).toBe(240);
    expect(initialize).toHaveBeenCalledOnce();
    expect(renderButton).toHaveBeenCalledTimes(2);
    dispose();
  });
});
