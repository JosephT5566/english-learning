import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
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
    const stop = auth.watchSession();
    localStorage.removeItem("el_auth_refresh_v1");
    window.dispatchEvent(
      new StorageEvent("storage", {
        key: "el_auth_refresh_v1",
        newValue: null,
      }),
    );
    expect(get(stores.authSession).kind).toBe("expired");
    expect(get(stores.authNotice)).toEqual({ kind: "other-tab" });
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
