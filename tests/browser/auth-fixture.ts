import { expect, type Page } from "@playwright/test";

export const apiOrigin = "http://127.0.0.1:8001";
export const refreshKey = "el_auth_refresh_v1";
export const profileKey = "el_auth_profile_v1";
export const pendingKey = "pending_review_submission_v2";
export const pendingMetaKey = "el_review_pending_meta_v1";

export function fixtureUserId(mode: string): number {
  const subject = mode.startsWith("browser-test-")
    ? mode
    : `browser-test-${mode}`;
  let hash = 2166136261;
  for (const character of subject)
    hash = Math.imul(hash ^ character.charCodeAt(0), 16777619) >>> 0;
  return (hash % 2147483646) + 1;
}

export function googleCredential(
  mode = "success",
  email = "browser-test@example.com",
): string {
  const encode = (value: object) =>
    btoa(JSON.stringify(value))
      .replaceAll("+", "-")
      .replaceAll("/", "_")
      .replaceAll("=", "");
  return `${encode({ alg: "none" })}.${encode({
    iss: "https://accounts.google.com",
    aud: "browser-contract-test",
    sub: mode.startsWith("browser-test-") ? mode : `browser-test-${mode}`,
    email,
    email_verified: true,
    exp: Math.floor(Date.now() / 1000) + 3600,
    name: "Browser Test",
  })}.test-signature`;
}

async function issue(page: Page, mode: string, reset = false) {
  const response = await page.request.post(`${apiOrigin}/v1/auth/session`, {
    data: { credential: googleCredential(mode) },
  });
  expect(response.status()).toBe(200);
  const tokens = await response.json();
  if (reset) {
    const cleared = await page.request.post(
      `${apiOrigin}/__test__/auth/reset-data`,
      { data: { refresh_token: tokens.refresh_token } },
    );
    expect(cleared.status()).toBe(200);
  }
  return {
    refresh: String(tokens.refresh_token),
    profile: {
      ...tokens.user,
      ...(typeof tokens.profile.name === "string"
        ? { name: tokens.profile.name }
        : {}),
      ...(typeof tokens.profile.picture === "string"
        ? { picture: tokens.profile.picture }
        : {}),
    },
  };
}

export async function seedSignedIn(page: Page, mode = "success") {
  const session = await issue(page, mode, true);
  await page.addInitScript(
    ({ session, marker }) => {
      if (sessionStorage.getItem(marker)) return;
      sessionStorage.setItem(marker, "1");
      localStorage.setItem("el_auth_refresh_v1", session.refresh);
      localStorage.setItem(
        "el_auth_profile_v1",
        JSON.stringify(session.profile),
      );
      sessionStorage.removeItem("learning_guest_session");
    },
    { session, marker: `fixture-auth-${crypto.randomUUID()}` },
  );
  return session;
}

export async function signInAs(page: Page, mode = "success") {
  const session = await issue(page, mode);
  await page.evaluate(({ refresh, profile }) => {
    localStorage.setItem("el_auth_profile_v1", JSON.stringify(profile));
    const oldValue = localStorage.getItem("el_auth_refresh_v1");
    localStorage.setItem("el_auth_refresh_v1", refresh);
    sessionStorage.removeItem("learning_guest_session");
    window.dispatchEvent(
      new StorageEvent("storage", {
        key: "el_auth_refresh_v1",
        oldValue,
        newValue: refresh,
        storageArea: localStorage,
      }),
    );
  }, session);
  return session;
}

export async function removeSessionInAnotherTab(page: Page) {
  await page.evaluate(() => {
    const oldValue = localStorage.getItem("el_auth_refresh_v1");
    localStorage.removeItem("el_auth_refresh_v1");
    localStorage.removeItem("el_auth_profile_v1");
    window.dispatchEvent(
      new StorageEvent("storage", {
        key: "el_auth_refresh_v1",
        oldValue,
        newValue: null,
        storageArea: localStorage,
      }),
    );
  });
}

export async function authHook(
  page: Page,
  action: "expire-access" | "revoke" | "allowlist",
  allowed?: boolean,
) {
  const refresh_token = await page.evaluate(() =>
    localStorage.getItem("el_auth_refresh_v1"),
  );
  const response = await page.request.post(
    `${apiOrigin}/__test__/auth/${action}`,
    { data: { refresh_token, allowed } },
  );
  expect(response.status()).toBe(200);
}

export async function installMockGis(
  page: Page,
  mode = "success",
  email = "browser-test@example.com",
) {
  await page.route("https://accounts.google.com/gsi/client", (route) =>
    route.fulfill({
      contentType: "application/javascript",
      body: "window.__mockGisScriptLoaded = true;",
    }),
  );
  const credential = googleCredential(mode, email);
  await page.addInitScript(
    ({ credential }) => {
      let callback: ((response: { credential: string }) => void) | undefined;
      Object.defineProperty(window, "google", {
        configurable: true,
        value: {
          accounts: {
            id: {
              initialize(options: { callback: typeof callback }) {
                callback = options.callback;
              },
              renderButton(container: HTMLElement) {
                const button = document.createElement("button");
                button.textContent = "Sign in with Google";
                button.onclick = () => callback?.({ credential });
                container.append(button);
              },
              disableAutoSelect() {},
            },
          },
        },
      });
    },
    { credential },
  );
}

export async function signInFromDialog(page: Page) {
  const menu = page.getByRole("button", { name: /account menu/i });
  await menu.click();
  await page.getByRole("menuitem", { name: "Sign in", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Sign in with Google" })
    .click();
}
