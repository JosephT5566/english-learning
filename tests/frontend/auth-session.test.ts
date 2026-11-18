import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";

vi.mock("$app/environment", () => ({ browser: true }));
const publicConfig = vi.hoisted(() => ({
  PUBLIC_GOOGLE_AUTH_CLIENT_ID: "test-client",
  PUBLIC_EMAIL_WHITE_LIST: "learner@example.test",
}));
vi.mock("$env/static/public", () => publicConfig);
vi.mock("$env/dynamic/public", () => ({
  env: { PUBLIC_API_BASE_URL: "https://api.example.test" },
}));

let auth: typeof import("$lib/auth");
let stores: typeof import("$lib/stores/auth");
let pending: typeof import("$lib/review/pending");
const profile = { id: 7, email: "learner@example.test", name: "王小明" };
const tokens = (suffix = "one", id = 7) => ({
  access_token: `ela_${suffix}`,
  access_expires_at: new Date(Date.now() + 900_000).toISOString(),
  refresh_token: `elr_${suffix}`,
  refresh_expires_at: new Date(Date.now() + 604800_000).toISOString(),
  user: { id, email: profile.email },
  profile: { name: profile.name, picture: null },
});
const response = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status });
function seed() {
  localStorage.setItem("el_auth_refresh_v1", "elr_seed");
  localStorage.setItem("el_auth_profile_v1", JSON.stringify(profile));
}
function googleSignIn() {
  let callback: (value: {
    credential: string;
  }) => Promise<void> = async () => {};
  Object.defineProperty(window, "google", {
    configurable: true,
    value: {
      accounts: {
        id: {
          initialize: vi.fn((options) => {
            callback = options.callback;
          }),
        },
      },
    },
  });
  auth.initGsiOnce();
  return (email: string) =>
    callback({
      credential: `e30.${btoa(JSON.stringify({ email }))}.synthetic`,
    });
}
const payload = {
  items: [
    {
      card_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      decision: "yes" as const,
      expected_version: 1,
    },
  ],
};

