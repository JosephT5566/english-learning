import {
  PUBLIC_GOOGLE_AUTH_CLIENT_ID,
  PUBLIC_EMAIL_WHITE_LIST,
} from "$env/static/public";
import { browser } from "$app/environment";
import { authSession, setSignIn, setSignOut } from "./stores/auth";
import {
  clearPendingSubmission,
  loadPendingSubmission,
} from "./review/pending";

// ======== 設定 ========
const STORAGE_TOKEN = "gid_id_token";
const STORAGE_EXP = "gid_exp"; // 秒級 UNIX time
const SAFETY_BUFFER_SEC = 60; // 快過期前 60 秒就視為無效
const MAX_SKEW_SEC = 60; // 允許裝置時間偏差（保守）

const renderedButtons = new WeakSet<HTMLElement>();
const signInErrorListeners = new Set<(error: Error) => void>();
const GUEST_SESSION = "learning_guest_session";
let gsiInitialized = false;

// ======== 公用工具 ========
type JwtPayload = {
  iss?: string;
  aud?: string;
  exp: number; // seconds
  email?: string;
  email_verified?: boolean;
  name?: string;
  picture?: string;
  sub?: string;
};

function decodeJwt(token: string): JwtPayload {
  const [, payload] = token.split(".");
  const bytes = Uint8Array.from(
    atob(payload.replace(/-/g, "+").replace(/_/g, "/")),
    (character) => character.charCodeAt(0),
  );
  const json = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  const value: unknown = JSON.parse(json);
  if (!isJwtPayload(value)) throw new Error("Invalid Google profile");
  return value;
}

function isJwtPayload(value: unknown): value is JwtPayload {
  if (
    !value ||
    typeof value !== "object" ||
    !("exp" in value) ||
    typeof value.exp !== "number" ||
    !Number.isFinite(value.exp)
  )
    return false;
  for (const key of ["iss", "aud", "email", "name", "picture", "sub"]) {
    if (key in value && typeof Reflect.get(value, key) !== "string")
      return false;
  }
  return (
    !("email_verified" in value) || typeof value.email_verified === "boolean"
  );
}

function nowSec() {
  return Math.floor(Date.now() / 1000);
}

// ======== localStorage 存取 ========
function saveToken(token: string, exp: number) {
  localStorage.setItem(STORAGE_TOKEN, token);
  localStorage.setItem(STORAGE_EXP, String(exp));
}

function loadToken(): { token: string | null; exp: number } {
  try {
    const token = localStorage.getItem(STORAGE_TOKEN);
    const exp = Number(localStorage.getItem(STORAGE_EXP) || 0);
    return { token, exp };
  } catch {
    return { token: null, exp: 0 };
  }
}

function clearToken() {
  try {
    localStorage.removeItem(STORAGE_TOKEN);
    localStorage.removeItem(STORAGE_EXP);
  } catch {
    /* Storage can be disabled by the browser. */
  }
}

// 是否有效（含緩衝與時間偏差）
function isTokenStillValid(exp: number) {
  const now = nowSec();
  return now + SAFETY_BUFFER_SEC + MAX_SKEW_SEC < exp;
}

// ======== 狀態查詢 ========
function usableStoredIdentity(): {
  token: string;
  profile: JwtPayload & { sub: string };
} | null {
  const { token, exp } = loadToken();
  if (!token || !isTokenStillValid(exp)) return null;
  try {
    const profile = decodeJwt(token);
    if (!profile.sub?.trim() || !isTokenStillValid(profile.exp)) return null;
    return { token, profile: { ...profile, sub: profile.sub } };
  } catch {
    return null;
  }
}

export function getIsSignedIn(): boolean {
  if (usableStoredIdentity()) return true;
  clearToken();
  return false;
}

export function getProfile(): JwtPayload | null {
  return usableStoredIdentity()?.profile ?? null;
}

export function isCurrentToken(token: string): boolean {
  return loadToken().token === token;
}

export function getTokenIfValid(): string | null {
  const identity = usableStoredIdentity();
  if (!identity) {
    clearToken();
    setSignOut();
    return null;
  }
  return identity.token;
}

// ======== 登入流程（按鈕/自動） ========

