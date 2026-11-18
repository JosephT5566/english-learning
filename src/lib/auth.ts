import {
  PUBLIC_GOOGLE_AUTH_CLIENT_ID,
  PUBLIC_EMAIL_WHITE_LIST,
} from "$env/static/public";
import { env } from "$env/dynamic/public";
import { browser } from "$app/environment";
import { get } from "svelte/store";
import {
  authSession,
  authOffline,
  authNotice,
  setSignIn,
  setSignOut,
  signInOpen,
  type SessionProfile,
} from "./stores/auth";
import {
  clearPendingSubmission,
  consumePendingExpiredNotice,
  inspectPendingReviews,
  loadPendingSubmission,
  pendingReviewResult,
  pendingReviewReplay,
  reconcilePendingOwner,
  setPendingGuestMode,
} from "./review/pending";

export const AUTH_REFRESH_STORAGE_KEY = "el_auth_refresh_v1";
export const AUTH_PROFILE_STORAGE_KEY = "el_auth_profile_v1";
const GUEST_SESSION = "learning_guest_session";
const GUEST_DURATION_MS = 30 * 60_000;
const REFRESH_LOCK = "el_auth_refresh_v1";
let accessToken: string | null = null;
let accessExpiresAt = 0;
let cachedProfile: SessionProfile | null = null;
let generation = 0;
let refreshFlight: {
  generation: number;
  promise: Promise<string | null>;
} | null = null;
let replayFlight: {
  key: string;
  generation: number;
  promise: Promise<void>;
} | null = null;
let gsiInitialized = false;
const renderedButtons = new WeakSet<HTMLElement>();
const signInErrorListeners = new Set<(error: Error) => void>();

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function remove(key: string) {
  try {
    localStorage.removeItem(key);
  } catch {
    /* Storage may be disabled. */
  }
}
function refreshToken(): string | null {
  const token = read(AUTH_REFRESH_STORAGE_KEY);
  return token?.startsWith("elr_") ? token : null;
}
function isProfile(value: unknown): value is SessionProfile {
  if (
    typeof value !== "object" ||
    value === null ||
    !("id" in value) ||
    !("email" in value) ||
    typeof value.id !== "number" ||
    !Number.isSafeInteger(value.id) ||
    value.id < 1 ||
    typeof value.email !== "string" ||
    !value.email
  )
    return false;
  return ["name", "picture"].every(
    (key) => !(key in value) || typeof Reflect.get(value, key) === "string",
  );
}
export function getCachedProfile(): SessionProfile | null {
  try {
    const stored: unknown = JSON.parse(
      read(AUTH_PROFILE_STORAGE_KEY) ?? "null",
    );
    if (isProfile(stored)) cachedProfile = stored;
  } catch {
    /* A malformed display profile grants no identity. */
  }
  return cachedProfile;
}
export function getProfile(): SessionProfile | null {
  const session = get(authSession);
  return session.kind === "authenticated" || session.kind === "expired"
    ? session.profile
    : null;
}
export function getIsSignedIn(): boolean {
  return get(authSession).kind === "authenticated";
}
export function getTokenIfValid(): string | null {
  if (
    get(authSession).kind !== "authenticated" ||
    accessExpiresAt <= Date.now()
  )
    return null;
  return accessToken;
}
export function isCurrentToken(token: string): boolean {
  return accessToken === token;
}
export function getSessionGeneration(): number {
  return generation;
}
function clearAccess() {
  accessToken = null;
  accessExpiresAt = 0;
}
function dropAccess() {
  authOffline.set(false);
  clearAccess();
}
export function expireSession(token?: string) {
  if (token !== undefined && !isCurrentToken(token)) return;
  if (get(authSession).kind === "guest") return;
  generation++;
  const profile = getProfile() ?? getCachedProfile();
  dropAccess();
  remove(AUTH_REFRESH_STORAGE_KEY);
  authSession.set({ kind: "expired", profile });
  authNotice.set({ kind: "expired" });
}
class AuthFailure extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
  ) {
    super("Sign-in did not finish. Please try again.");
  }
}
class AuthNetworkFailure extends Error {}
async function authRequest(
  path: string,
  body: object,
  token?: string,
): Promise<unknown> {
  const base = (env.PUBLIC_API_BASE_URL ?? "").trim().replace(/\/+$/, "");
  if (!base) throw new Error("The API is not configured.");
  const response = await fetch(`${base}/v1/auth/${path}`, {
    method: "POST",
    credentials: "omit",
    cache: "no-store",
    ...(path === "logout" ? { keepalive: true } : {}),
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  }).catch((cause: unknown) => {
    throw new AuthNetworkFailure("Authentication network request failed", {
      cause,
    });
  });
  if (response.status === 204) return null;
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new Error("Sign-in did not finish. Please try again.");
  }
  if (!response.ok) {
    const code =
      typeof data === "object" &&
      data !== null &&
      "error" in data &&
      typeof data.error === "object" &&
      data.error !== null &&
      "code" in data.error &&
      typeof data.error.code === "string"
        ? data.error.code
        : "authentication_failed";
    throw new AuthFailure(response.status, code);
  }
  return data;
}
type TokenResponse = {
  access_token: string;
  access_expires_at: string;
  refresh_token: string;
  refresh_expires_at: string;
  user: { id: number; email: string };
  profile: { name: string | null; picture: string | null };
};
function isTokenResponse(value: unknown): value is TokenResponse {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Partial<TokenResponse>;
  return (
    typeof item.access_token === "string" &&
    item.access_token.startsWith("ela_") &&
    typeof item.refresh_token === "string" &&
    item.refresh_token.startsWith("elr_") &&
    typeof item.access_expires_at === "string" &&
    Number.isFinite(Date.parse(item.access_expires_at)) &&
    Date.parse(item.access_expires_at) > Date.now() &&
    typeof item.refresh_expires_at === "string" &&
    Number.isFinite(Date.parse(item.refresh_expires_at)) &&
    Date.parse(item.refresh_expires_at) > Date.now() &&
    typeof item.user === "object" &&
    item.user !== null &&
    Number.isSafeInteger(item.user.id) &&
    item.user.id > 0 &&
    typeof item.user.email === "string" &&
    !!item.user.email &&
    typeof item.profile === "object" &&
    item.profile !== null &&
    ["name", "picture"].every(
      (key) =>
        Reflect.get(item.profile!, key) === null ||
        typeof Reflect.get(item.profile!, key) === "string",
    )
  );
}
function acceptTokens(value: unknown): {
  profile: SessionProfile;
  cleared: number;
} {
  if (!isTokenResponse(value))
    throw new Error("Sign-in did not finish. Please try again.");
  const previous = getCachedProfile();
  const profile: SessionProfile = {
    id: value.user.id,
    email: value.user.email,
    ...(value.profile.name !== null
      ? { name: value.profile.name }
      : previous?.id === value.user.id && previous.name
        ? { name: previous.name }
        : {}),
    ...(value.profile.picture !== null
      ? { picture: value.profile.picture }
      : previous?.id === value.user.id && previous.picture
        ? { picture: previous.picture }
        : {}),
  };
  // Credentials become usable only after browser persistence succeeds.
  localStorage.setItem(AUTH_PROFILE_STORAGE_KEY, JSON.stringify(profile));
  localStorage.setItem(AUTH_REFRESH_STORAGE_KEY, value.refresh_token);
  cachedProfile = profile;
  accessToken = value.access_token;
  accessExpiresAt = Date.parse(value.access_expires_at);
  clearGuestSelection();
  setPendingGuestMode(false);
  const reconciliation = reconcilePendingOwner(profile.id, profile.email);
  setSignIn(profile);
  if (reconciliation.cleared)
    authNotice.set({
      kind: "account-changed",
      count: reconciliation.cleared,
      ...(reconciliation.previousEmail || previous?.email
        ? { previousEmail: reconciliation.previousEmail ?? previous?.email }
        : {}),
    });
  else if (
    !["account-changed", "saved", "pending-expired"].includes(
      get(authNotice)?.kind ?? "",
    )
  )
    authNotice.set(null);
  if (consumePendingExpiredNotice())
    authNotice.set({ kind: "pending-expired" });
  return { profile, cleared: reconciliation.cleared };
}
export function refreshSession(): Promise<string | null> {
  if (get(authSession).kind === "guest") return Promise.resolve(null);
  if (refreshFlight?.generation === generation) return refreshFlight.promise;
  const attempt = generation;
  const ownerId = getProfile()?.id ?? getCachedProfile()?.id;
  const run = async (): Promise<string | null> => {
    if (attempt !== generation || get(authSession).kind === "guest")
      return null;
    let used = refreshToken();
    if (!used) {
      if (attempt === generation) expireSession();
      return null;
    }
    try {
      let value: unknown;
      try {
        value = await authRequest("refresh", { refresh_token: used });
      } catch (error) {
        if (
          !(error instanceof AuthFailure) ||
          error.status !== 409 ||
          error.code !== "refresh_superseded" ||
          attempt !== generation
        )
          throw error;
        used = refreshToken();
        if (!used) throw new AuthFailure(401, "refresh_invalid");
        value = await authRequest("refresh", { refresh_token: used });
      }
      if (
        attempt !== generation ||
        get(authSession).kind === "guest" ||
        refreshToken() !== used
      )
        return null;
      acceptTokens(value);
      return accessToken;
    } catch (error) {
      if (
        error instanceof AuthFailure &&
        error.status === 409 &&
        error.code === "refresh_superseded"
      )
        return null;
      if (attempt === generation && get(authSession).kind !== "guest") {
        if (error instanceof AuthNetworkFailure) {
          clearAccess();
          authSession.set({ kind: "initializing" });
          authOffline.set(refreshToken() !== null);
          return null;
        }
        const email = getProfile()?.email ?? getCachedProfile()?.email;
        expireSession();
        if (
          error instanceof AuthFailure &&
          error.status === 403 &&
          error.code === "account_not_allowed"
        )
          authNotice.set({ kind: "error", ...(email ? { email } : {}) });
      }
      return null;
    }
  };
  const locks = typeof navigator !== "undefined" ? navigator.locks : undefined;
  const withLock = async () => {
    if (!locks?.request) return run();
    try {
      return await locks.request(REFRESH_LOCK, run);
    } catch {
      return run();
    }
  };
  const promise: Promise<string | null> = withLock()
    .then(async (token) => {
      if (token !== null || attempt === generation) return token;
      const kind = get(authSession).kind;
      if (
        ownerId === undefined ||
        kind === "guest" ||
        kind === "signed-out" ||
        getCachedProfile()?.id !== ownerId
      )
        return null;
      const newer = refreshFlight;
      if (newer && newer.generation === generation && newer.promise !== promise)
        return newer.promise;
      return getTokenIfValid();
    })
    .finally(() => {
      if (refreshFlight?.promise === promise) refreshFlight = null;
    });
  refreshFlight = { generation: attempt, promise };
  return promise;
}
export async function ensureAccessToken(
  minValiditySeconds = 0,
): Promise<string | null> {
  if (
    get(authSession).kind === "guest" ||
    get(authSession).kind === "signed-out"
  )
    return null;
  if (accessToken && accessExpiresAt > Date.now() + minValiditySeconds * 1000)
    return accessToken;
  return refreshSession();
}
async function logoutTokens(refresh: string | null, access: string | null) {
  if (!refresh && !access) return;
  try {
    await authRequest(
      "logout",
      refresh ? { refresh_token: refresh } : {},
      access ?? undefined,
    );
  } catch {
    /* Local sign-out remains effective when the service is unavailable. */
  }
}
export async function replayPendingReviews(): Promise<void> {
  const profile = getProfile();
  if (!profile || get(authSession).kind !== "authenticated") return;
  const command = loadPendingSubmission(profile.id);
  if (!command) return;
  const key = `${profile.id}:${command.idempotencyKey}`;
  const attempt = generation;
  if (replayFlight?.key === key && replayFlight.generation === attempt)
    return replayFlight.promise;
  const flight = { key, generation: attempt, promise: Promise.resolve() };
  const isActive = () =>
    replayFlight === flight &&
    generation === attempt &&
    get(authSession).kind === "authenticated" &&
    getProfile()?.id === profile.id;
  const run = async () => {
    try {
      if (!isActive()) return;
      const client = await import("./api/client");
      if (!isActive()) return;
      const result = await client.submitReviews(
        command.payload,
        command.idempotencyKey,
      );
      if (!isActive()) return;
      const current = loadPendingSubmission(profile.id);
      if (
        current?.idempotencyKey !== command.idempotencyKey ||
        JSON.stringify(current.payload) !== JSON.stringify(command.payload)
      )
        return;
      clearPendingSubmission();
      pendingReviewResult.set({
        ownerId: profile.id,
        idempotencyKey: command.idempotencyKey,
        result,
      });
      authNotice.set({ kind: "saved", count: command.payload.items.length });
    } catch {
      /* An unconfirmed exact command remains available for retry. */
    }
  };
  // Publish before the first await so mounted review controls lock this command.
  flight.promise = Promise.resolve()
    .then(run)
    .finally(() => {
      if (replayFlight !== flight) return;
      replayFlight = null;
      pendingReviewReplay.set(null);
    });
  replayFlight = flight;
  pendingReviewReplay.set({
    ownerId: profile.id,
    idempotencyKey: command.idempotencyKey,
  });
  return flight.promise;
}
function credentialEmail(credential: string): string | undefined {
  try {
    const payload = credential.split(".")[1];
    const bytes = Uint8Array.from(
      atob(payload.replace(/-/g, "+").replace(/_/g, "/")),
      (char) => char.charCodeAt(0),
    );
    const value: unknown = JSON.parse(new TextDecoder().decode(bytes));
    if (
      typeof value === "object" &&
      value !== null &&
      "email" in value &&
      typeof value.email === "string"
    )
      return value.email;
  } catch {
    /* Unverified display data is optional and never authorizes a request. */
  }
}
export async function exchangeCredential(credential: string): Promise<void> {
  const refresh = refreshToken();
  const access = accessToken;
  const attempt = ++generation;
  dropAccess();
  remove(AUTH_REFRESH_STORAGE_KEY);
  if (getCachedProfile())
    authSession.set({ kind: "expired", profile: getCachedProfile() });
  authNotice.set({ kind: "signing-in" });
  try {
    if (!credential)
      throw new Error("Sign-in did not finish. Please try again.");
    await logoutTokens(refresh, access);
    const value = await authRequest("session", { credential });
    if (attempt !== generation) return;
    acceptTokens(value);
    signInOpen.set(false);
    await replayPendingReviews();
  } catch (cause) {
    if (attempt !== generation) return;
    dropAccess();
    remove(AUTH_REFRESH_STORAGE_KEY);
    const rejected =
      cause instanceof AuthFailure &&
      cause.status === 403 &&
      cause.code === "account_not_allowed";
    const email = rejected ? credentialEmail(credential) : undefined;
    authNotice.set({ kind: "error", ...(email ? { email } : {}) });
    const error = new Error("Sign-in did not finish. Please try again.");
    for (const listener of signInErrorListeners) listener(error);
  }
}
export function initGsiOnce() {
  if (!browser || gsiInitialized) return;
  const gis = window.google?.accounts?.id;
  if (!gis) throw new Error("Google Identity Services 未載入");
  const emailWhiteList = PUBLIC_EMAIL_WHITE_LIST.split(",");
  gis.initialize({
    client_id: PUBLIC_GOOGLE_AUTH_CLIENT_ID,
    cancel_on_tap_outside: false,
    use_fedcm_for_prompt: true,
    callback: async (res: { credential?: string }) => {
      const credential = res?.credential ?? "";
      const email = credentialEmail(credential);
      // UX precheck only; the exchange verifies identity and server authorization.
      if (!email || !emailWhiteList.includes(email.toLowerCase())) {
        authNotice.set({ kind: "error", ...(email ? { email } : {}) });
        const error = new Error("Google login failed: Email not in whitelist");
        for (const listener of signInErrorListeners) listener(error);
        return;
      }
      await exchangeCredential(credential);
    },
  });
  gsiInitialized = true;
}
export function renderGoogleButton(container: HTMLElement) {
  if (!container || renderedButtons.has(container)) return;
  container.innerHTML = "";
  window.google.accounts.id.renderButton(container, {
    type: "standard",
    theme: "outline",
    size: "large",
    text: "signin_with",
    shape: "pill",
    logo_alignment: "left",
    width: Math.min(320, container.clientWidth || 320),
  });
  renderedButtons.add(container);
}
export async function signOut(): Promise<void> {
  const refresh = refreshToken();
  const access = accessToken;
  generation++;
  dropAccess();
  remove(AUTH_REFRESH_STORAGE_KEY);
  remove(AUTH_PROFILE_STORAGE_KEY);
  cachedProfile = null;
  clearGuestSelection();
  setPendingGuestMode(false);
  setSignOut();
  signInOpen.set(false);
  authNotice.set({ kind: "signed-out" });
  try {
    window.google?.accounts?.id?.disableAutoSelect?.();
  } catch {
    /* GIS may be unavailable. */
  }
  void logoutTokens(refresh, access);
}
function clearGuestSelection() {
  try {
    sessionStorage.removeItem(GUEST_SESSION);
  } catch {
    /* No guest selection can be retained. */
  }
}
export function getGuestTimeRemaining(): number {
  try {
    const deadline = Number(sessionStorage.getItem(GUEST_SESSION));
    return Number.isSafeInteger(deadline)
      ? Math.max(0, deadline - Date.now())
      : 0;
  } catch {
    return 0;
  }
}
export function enterGuestSession({
  keepRefreshToken = get(authOffline),
}: { keepRefreshToken?: boolean } = {}):
  | { ok: true }
  | { ok: false; error: string } {
  if (getGuestTimeRemaining() > 0) {
    generation++;
    dropAccess();
    if (!keepRefreshToken) remove(AUTH_REFRESH_STORAGE_KEY);
    setPendingGuestMode(true);
    authSession.set({ kind: "guest" });
    authNotice.set(null);
    signInOpen.set(false);
    return { ok: true };
  }
  // Snapshot only safe counts before entering guest; guest never loads answer bodies.
  if (get(authSession).kind !== "guest") {
    setPendingGuestMode(false);
    try {
      inspectPendingReviews();
    } catch {
      /* Metadata is optional. */
    }
  }
  generation++;
  dropAccess();
  if (!keepRefreshToken) remove(AUTH_REFRESH_STORAGE_KEY);
  try {
    const deadline = String(Date.now() + GUEST_DURATION_MS);
    sessionStorage.setItem(GUEST_SESSION, deadline);
    if (sessionStorage.getItem(GUEST_SESSION) !== deadline)
      throw new Error("Storage unavailable");
    setPendingGuestMode(true);
    authSession.set({ kind: "guest" });
    authNotice.set(null);
    signInOpen.set(false);
    return { ok: true };
  } catch {
    const profile = getProfile() ?? getCachedProfile();
    if (profile) {
      authSession.set({ kind: "expired", profile });
      authNotice.set({ kind: "expired" });
    } else setSignOut();
    return {
      ok: false,
      error:
        "Guest practice needs session storage. Allow browser storage for this site and try again.",
    };
  }
}
export function leaveGuestSession() {
  generation++;
  dropAccess();
  clearGuestSelection();
  setPendingGuestMode(false);
  authNotice.set(null);
  if (refreshToken()) {
    authSession.set({ kind: "initializing" });
    void initializeSession().catch(() => {
      /* Retain the session for a later startup/focus retry. */
    });
  } else setSignOut();
}
export async function initializeSession(): Promise<void> {
  if (!browser) return;
  const legacy = read("gid_id_token") !== null || read("gid_exp") !== null;
  remove("gid_id_token");
  remove("gid_exp");
  getCachedProfile();
  if (
    getGuestTimeRemaining() > 0 &&
    get(authSession).kind !== "authenticated"
  ) {
    authOffline.set(false);
    setPendingGuestMode(true);
    authSession.set({ kind: "guest" });
    try {
      inspectPendingReviews();
      if (consumePendingExpiredNotice())
        authNotice.set({ kind: "pending-expired" });
    } catch {
      /* Count metadata is optional. */
    }
    return;
  }
  clearGuestSelection();
  setPendingGuestMode(false);
  try {
    inspectPendingReviews();
    if (consumePendingExpiredNotice())
      authNotice.set({ kind: "pending-expired" });
  } catch {
    /* Private recovery reports storage errors at submission. */
  }
  if (getTokenIfValid()) return;
  if (refreshToken()) {
    await refreshSession();
    return;
  }
  authOffline.set(false);
  if (legacy) {
    authSession.set({ kind: "expired", profile: cachedProfile });
    authNotice.set({ kind: "expired" });
    return;
  }
  if (get(authSession).kind !== "expired") setSignOut();
}
export function watchSession(): () => void {
  void initializeSession();
  const refresh = () => {
    if (get(authSession).kind === "guest") {
      if (getGuestTimeRemaining() === 0) leaveGuestSession();
    } else if (get(authSession).kind === "authenticated" && !getTokenIfValid())
      void refreshSession();
    else if (get(authSession).kind === "initializing") void initializeSession();
  };
  const storage = (event: StorageEvent) => {
    if (event.key !== AUTH_REFRESH_STORAGE_KEY && event.key !== null) return;
    const session = get(authSession);
    if (session.kind === "guest") return;
    const stored = refreshToken();
    if (!stored) {
      generation++;
      dropAccess();
      authSession.set({
        kind: "expired",
        profile: getProfile() ?? cachedProfile,
      });
      authNotice.set({ kind: "other-tab" });
      return;
    }
    const current = getProfile();
    const next = getCachedProfile();
    const sameOwner = current !== null && current.id === next?.id;
    if (sameOwner) {
      // Rotation does not invalidate existing access; avoid reciprocal cross-tab rotations.
      if (!getTokenIfValid() && refreshFlight?.generation !== generation)
        void refreshSession();
      return;
    }
    if (
      session.kind === "initializing" &&
      refreshFlight?.generation === generation
    )
      return;
    generation++;
    dropAccess();
    void refreshSession();
  };
  window.addEventListener("storage", storage);
  window.addEventListener("focus", refresh);
  window.addEventListener("online", refresh);
  const timer = window.setInterval(refresh, 1000);
  return () => {
    window.removeEventListener("storage", storage);
    window.removeEventListener("focus", refresh);
    window.removeEventListener("online", refresh);
    window.clearInterval(timer);
  };
}
export function onSignInError(listener: (error: Error) => void) {
  signInErrorListeners.add(listener);
  return () => {
    signInErrorListeners.delete(listener);
  };
}