beforeEach(async () => {
  vi.resetModules();
  publicConfig.PUBLIC_EMAIL_WHITE_LIST = profile.email;
  localStorage.clear();
  sessionStorage.clear();
  stores = await import("$lib/stores/auth");
  pending = await import("$lib/review/pending");
  auth = await import("$lib/auth");
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(tokens())));
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("app-issued browser session", () => {
  it("browser allowlist rejection shows the email without exchange or changing an existing app session", async () => {
    seed();
    await auth.initializeSession();
    const command = pending.createPendingSubmission(7, payload);
    pending.savePendingSubmission(command);
    const raw = localStorage.getItem(pending.PENDING_REVIEW_STORAGE_KEY);
    vi.mocked(fetch).mockClear();
    const error = vi.fn();
    const stop = auth.onSignInError(error);
    await googleSignIn()("rejected@example.test");
    expect(fetch).not.toHaveBeenCalled();
    expect(get(stores.authNotice)).toEqual({
      kind: "error",
      email: "rejected@example.test",
    });
    expect(error).toHaveBeenCalledOnce();
    expect(auth.getTokenIfValid()).toBe("ela_one");
    expect(localStorage.getItem("el_auth_refresh_v1")).toBe("elr_one");
    expect(localStorage.getItem(pending.PENDING_REVIEW_STORAGE_KEY)).toBe(raw);
    expect(auth.enterGuestSession()).toEqual({ ok: true });
    expect(get(stores.authSession).kind).toBe("guest");
    expect(auth.getTokenIfValid()).toBeNull();
    expect(localStorage.getItem(pending.PENDING_REVIEW_STORAGE_KEY)).toBe(raw);
    expect(fetch).not.toHaveBeenCalled();
    stop();
  });
  it.each([
    ["learner@example.test", "learner@example.test"],
    ["learner@example.test", "LEARNER@EXAMPLE.TEST"],
    ["other@example.test,learner@example.test", "learner@example.test"],
  ])(
    "browser allowlist %j permits %j before authoritative exchange",
    async (allowlist, email) => {
      publicConfig.PUBLIC_EMAIL_WHITE_LIST = allowlist;
      await googleSignIn()(email);
      expect(fetch).toHaveBeenCalledOnce();
      expect(fetch).toHaveBeenCalledWith(
        "https://api.example.test/v1/auth/session",
        expect.anything(),
      );
      expect(auth.getTokenIfValid()).toBe("ela_one");
      expect(get(stores.authSession)).toEqual({
        kind: "authenticated",
        profile,
      });
    },
  );
  it.each([
    ["", "learner@example.test"],
    [",", "learner@example.test"],
    ["LEARNER@EXAMPLE.TEST", "learner@example.test"],
    [" learner@example.test ", "learner@example.test"],
    ["learner@example.test", " learner@example.test "],
  ])(
    "browser allowlist %j rejects %j without normalizing configuration or trimming emails",
    async (allowlist, email) => {
      publicConfig.PUBLIC_EMAIL_WHITE_LIST = allowlist;
      await auth.initializeSession();
      await googleSignIn()(email);
      expect(fetch).not.toHaveBeenCalled();
      expect(get(stores.authSession).kind).toBe("signed-out");
      expect(get(stores.authNotice)).toEqual({ kind: "error", email });
      expect(auth.getTokenIfValid()).toBeNull();
    },
  );
  it("server rejection remains authoritative after the browser allowlist permits sign-in", async () => {
    vi.mocked(fetch).mockResolvedValue(
      response({ error: { code: "account_not_allowed" } }, 403),
    );
    await googleSignIn()(profile.email);
    expect(fetch).toHaveBeenCalledOnce();
    expect(get(stores.authNotice)).toEqual({
      kind: "error",
      email: profile.email,
    });
    expect(auth.getTokenIfValid()).toBeNull();
    expect(localStorage.getItem("el_auth_refresh_v1")).toBeNull();
    expect(auth.enterGuestSession()).toEqual({ ok: true });
    expect(get(stores.authSession).kind).toBe("guest");
  });
  it("exchanges GIS credentials once and stores only refresh and display profile", async () => {
    let callback: (value: {
      credential: string;
    }) => Promise<void> = async () => {};
    const initialize = vi.fn((options) => {
      callback = options.callback;
    });
    Object.defineProperty(window, "google", {
      configurable: true,
      value: { accounts: { id: { initialize } } },
    });
    auth.initGsiOnce();
    const credential = `e30.${btoa(JSON.stringify({ email: profile.email }))}.synthetic`;
    await callback({ credential });
    expect(fetch).toHaveBeenCalledWith(
      "https://api.example.test/v1/auth/session",
      expect.objectContaining({ body: JSON.stringify({ credential }) }),
    );
    expect(localStorage.getItem("el_auth_refresh_v1")).toBe("elr_one");
    expect(JSON.parse(localStorage.getItem("el_auth_profile_v1")!)).toEqual(
      profile,
    );
    expect(
      [...Array(localStorage.length)]
        .map((_, index) => localStorage.getItem(localStorage.key(index)!))
        .join(),
    ).not.toContain("ela_one");
    expect(localStorage.getItem("gid_id_token")).toBeNull();
    expect(auth.getTokenIfValid()).toBe("ela_one");
  });
  it("removes legacy credentials and shows Session ended only on the first load", async () => {
    localStorage.setItem("gid_id_token", "legacy-secret");
    localStorage.setItem("gid_exp", "9999999999");
    await auth.initializeSession();
    expect(localStorage.getItem("gid_id_token")).toBeNull();
    expect(localStorage.getItem("gid_exp")).toBeNull();
    expect(get(stores.authNotice)).toEqual({ kind: "expired" });
    stores.authNotice.set(null);
    await auth.initializeSession();
    expect(get(stores.authNotice)).toBeNull();
  });
  it("restores a reload through refresh and preserves a cached profile when refresh profile is null", async () => {
    seed();
    vi.mocked(fetch).mockResolvedValue(
      response({ ...tokens(), profile: { name: null, picture: null } }),
    );
    await auth.initializeSession();
    expect(get(stores.authSession)).toEqual({ kind: "authenticated", profile });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(get(stores.authNotice)).toBeNull();
  });
  it("refresh is single-flight per tab", async () => {
    seed();
    let finish!: (value: Response) => void;
    vi.mocked(fetch).mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const first = auth.refreshSession();
    const second = auth.refreshSession();
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    finish(response(tokens()));
    expect(await first).toBe("ela_one");
    expect(await second).toBe("ela_one");
  });
  it("re-reads refresh storage after acquiring the cross-tab lock", async () => {
    seed();
    const request = vi.fn(async (_name, callback) => {
      localStorage.setItem("el_auth_refresh_v1", "elr_other-tab");
      return callback();
    });
    Object.defineProperty(navigator, "locks", {
      configurable: true,
      value: { request },
    });
    await auth.refreshSession();
    expect(request).toHaveBeenCalledOnce();
    expect(
      JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string),
    ).toEqual({ refresh_token: "elr_other-tab" });
    Object.defineProperty(navigator, "locks", {
      configurable: true,
      value: undefined,
    });
  });
  it("on 409 it re-reads storage and retries refresh exactly once", async () => {
    seed();
    vi.mocked(fetch)
      .mockImplementationOnce(async () => {
        localStorage.setItem("el_auth_refresh_v1", "elr_rotated");
        return response({ error: { code: "refresh_superseded" } }, 409);
      })
      .mockResolvedValue(response(tokens()));
    expect(await auth.refreshSession()).toBe("ela_one");
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(
      JSON.parse(vi.mocked(fetch).mock.calls[1][1]!.body as string)
        .refresh_token,
    ).toBe("elr_rotated");
  });
  it("refresh failure expires without clearing pending answers", async () => {
    seed();
    const command = pending.createPendingSubmission(7, payload);
    pending.savePendingSubmission(command);
    vi.mocked(fetch).mockResolvedValue(
      response({ error: { code: "refresh_invalid" } }, 401),
    );
    await auth.initializeSession();
    expect(get(stores.authSession).kind).toBe("expired");
    expect(localStorage.getItem(pending.PENDING_REVIEW_STORAGE_KEY)).toBe(
      JSON.stringify(command),
    );
    expect(get(stores.authNotice)).toEqual({ kind: "expired" });
  });
  it("guest keeps pending answers and profile, clears credentials, and never loads or writes answer storage", async () => {
    seed();
    await auth.initializeSession();
    const command = pending.createPendingSubmission(7, payload);
    pending.savePendingSubmission(command);
    const raw = localStorage.getItem(pending.PENDING_REVIEW_STORAGE_KEY);
    const cached = localStorage.getItem("el_auth_profile_v1");
    expect(auth.enterGuestSession()).toEqual({ ok: true });
    const read = vi.spyOn(Storage.prototype, "getItem");
    const write = vi.spyOn(Storage.prototype, "setItem");
    await auth.initializeSession();
    pending.loadPendingSubmission(7);
    pending.savePendingSubmission(command);
    expect(
      read.mock.calls.some(
        ([key]) => key === pending.PENDING_REVIEW_STORAGE_KEY,
      ),
    ).toBe(false);
    expect(
      write.mock.calls.some(
        ([key]) => key === pending.PENDING_REVIEW_STORAGE_KEY,
      ),
    ).toBe(false);
    read.mockRestore();
    write.mockRestore();
    expect(localStorage.getItem(pending.PENDING_REVIEW_STORAGE_KEY)).toBe(raw);
    expect(localStorage.getItem("el_auth_profile_v1")).toBe(cached);
    expect(localStorage.getItem("el_auth_refresh_v1")).toBeNull();
    expect(auth.getTokenIfValid()).toBeNull();
    expect(get(stores.authSession).kind).toBe("guest");
  });
  it("guest reload does not call owner APIs and never renews its 30-minute deadline", async () => {
    vi.useFakeTimers();
    const now = Date.now();
    expect(auth.enterGuestSession()).toEqual({ ok: true });
    const deadline = sessionStorage.getItem("learning_guest_session");
    await auth.initializeSession();
    await auth.initializeSession();
    expect(fetch).not.toHaveBeenCalled();
    expect(sessionStorage.getItem("learning_guest_session")).toBe(deadline);
    expect(Number(deadline)).toBe(now + 30 * 60_000);
  });
  it("continuing guest after failed sign-in preserves the original live guest deadline", async () => {
    vi.useFakeTimers();
    seed();
    auth.enterGuestSession();
    const deadline = sessionStorage.getItem("learning_guest_session");
    vi.advanceTimersByTime(5 * 60_000);
    vi.mocked(fetch).mockResolvedValue(
      response({ error: { code: "account_not_allowed" } }, 403),
    );
    await auth.exchangeCredential("synthetic-rejected-credential");
    expect(get(stores.authSession).kind).toBe("expired");
    expect(auth.enterGuestSession()).toEqual({ ok: true });
    expect(get(stores.authSession).kind).toBe("guest");
    expect(sessionStorage.getItem("learning_guest_session")).toBe(deadline);
    expect(auth.getGuestTimeRemaining()).toBe(25 * 60_000);
  });
  it("sign-out calls logout, clears profile and credentials, and keeps pending", async () => {
    seed();
    await auth.initializeSession();
    const command = pending.createPendingSubmission(7, payload);
    pending.savePendingSubmission(command);
    const disableAutoSelect = vi.fn();
    Object.defineProperty(window, "google", {
      configurable: true,
      value: { accounts: { id: { disableAutoSelect } } },
    });
    await auth.signOut();
    expect(fetch).toHaveBeenLastCalledWith(
      "https://api.example.test/v1/auth/logout",
      expect.objectContaining({ method: "POST" }),
    );
    expect(localStorage.getItem("el_auth_profile_v1")).toBeNull();
    expect(localStorage.getItem("el_auth_refresh_v1")).toBeNull();
    expect(localStorage.getItem(pending.PENDING_REVIEW_STORAGE_KEY)).toBe(
      JSON.stringify(command),
    );
    expect(disableAutoSelect).toHaveBeenCalledOnce();
  });
  it("other-tab sign-out preserves the page identity and pending work", async () => {
    seed();
    await auth.initializeSession();
    const command = pending.createPendingSubmission(7, payload);
    pending.savePendingSubmission(command);
    const raw = localStorage.getItem(pending.PENDING_REVIEW_STORAGE_KEY);
    const stop = auth.watchSession();
    vi.mocked(fetch).mockClear();
    localStorage.removeItem("el_auth_refresh_v1");
    window.dispatchEvent(
      new StorageEvent("storage", {
        key: "el_auth_refresh_v1",
        newValue: null,
      }),
    );
    expect(get(stores.authSession).kind).toBe("expired");
    expect(get(stores.authNotice)).toEqual({ kind: "other-tab" });
    expect(auth.getProfile()).toEqual(profile);
    expect(localStorage.getItem(pending.PENDING_REVIEW_STORAGE_KEY)).toBe(raw);
    expect(fetch).not.toHaveBeenCalled();
    expect(get(pending.pendingReviewReplay)).toBeNull();
    stop();
  });
  it("same-user sign-in sends the saved exact command and publishes its validated result", async () => {
    seed();
    const command = pending.createPendingSubmission(7, payload);
    pending.savePendingSubmission(command);
    const state = {
      review_stage: 1,
      ease_factor: "2.50",
      interval_days: 0,
      last_reviewed_at: null,
      next_review_at: "2026-11-17T00:00:00Z",
      version: 1,
    };
    const result = {
      batch_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
      reviewed_at: "2026-11-17T00:00:00Z",
      algorithm_version: "srs-v1",
      items: [
        {
          event_id: 1,
          card_id: payload.items[0].card_id,
          decision: "yes",
          quality: 5,
          previous_state: state,
          resulting_state: { ...state, version: 2 },
        },
      ],
    };
    vi.mocked(fetch).mockImplementation(async (url) => {
      if (String(url).endsWith("/auth/logout"))
        return new Response(null, { status: 204 });
      if (String(url).endsWith("/v1/reviews"))
        expect(get(pending.pendingReviewReplay)).toEqual({
          ownerId: 7,
          idempotencyKey: command.idempotencyKey,
        });
      return response(String(url).endsWith("/v1/reviews") ? result : tokens());
    });
    await auth.exchangeCredential("synthetic-google-credential");
    const call = vi
      .mocked(fetch)
      .mock.calls.find(([url]) => String(url).endsWith("/v1/reviews"));
    expect(call?.[1]?.body).toBe(JSON.stringify(command.payload));
    expect(call?.[1]?.headers).toMatchObject({
      "Idempotency-Key": command.idempotencyKey,
    });
    expect(localStorage.getItem(pending.PENDING_REVIEW_STORAGE_KEY)).toBeNull();
    expect(get(pending.pendingReviewResult)).toEqual({
      ownerId: 7,
      idempotencyKey: command.idempotencyKey,
      result,
    });
    expect(get(stores.authNotice)).toEqual({ kind: "saved", count: 1 });
    expect(get(pending.pendingReviewReplay)).toBeNull();
  });
  it("same-user re-login replays current pending work even when the prior login replay fails", async () => {
    seed();
    const command = pending.createPendingSubmission(7, payload);
    pending.savePendingSubmission(command);
    const state = {
      review_stage: 1,
      ease_factor: "2.50",
      interval_days: 0,
      last_reviewed_at: null,
      next_review_at: "2026-11-17T00:00:00Z",
      version: 1,
    };
    const result = {
      batch_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
      reviewed_at: "2026-11-17T00:00:00Z",
      algorithm_version: "srs-v1",
      items: [
        {
          event_id: 1,
          card_id: payload.items[0].card_id,
          decision: "yes",
          quality: 5,
          previous_state: state,
          resulting_state: { ...state, version: 2 },
        },
      ],
    };
    let finishOld!: (value: Response) => void;
    let finishNew!: (value: Response) => void;
    let sessions = 0;
    const reviews: RequestInit[] = [];
    vi.mocked(fetch).mockImplementation(async (url, init) => {
      if (String(url).endsWith("/auth/logout"))
        return new Response(null, { status: 204 });
      if (String(url).endsWith("/auth/session"))
        return response(tokens(++sessions === 1 ? "first" : "second"));
      reviews.push(init!);
      if (reviews.length === 1)
        return new Promise<Response>((resolve) => {
          finishOld = resolve;
        });
      return new Promise<Response>((resolve) => {
        finishNew = resolve;
      });
    });
    const firstLogin = auth.exchangeCredential("first-synthetic-credential");
    await vi.waitFor(() => expect(finishOld).toBeTypeOf("function"));
    const secondLogin = auth.exchangeCredential("second-synthetic-credential");
    await vi.waitFor(() => expect(finishNew).toBeTypeOf("function"));
    expect(auth.getTokenIfValid()).toBe("ela_second");
    finishOld(
      response(
        {
          error: {
            code: "database_unavailable",
            message: "Unavailable",
            retryable: true,
            request_id: "test-request",
          },
        },
        503,
      ),
    );
    await firstLogin;
    expect(get(pending.pendingReviewReplay)).toEqual({
      ownerId: 7,
      idempotencyKey: command.idempotencyKey,
    });
    expect(localStorage.getItem(pending.PENDING_REVIEW_STORAGE_KEY)).toBe(
      JSON.stringify(command),
    );
    finishNew(response(result));
    await secondLogin;
    expect(reviews).toHaveLength(2);
    for (const request of reviews) {
      expect(request.body).toBe(JSON.stringify(command.payload));
      expect(request.headers).toMatchObject({
        "Idempotency-Key": command.idempotencyKey,
      });
    }
    expect(localStorage.getItem(pending.PENDING_REVIEW_STORAGE_KEY)).toBeNull();
    expect(get(pending.pendingReviewResult)).toEqual({
      ownerId: 7,
      idempotencyKey: command.idempotencyKey,
      result,
    });
    expect(auth.getTokenIfValid()).toBe("ela_second");
    expect(get(stores.authSession).kind).toBe("authenticated");
    expect(get(pending.pendingReviewReplay)).toBeNull();
  });
  it("failed replay releases the active command and retains the exact pending submission", async () => {
    seed();
    const command = pending.createPendingSubmission(7, payload);
    pending.savePendingSubmission(command);
    const activity: unknown[] = [];
    const stop = pending.pendingReviewReplay.subscribe((value) =>
      activity.push(value),
    );
    vi.mocked(fetch).mockImplementation(async (url) => {
      if (String(url).endsWith("/auth/logout"))
        return new Response(null, { status: 204 });
      if (String(url).endsWith("/auth/session")) return response(tokens());
      expect(get(pending.pendingReviewReplay)).toEqual({
        ownerId: 7,
        idempotencyKey: command.idempotencyKey,
      });
      return response(
        {
          error: {
            code: "database_unavailable",
            message: "Unavailable",
            retryable: true,
            request_id: "test-request",
          },
        },
        503,
      );
    });
    await auth.exchangeCredential("synthetic-credential");
    expect(activity).toEqual([
      null,
      { ownerId: 7, idempotencyKey: command.idempotencyKey },
      null,
    ]);
    expect(localStorage.getItem(pending.PENDING_REVIEW_STORAGE_KEY)).toBe(
      JSON.stringify(command),
    );
    expect(get(pending.pendingReviewResult)).toBeNull();
    stop();
  });
  it("different internal user id clears prior answers and reports their count without sending them", async () => {
    seed();
    pending.savePendingSubmission(pending.createPendingSubmission(7, payload));
    vi.mocked(fetch).mockImplementation(async (url) =>
      String(url).endsWith("/auth/logout")
        ? new Response(null, { status: 204 })
        : response(tokens("other", 8)),
    );
    await auth.exchangeCredential("synthetic-other-credential");
    expect(localStorage.getItem(pending.PENDING_REVIEW_STORAGE_KEY)).toBeNull();
    expect(get(stores.authNotice)).toMatchObject({
      kind: "account-changed",
      count: 1,
    });
    expect(
      vi
        .mocked(fetch)
        .mock.calls.some(([url]) => String(url).endsWith("/v1/reviews")),
    ).toBe(false);
  });
  it("guest never extends the 24-hour pending TTL and announces unsent expiry once", async () => {
    vi.useFakeTimers();
    const started = Date.now();
    seed();
    const command = pending.createPendingSubmission(
      7,
      payload,
      started - pending.PENDING_REVIEW_TTL_MS + 10,
    );
    pending.savePendingSubmission(command);
    auth.enterGuestSession();
    const guestDeadline = sessionStorage.getItem("learning_guest_session");
    vi.setSystemTime(started + 11);
    await auth.initializeSession();
    expect(get(stores.authNotice)).toEqual({ kind: "pending-expired" });
    expect(localStorage.getItem(pending.PENDING_REVIEW_STORAGE_KEY)).toBe(
      JSON.stringify(command),
    );
    expect(sessionStorage.getItem("learning_guest_session")).toBe(
      guestDeadline,
    );
    stores.authNotice.set(null);
    await auth.initializeSession();
    expect(get(stores.authNotice)).toBeNull();
    auth.leaveGuestSession();
    await auth.initializeSession();
    expect(get(stores.authNotice)).toBeNull();
    expect(localStorage.getItem(pending.PENDING_REVIEW_STORAGE_KEY)).toBeNull();
  });
  it("Web Locks rejection gracefully falls back to the guarded refresh path", async () => {
    seed();
    Object.defineProperty(navigator, "locks", {
      configurable: true,
      value: { request: vi.fn().mockRejectedValue(new Error("unavailable")) },
    });
    expect(await auth.refreshSession()).toBe("ela_one");
    expect(fetch).toHaveBeenCalledTimes(1);
    Object.defineProperty(navigator, "locks", {
      configurable: true,
      value: undefined,
    });
  });
  it("a second superseded response preserves the session and does not loop", async () => {
    seed();
    await auth.initializeSession();
    vi.mocked(fetch)
      .mockClear()
      .mockImplementation(async () =>
        response({ error: { code: "refresh_superseded" } }, 409),
      );
    expect(await auth.refreshSession()).toBeNull();
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(localStorage.getItem("el_auth_refresh_v1")).toBe("elr_one");
    expect(get(stores.authSession).kind).toBe("authenticated");
    expect(get(stores.authNotice)).toBeNull();
  });
  it("selecting guest again preserves the existing absolute deadline", async () => {
    vi.useFakeTimers();
    auth.enterGuestSession();
    const deadline = sessionStorage.getItem("learning_guest_session");
    vi.setSystemTime(Date.now() + 5 * 60_000);
    expect(auth.enterGuestSession()).toEqual({ ok: true });
    expect(sessionStorage.getItem("learning_guest_session")).toBe(deadline);
  });
  it("guest storage failure cannot leave writes enabled after tokens are dropped", async () => {
    seed();
    await auth.initializeSession();
    const original = Storage.prototype.setItem;
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (
      this: Storage,
      key,
      value,
    ) {
      if (key === "learning_guest_session") throw new Error("unavailable");
      return original.call(this, key, value);
    });
    expect(auth.enterGuestSession().ok).toBe(false);
    expect(get(stores.canWrite)).toBe(false);
    expect(auth.getTokenIfValid()).toBeNull();
  });
  it("same-owner storage rotation preserves valid access without reciprocal refresh", async () => {
    seed();
    await auth.initializeSession();
    const stop = auth.watchSession();
    vi.mocked(fetch).mockClear();
    localStorage.setItem("el_auth_refresh_v1", "elr_other-tab");
    window.dispatchEvent(
      new StorageEvent("storage", {
        key: "el_auth_refresh_v1",
        newValue: "elr_other-tab",
      }),
    );
    expect(auth.getTokenIfValid()).toBe("ela_one");
    expect(fetch).not.toHaveBeenCalled();
    expect(get(stores.authSession).kind).toBe("authenticated");
    stop();
  });
  it("same-owner storage event joins the active flight, which retries the reread token once", async () => {
    seed();
    await auth.initializeSession();
    const stop = auth.watchSession();
    let finish!: (value: Response) => void;
    vi.mocked(fetch)
      .mockClear()
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finish = resolve;
          }),
      )
      .mockResolvedValue(response(tokens("new")));
    const first = auth.refreshSession();
    await vi.waitFor(() => expect(finish).toBeTypeOf("function"));
    localStorage.setItem("el_auth_refresh_v1", "elr_other-tab");
    window.dispatchEvent(
      new StorageEvent("storage", {
        key: "el_auth_refresh_v1",
        newValue: "elr_other-tab",
      }),
    );
    expect(fetch).toHaveBeenCalledTimes(1);
    finish(response({ error: { code: "refresh_superseded" } }, 409));
    expect(await first).toBe("ela_new");
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(
      JSON.parse(vi.mocked(fetch).mock.calls[1][1]!.body as string)
        .refresh_token,
    ).toBe("elr_other-tab");
    expect(get(stores.authSession).kind).toBe("authenticated");
    stop();
  });
  it("allowlist removal on refresh shows the rejected cached email", async () => {
    seed();
    vi.mocked(fetch).mockResolvedValue(
      response({ error: { code: "account_not_allowed" } }, 403),
    );
    await auth.initializeSession();
    expect(get(stores.authSession).kind).toBe("expired");
    expect(get(stores.authNotice)).toEqual({
      kind: "error",
      email: profile.email,
    });
  });
  it("guest expires on focus exactly at the existing absolute deadline", async () => {
    vi.useFakeTimers();
    const started = Date.now();
    auth.enterGuestSession();
    const stop = auth.watchSession();
    vi.setSystemTime(started + 30 * 60_000 - 1);
    window.dispatchEvent(new Event("focus"));
    expect(get(stores.authSession).kind).toBe("guest");
    vi.setSystemTime(started + 30 * 60_000);
    window.dispatchEvent(new Event("focus"));
    expect(get(stores.authSession).kind).toBe("signed-out");
    expect(sessionStorage.getItem("learning_guest_session")).toBeNull();
    stop();
  });
});