export function initGsiOnce() {
  if (!browser) {
    return;
  }

  const gis = window?.google?.accounts?.id;
  if (!gis) {
    throw new Error("Google Identity Services 未載入");
  }

  const EMAIL_WHITE_LIST: string[] = PUBLIC_EMAIL_WHITE_LIST.split(",");
  if (gsiInitialized) {
    return;
  }
  gis.initialize({
    client_id: PUBLIC_GOOGLE_AUTH_CLIENT_ID,
    cancel_on_tap_outside: false,
    use_fedcm_for_prompt: true,
    callback: (res: { credential?: string }) => {
      try {
        const idToken = res?.credential;
        if (!idToken) {
          throw new Error("Did not receive Google ID token");
        }
        const payload = decodeJwt(idToken);

        if (!payload.email || payload.email_verified !== true) {
          throw new Error("Google login failed: Email not verified");
        }
        const email = String(payload.email).toLowerCase();
        if (!EMAIL_WHITE_LIST.includes(email)) {
          throw new Error("Google login failed: Email not in whitelist");
        }

        if (!isTokenStillValid(payload.exp)) {
          throw new Error("Google login failed: Expired token");
        }
        if (!payload.sub?.trim()) {
          throw new Error("Google login failed: No subject in token");
        }
        const previousSubject = getProfile()?.sub;
        if (previousSubject && previousSubject !== payload.sub) {
          clearPendingSubmission();
        } else {
          loadPendingSubmission(payload.sub);
        }
        saveToken(idToken, payload.exp);
        clearGuestSelection();
        setSignIn(payload);
      } catch (e) {
        const error = e instanceof Error ? e : new Error("Google login failed");
        for (const listener of signInErrorListeners) listener(error);
      }
    },
  });
  gsiInitialized = true;
}

export function renderGoogleButton(container: HTMLElement) {
  if (!container || renderedButtons.has(container)) {
    return;
  }

  const gis = window.google.accounts.id;
  container.innerHTML = "";
  gis.renderButton(container, {
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

// ======== 登出 ========
export function signOut() {
  clearToken();
  clearGuestSelection();
  setSignOut();
  // 可選：通知 GIS 取消自動選擇
  try {
    window.google?.accounts?.id?.disableAutoSelect?.();
  } catch {
    /* GIS may be unavailable while signing out locally. */
  }
}

function clearGuestSelection() {
  try {
    sessionStorage.removeItem(GUEST_SESSION);
  } catch {
    /* No stored guest selection. */
  }
}

export function enterGuestSession():
  | { ok: true }
  | { ok: false; error: string } {
  if (getIsSignedIn())
    return { ok: false, error: "Sign out before starting guest practice." };
  try {
    sessionStorage.setItem(GUEST_SESSION, "1");
    if (sessionStorage.getItem(GUEST_SESSION) !== "1")
      throw new Error("Storage unavailable");
    authSession.set({ kind: "guest" });
    return { ok: true };
  } catch {
    return {
      ok: false,
      error:
        "Guest practice needs session storage. Allow browser storage for this site and try again.",
    };
  }
}

export function initializeSession() {
  const profile = getProfile();
  if (profile && getIsSignedIn()) {
    clearGuestSelection();
    setSignIn(profile);
    return;
  }
  try {
    if (sessionStorage.getItem(GUEST_SESSION) === "1") {
      authSession.set({ kind: "guest" });
      return;
    }
  } catch {
    /* The homepage reports storage failure when guest is selected. */
  }
  setSignOut();
}

export function watchSession() {
  initializeSession();
  const refresh = () => initializeSession();
  const onStorage = (event: StorageEvent) => {
    if (
      event.key === null ||
      event.key === STORAGE_TOKEN ||
      event.key === STORAGE_EXP
    )
      refresh();
  };
  window.addEventListener("storage", onStorage);
  window.addEventListener("focus", refresh);
  const timer = window.setInterval(refresh, 1000);
  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener("focus", refresh);
    window.clearInterval(timer);
  };
}

export function onSignInError(listener: (error: Error) => void) {
  signInErrorListeners.add(listener);
  return () => {
    signInErrorListeners.delete(listener);
  };
}