describe("offline session recovery", () => {
  it("keeps authOffline true across consecutive network-failed refreshes", async () => {
    seed();
    vi.mocked(fetch).mockRejectedValue(new TypeError("offline"));
    await auth.refreshSession();
    const offlineStates: boolean[] = [];
    const stop = stores.authOffline.subscribe((value) =>
      offlineStates.push(value),
    );
    try {
      await auth.refreshSession();
      expect(fetch).toHaveBeenCalledTimes(2);
      expect(offlineStates).toEqual([true]);
    } finally {
      stop();
    }
  });
  it("makes exactly one refresh request for each offline retry trigger", async () => {
    vi.useFakeTimers();
    seed();
    vi.mocked(fetch).mockRejectedValue(new TypeError("offline"));
    const stop = auth.watchSession();
    try {
      await vi.advanceTimersByTimeAsync(0);
      expect(fetch).toHaveBeenCalledTimes(1);
      for (const [index, event] of ["online", "focus"].entries()) {
        window.dispatchEvent(new Event(event));
        await vi.advanceTimersByTimeAsync(0);
        expect(fetch).toHaveBeenCalledTimes(index + 2);
        expect(vi.mocked(fetch).mock.calls.at(-1)?.[0]).toBe(
          "https://api.example.test/v1/auth/refresh",
        );
      }
      await vi.advanceTimersByTimeAsync(1000);
      expect(fetch).toHaveBeenCalledTimes(4);
      await vi.advanceTimersByTimeAsync(999);
      expect(fetch).toHaveBeenCalledTimes(4);
    } finally {
      stop();
    }
  });
  it.each([
    new TypeError("Failed to fetch"),
    new DOMException("Aborted", "AbortError"),
  ])("retains refresh and profile after fetch rejects: %s", async (error) => {
    seed();
    vi.mocked(fetch).mockRejectedValue(error);
    await auth.initializeSession();
    expect(localStorage.getItem("el_auth_refresh_v1")).toBe("elr_seed");
    expect(localStorage.getItem("el_auth_profile_v1")).toBe(
      JSON.stringify(profile),
    );
    expect(get(stores.authSession).kind).toBe("initializing");
    expect(get(stores.authNotice)).toBeNull();
    expect(get(stores.authOffline)).toBe(true);
  });
  it.each([401, 403, 500])(
    "HTTP %s still expires and clears offline state",
    async (status) => {
      seed();
      stores.authOffline.set(true);
      vi.mocked(fetch).mockResolvedValue(
        response({ error: { code: "refresh_invalid" } }, status),
      );
      await auth.initializeSession();
      expect(get(stores.authSession).kind).toBe("expired");
      expect(localStorage.getItem("el_auth_refresh_v1")).toBeNull();
      expect(get(stores.authOffline)).toBe(false);
    },
  );
  it("a non-JSON HTTP failure is not classified as offline", async () => {
    seed();
    vi.mocked(fetch).mockResolvedValue(
      new Response("unavailable", { status: 503 }),
    );
    await auth.initializeSession();
    expect(get(stores.authSession).kind).toBe("expired");
    expect(get(stores.authOffline)).toBe(false);
  });
  it.each([
    "refresh",
    "sign-in",
    "sign-out",
    "expiry",
    "guest",
    "reset",
    "initialize",
  ])("clears offline state on %s", async (action) => {
    seed();
    stores.authOffline.set(true);
    if (action === "refresh") await auth.refreshSession();
    if (action === "sign-in") await auth.exchangeCredential("synthetic");
    if (action === "sign-out") await auth.signOut();
    if (action === "expiry") auth.expireSession();
    if (action === "guest") auth.enterGuestSession();
    if (action === "reset") stores.setSignOut();
    if (action === "initialize") {
      localStorage.removeItem("el_auth_refresh_v1");
      await auth.initializeSession();
    }
    expect(get(stores.authOffline)).toBe(false);
  });
  it.each(["online", "focus"])(
    "retries on %s with single-flight and cleans up listeners",
    async (event) => {
      seed();
      vi.mocked(fetch).mockRejectedValue(new TypeError("offline"));
      const stop = auth.watchSession();
      try {
        await vi.waitFor(() => expect(get(stores.authOffline)).toBe(true));
        let finish!: (value: Response) => void;
        vi.mocked(fetch)
          .mockClear()
          .mockImplementation(
            () =>
              new Promise((resolve) => {
                finish = resolve;
              }),
          );
        window.dispatchEvent(new Event(event));
        window.dispatchEvent(new Event(event));
        await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
        finish(response(tokens()));
        await vi.waitFor(() =>
          expect(get(stores.authSession).kind).toBe("authenticated"),
        );
        expect(get(stores.authOffline)).toBe(false);
      } finally {
        stop();
      }
      auth.expireSession();
      stores.authSession.set({ kind: "initializing" });
      localStorage.setItem("el_auth_refresh_v1", "elr_after_cleanup");
      vi.mocked(fetch).mockClear();
      window.dispatchEvent(new Event(event));
      expect(fetch).not.toHaveBeenCalled();
    },
  );
  it.each([true, false])(
    "explicit guest keepRefreshToken=%s is respected",
    async (keepRefreshToken) => {
      seed();
      expect(auth.enterGuestSession({ keepRefreshToken })).toEqual({
        ok: true,
      });
      expect(localStorage.getItem("el_auth_refresh_v1")).toBe(
        keepRefreshToken ? "elr_seed" : null,
      );
      // Re-enter the existing deadline branch too.
      localStorage.setItem("el_auth_refresh_v1", "elr_seed");
      auth.enterGuestSession({ keepRefreshToken });
      expect(localStorage.getItem("el_auth_refresh_v1")).toBe(
        keepRefreshToken ? "elr_seed" : null,
      );
    },
  );
  it.each([true, false])(
    "guest default follows authOffline=%s",
    async (offline) => {
      seed();
      stores.authOffline.set(offline);
      auth.enterGuestSession();
      expect(localStorage.getItem("el_auth_refresh_v1")).toBe(
        offline ? "elr_seed" : null,
      );
      expect(get(stores.authOffline)).toBe(false);
    },
  );
  it.each([true, false])(
    "guest exit restores only with a retained token=%s",
    async (retained) => {
      seed();
      auth.enterGuestSession({ keepRefreshToken: retained });
      const kinds: string[] = [];
      const stop = stores.authSession.subscribe((s) => kinds.push(s.kind));
      auth.leaveGuestSession();
      if (retained) {
        await vi.waitFor(() =>
          expect(get(stores.authSession).kind).toBe("authenticated"),
        );
        expect(fetch).toHaveBeenCalledTimes(1);
        expect(kinds).not.toContain("signed-out");
      } else {
        expect(fetch).not.toHaveBeenCalled();
        expect(kinds).toEqual(["guest", "signed-out"]);
      }
      stop();
    },
  );
  it("guest expiry restores the retained session", async () => {
    vi.useFakeTimers();
    seed();
    auth.enterGuestSession({ keepRefreshToken: true });
    const stop = auth.watchSession();
    try {
      vi.setSystemTime(Date.now() + 30 * 60_000);
      vi.mocked(fetch).mockImplementation(async () => response(tokens()));
      window.dispatchEvent(new Event("focus"));
      await vi.waitFor(() =>
        expect(get(stores.authSession).kind).toBe("authenticated"),
      );
      expect(sessionStorage.getItem("learning_guest_session")).toBeNull();
    } finally {
      stop();
    }
  });
});

it("network failure after another tab rotates refresh retains the newer token", async () => {
  seed();
  vi.mocked(fetch).mockImplementation(async () => {
    localStorage.setItem("el_auth_refresh_v1", "elr_other_tab");
    throw new TypeError("offline");
  });
  await auth.initializeSession();
  expect(localStorage.getItem("el_auth_refresh_v1")).toBe("elr_other_tab");
  expect(get(stores.authOffline)).toBe(true);
  expect(get(stores.authSession).kind).toBe("initializing");
});

it("focus failure after access expiry returns to initializing for online recovery", async () => {
  vi.useFakeTimers();
  seed();
  await auth.initializeSession();
  const stop = auth.watchSession();
  try {
    vi.setSystemTime(Date.now() + 900_001);
    vi.mocked(fetch).mockRejectedValue(new TypeError("offline"));
    window.dispatchEvent(new Event("focus"));
    await vi.waitFor(() => expect(get(stores.authOffline)).toBe(true));
    expect(get(stores.authSession).kind).toBe("initializing");
    expect(localStorage.getItem("el_auth_refresh_v1")).toBe("elr_one");
    vi.mocked(fetch).mockImplementation(async () =>
      response(tokens("recovered")),
    );
    window.dispatchEvent(new Event("online"));
    await vi.waitFor(() =>
      expect(auth.getTokenIfValid()).toBe("ela_recovered"),
    );
    expect(get(stores.authOffline)).toBe(false);
  } finally {
    stop();
  }
});

it("offline guest exit retries on reconnect without losing pending answers", async () => {
  seed();
  const command = pending.createPendingSubmission(7, payload);
  pending.savePendingSubmission(command);
  vi.mocked(fetch).mockRejectedValue(new TypeError("offline"));
  await auth.initializeSession();
  auth.enterGuestSession();
  const stop = auth.watchSession();
  try {
    auth.leaveGuestSession();
    await vi.waitFor(() => expect(get(stores.authOffline)).toBe(true));
    expect(localStorage.getItem(pending.PENDING_REVIEW_STORAGE_KEY)).toBe(
      JSON.stringify(command),
    );
    vi.mocked(fetch).mockImplementation(async () => response(tokens()));
    window.dispatchEvent(new Event("online"));
    await vi.waitFor(() =>
      expect(get(stores.authSession).kind).toBe("authenticated"),
    );
    expect(localStorage.getItem(pending.PENDING_REVIEW_STORAGE_KEY)).toBe(
      JSON.stringify(command),
    );
  } finally {
    stop();
  }
});
