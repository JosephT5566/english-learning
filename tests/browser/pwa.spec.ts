// @ts-expect-error Node built-in types are absent; Playwright runs this import in Node.
import { readFileSync } from "node:fs";
import {
  expect,
  test,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import { guestLastGoodKey } from "../../src/lib/pwa/policy";
import {
  apiOrigin,
  profileKey,
  refreshKey,
  seedSignedIn,
} from "./auth-fixture";

let base = "";
const origin = "http://127.0.0.1:4173";
let home = `${origin}/`;
const guestCache = "english-learning-guest-v1";
const fixture = JSON.parse(
  readFileSync("tests/browser/fixtures/guest-cards.json", "utf8"),
);
let guestPath = "/guest/cards.json";

async function settings(request: APIRequestContext, value: object) {
  expect(
    (await request.post(`${origin}/__test__/pwa`, { data: value })).ok(),
  ).toBe(true);
}
async function controlled(page: Page) {
  await page.goto(home);
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await page.waitForFunction(() => !!navigator.serviceWorker.controller);
}
async function savedGuest(page: Page) {
  return page.evaluate(
    async ({ guestCache, guestPath }) => {
      const response = await (await caches.open(guestCache)).match(guestPath);
      return response ? response.json() : null;
    },
    { guestCache, guestPath },
  );
}
async function readGuest(page: Page) {
  return page.evaluate(async (path) => {
    const response = await fetch(path, {
      credentials: "omit",
      redirect: "error",
    });
    return { status: response.status, text: await response.text() };
  }, guestPath);
}
async function waitingRegistration(page: Page) {
  const registration = await page.evaluateHandle(async () => {
    const registration = await navigator.serviceWorker.getRegistration();
    if (!registration)
      throw new Error("Expected an existing worker registration");
    return registration;
  });
  // The registration handle is live; poll its state with a synchronous predicate.
  await page.waitForFunction(
    (registration) =>
      !!navigator.serviceWorker.controller &&
      registration.waiting?.state === "installed" &&
      registration.active === navigator.serviceWorker.controller,
    registration,
  );
  return registration;
}
async function update(page: Page, request: APIRequestContext, worker: string) {
  await settings(request, { worker });
  await page.evaluate(async () => {
    await (await navigator.serviceWorker.getRegistration())!.update();
  });
  await waitingRegistration(page);
}
async function acceptUpdate(page: Page) {
  const registration = await waitingRegistration(page);
  await registration.evaluate((registration) => {
    const waiting = registration.waiting;
    if (!waiting || waiting.state !== "installed") {
      throw new Error(
        "Expected an installed waiting worker before accepting update",
      );
    }
    navigator.serviceWorker.addEventListener(
      "controllerchange",
      () => location.reload(),
      { once: true },
    );
    waiting.postMessage({ type: "SKIP_WAITING" });
  });
}

test.beforeEach(async ({ request, baseURL }) => {
  base = new URL(baseURL!).pathname.replace(/\/$/, "");
  home = `${origin}${base}/`;
  guestPath = `${base}/guest/cards.json`;
  await settings(request, { reset: true });
});
test.afterEach(async ({ context, request }) => {
  await context.setOffline(false);
  await settings(request, { reset: true });
});

test("manifest and apple icon resolve on home, review and real-404 deep links", async ({
  page,
  request,
}) => {
  await settings(request, { fallbackStatus: 404 });
  for (const path of ["/", "/review", "/decks/pwa-deep-link"]) {
    // Inspect the original HTML even when auth subsequently redirects the page.
    const response = await request.get(`${origin}${base}${path}`);
    expect(response.status()).toBe(path.includes("pwa-deep") ? 404 : 200);
    const html = await response.text();
    const href = html.match(/rel="manifest"\s+href="([^"]+)"/)![1];
    const url = new URL(href, `${origin}${base}${path}`).href;
    expect(url).toBe(`${origin}${base}/manifest.webmanifest`);
    const appleHref = html.match(/rel="apple-touch-icon"\s+href="([^"]+)"/)![1];
    expect(new URL(appleHref, `${origin}${base}${path}`).href).toBe(
      `${origin}${base}/icons/apple-touch-icon.png`,
    );
    const manifestResponse = await request.get(url);
    expect(manifestResponse.headers()["content-type"]).toContain("json");
    const manifest = await manifestResponse.json();
    expect(manifest).toMatchObject({
      name: "English Learning",
      short_name: "English",
      display: "standalone",
      theme_color: "#cad8e4",
      background_color: "#cad8e4",
    });
    for (const key of ["id", "scope", "start_url"])
      expect(new URL(manifest[key], url).href).toBe(home);
    for (const icon of manifest.icons) {
      const image = await request.get(new URL(icon.src, url).href);
      expect(image.status()).toBe(200);
      expect(image.headers()["content-type"]).toBe("image/png");
    }
  }
  await page.goto(home);
  expect(
    await page
      .locator('meta[name="apple-mobile-web-app-status-bar-style"]')
      .getAttribute("content"),
  ).toBe("default");
});

test("registration precaches shell only and leaves unrelated caches intact", async ({
  page,
}) => {
  await controlled(page);
  expect(
    await page.evaluate(
      async () => (await navigator.serviceWorker.getRegistration())!.scope,
    ),
  ).toBe(home);
  const paths = await page.evaluate(async () => {
    const names = await caches.keys();
    const shell = await caches.open(
      names.find((name) => name.startsWith("english-learning-shell-"))!,
    );
    return (await shell.keys()).map((request) => new URL(request.url).pathname);
  });
  for (const path of [
    "/",
    "/review",
    "/404.html",
    "/_app/env.js",
    "/manifest.webmanifest",
    "/icons/icon-192.png",
    "/icons/icon-512.png",
    "/icons/icon-512-maskable.png",
  ])
    expect(paths).toContain(`${base}${path}`);
  for (const path of [
    "/guest/cards.json",
    "/robots.txt",
    "/.nojekyll",
    "/_app/version.json",
    "/service-worker.js",
  ])
    expect(paths).not.toContain(`${base}${path}`);
});

for (const path of ["/", "/review", "/decks", "/decks/pwa-deep-link"]) {
  test(`offline shell ${path} lands on home and keeps the session`, async ({
    page,
    context,
    request,
  }) => {
    await seedSignedIn(page);
    await controlled(page);
    const before = await page.evaluate(
      ({ refreshKey, profileKey }) => [
        localStorage.getItem(refreshKey),
        localStorage.getItem(profileKey),
      ],
      { refreshKey, profileKey },
    );
    await settings(request, { networkDown: true });
    // Verify that the server itself cannot supply the shell to a worker fetch.
    await expect(request.get(home, { timeout: 2000 })).rejects.toThrow();
    await context.setOffline(true);
    const response = await page.goto(`${origin}${base}${path}`);
    expect(response?.fromServiceWorker()).toBe(true);
    await expect(page).toHaveURL(home);
    await expect(
      page.getByRole("button", { name: "Practice public cards", exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Session ended", { exact: true })).toHaveCount(
      0,
    );
    expect(
      await page.evaluate(
        ({ refreshKey, profileKey }) => [
          localStorage.getItem(refreshKey),
          localStorage.getItem(profileKey),
        ],
        { refreshKey, profileKey },
      ),
    ).toEqual(before);
    await settings(request, { networkDown: false });
    await context.setOffline(false);
    await page.evaluate(() => window.dispatchEvent(new Event("online")));
    await expect(
      page.getByRole("button", { name: /Account menu for/ }),
    ).toBeVisible();
    expect(
      await page.evaluate((key) => !!localStorage.getItem(key), refreshKey),
    ).toBe(true);
  });
}

test("navigation is live online, non-OK fallback is not cached and API requests bypass worker", async ({
  page,
  request,
  context,
}) => {
  await controlled(page);
  const previous = await page.reload();
  const response = await page.reload();
  expect(response?.fromServiceWorker()).toBe(true);
  // Different server sequence values prove each navigation reached the network.
  expect(response?.headers()["x-pwa-test-network"]).toBeTruthy();
  expect(response?.headers()["x-pwa-test-network"]).not.toBe(
    previous?.headers()["x-pwa-test-network"],
  );
  await settings(request, { fallbackStatus: 404 });
  await page.evaluate(async (path) => {
    const frame = document.createElement("iframe");
    frame.src = path;
    document.body.append(frame);
    await new Promise<void>((resolve) => {
      frame.onload = () => resolve();
    });
    frame.remove();
  }, `${base}/unknown-pwa-path`);
  expect(
    await page.evaluate(async (path) => {
      const names = (await caches.keys()).filter((name) =>
        name.startsWith("english-learning-shell-"),
      );
      return !!(await (await caches.open(names[0])).match(path));
    }, `${base}/unknown-pwa-path`),
  ).toBe(false);
  for (const path of [
    `${origin}${base}/v1/probe`,
    `${apiOrigin}/health`,
    `${origin}${base}/_app/version.json`,
  ]) {
    const responsePromise = page.waitForResponse(path);
    await page.evaluate(
      (url) =>
        fetch(url)
          .then(() => undefined)
          .catch(() => undefined),
      path,
    );
    expect((await responsePromise).fromServiceWorker()).toBe(false);
  }
  const postResponse = page.waitForResponse(
    (response) =>
      response.url() === `${origin}${guestPath}` &&
      response.request().method() === "POST",
  );
  await page.evaluate(
    (path) => fetch(path, { method: "POST" }).then(() => undefined),
    guestPath,
  );
  expect((await postResponse).fromServiceWorker()).toBe(false);
  await context.setOffline(true);
  expect(
    await page.evaluate(
      async (url) =>
        fetch(url).then(
          () => false,
          () => true,
        ),
      `${apiOrigin}/health`,
    ),
  ).toBe(true);
});

test("waiting update stays passive, reload activates once, cleanup preserves guest and foreign cache", async ({
  page,
  request,
}) => {
  await controlled(page);
  await page.evaluate(async () => {
    await caches.open("foreign-pwa-cache");
    await caches.open("english-learning-shell-obsolete");
    await caches.open("english-learning-guest-v0");
    sessionStorage.setItem("pwa-loads", "0");
  });
  await page.addInitScript(() =>
    sessionStorage.setItem(
      "pwa-loads",
      String(Number(sessionStorage.getItem("pwa-loads")) + 1),
    ),
  );
  const originalController = await page.evaluateHandle(
    () => navigator.serviceWorker.controller,
  );
  await update(page, request, "update");
  expect(
    await page.evaluate(
      (controller) => navigator.serviceWorker.controller === controller,
      originalController,
    ),
  ).toBe(true);
  expect(
    await page.evaluate(async () => {
      const registration = await navigator.serviceWorker.getRegistration();
      return {
        waiting: registration?.waiting?.state,
        active: registration?.active?.state,
        controlled: !!navigator.serviceWorker.controller,
      };
    }),
  ).toEqual({ waiting: "installed", active: "activated", controlled: true });
  expect(await page.evaluate(() => sessionStorage.getItem("pwa-loads"))).toBe(
    "0",
  );
  expect(
    await page.evaluate(async () =>
      (await caches.keys()).includes("english-learning-shell-obsolete"),
    ),
  ).toBe(true);
  await acceptUpdate(page);
  await page.waitForFunction(() => sessionStorage.getItem("pwa-loads") === "1");
  await expect
    .poll(() => page.evaluate(() => caches.keys()))
    .not.toContain("english-learning-shell-obsolete");
  const names = await page.evaluate(() => caches.keys());
  expect(names).toContain("foreign-pwa-cache");
  expect(names).toContain(guestCache);
  expect(names).not.toContain("english-learning-guest-v0");
});

test("disabled worker removes only app caches and unregisters", async ({
  page,
  request,
}) => {
  await controlled(page);
  await page.evaluate(async () => {
    await caches.open("foreign-pwa-cache");
  });
  await update(page, request, "kill");
  await page.evaluate(async () =>
    (await navigator.serviceWorker.getRegistration())!.waiting!.postMessage({
      type: "SKIP_WAITING",
    }),
  );
  await expect
    .poll(() =>
      page.evaluate(
        async () => !!(await navigator.serviceWorker.getRegistration()),
      ),
    )
    .toBe(false);
  const names = await page.evaluate(() => caches.keys());
  expect(
    names.filter((name) => /^english-learning-(shell|guest)-/.test(name)),
  ).toEqual([]);
  expect(names).toContain("foreign-pwa-cache");
  // The current document keeps its controller until navigation, but the disabled worker has no fetch handler.
  const response = page.waitForResponse(`${home}manifest.webmanifest`);
  await page.evaluate((url) => fetch(url), `${home}manifest.webmanifest`);
  expect((await response).fromServiceWorker()).toBe(false);
});

test("guest snapshot is live, empty withdrawal replaces it, failures keep the last good copy", async ({
  page,
  request,
}) => {
  await controlled(page);
  const changed = { ...fixture, generated_at: "2026-11-18T01:00:00Z" };
  await settings(request, { snapshot: { body: JSON.stringify(changed) } });
  expect(JSON.parse((await readGuest(page)).text)).toEqual(changed);
  expect(await savedGuest(page)).toEqual(changed);
  for (const status of [201, 206, 404, 503]) {
    const body = JSON.stringify({
      ...fixture,
      generated_at: new Date(
        Date.UTC(2026, 10, 19, 0, 0, status % 60),
      ).toISOString(),
    });
    await settings(request, { snapshot: { status, body } });
    expect(await readGuest(page)).toEqual({ status, text: body });
    expect(await savedGuest(page)).toEqual(changed);
  }
  for (const snapshot of [
    { body: "invalid" },
    { body: "x".repeat(512 * 1024 + 1) },
    { body: '{"schema_version":2,"items":[]}' },
    { status: 302, location: "/manifest.webmanifest", body: "" },
  ]) {
    await settings(request, { snapshot });
    await readGuest(page).catch(() => undefined);
    expect(await savedGuest(page)).toEqual(changed);
  }
  const empty = { ...changed, items: [] };
  await settings(request, { snapshot: { body: JSON.stringify(empty) } });
  expect(JSON.parse((await readGuest(page)).text)).toEqual(empty);
  expect(await savedGuest(page)).toEqual(empty);
  await settings(request, { networkDown: true });
  expect(JSON.parse((await readGuest(page)).text)).toEqual(empty);
});

test("offline public round uses saved snapshot and retains a signed-in session", async ({
  page,
  context,
  request,
}) => {
  await seedSignedIn(page);
  await controlled(page);
  await readGuest(page);
  const refresh = await page.evaluate(
    (key) => localStorage.getItem(key),
    refreshKey,
  );
  await settings(request, { networkDown: true });
  await context.setOffline(true);
  await page.reload();
  await page
    .getByRole("button", { name: "Practice public cards", exact: true })
    .click();
  for (let index = 0; index < fixture.items.length; index++) {
    const active = page.locator('.swipe--card[aria-hidden="false"]');
    await expect(async () => {
      await active.press("Enter");
      await expect(active).toHaveAttribute("aria-expanded", "true", {
        timeout: 100,
      });
    }).toPass({ intervals: [200], timeout: 15000 });
    await page.getByRole("button", { name: "Knew it", exact: true }).click();
  }
  await expect(
    page.getByRole("button", { name: "Practice again" }),
  ).toBeVisible();
  expect(
    await page.evaluate((key) => localStorage.getItem(key), refreshKey),
  ).toBe(refresh);
  await settings(request, { networkDown: false });
  await context.setOffline(false);
  await page.getByRole("button", { name: /Guest account menu/i }).click();
  await page
    .getByRole("menuitem", { name: "Leave guest practice", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: /Account menu for/ }),
  ).toBeVisible();
});

test("page strict rejection restores the last good snapshot for offline practice", async ({
  page,
  request,
  context,
}) => {
  await settings(request, { snapshot: { body: JSON.stringify(fixture) } });
  await controlled(page);
  await page
    .getByRole("button", { name: "Continue as guest", exact: true })
    .click();
  await expect(page.locator('.swipe--card[aria-hidden="false"]')).toBeVisible();
  const good = await savedGuest(page);
  expect(good).toEqual(fixture);
  expect(
    await page.evaluate(
      async ({ guestCache, key }) => {
        const response = await (await caches.open(guestCache)).match(key);
        return response ? response.json() : null;
      },
      { guestCache, key: guestLastGoodKey(base) },
    ),
  ).toEqual(good);
  await page.getByRole("button", { name: /Guest account menu/i }).click();
  await page
    .getByRole("menuitem", { name: "Leave guest practice", exact: true })
    .click();
  await settings(request, {
    snapshot: {
      body: JSON.stringify({
        ...fixture,
        items: [fixture.items[0], fixture.items[0]],
      }),
    },
  });
  await page
    .getByRole("button", { name: "Continue as guest", exact: true })
    .click();
  await expect(
    page.getByText(
      "The card snapshot was unavailable or invalid. Please try again.",
    ),
  ).toBeVisible();
  await expect.poll(() => savedGuest(page)).toEqual(good);
  await page.getByRole("button", { name: /Guest account menu/i }).click();
  await page
    .getByRole("menuitem", { name: "Leave guest practice", exact: true })
    .click();
  await settings(request, { networkDown: true });
  await context.setOffline(true);
  await page.reload();
  await page
    .getByRole("button", { name: "Continue as guest", exact: true })
    .click();
  for (let index = 0; index < fixture.items.length; index++) {
    const active = page.locator('.swipe--card[aria-hidden="false"]');
    await expect(async () => {
      await active.press("Enter");
      await expect(active).toHaveAttribute("aria-expanded", "true", {
        timeout: 100,
      });
    }).toPass({ intervals: [200], timeout: 15000 });
    await page.getByRole("button", { name: "Knew it", exact: true }).click();
  }
  await expect(
    page.getByRole("button", { name: "Practice again" }),
  ).toBeVisible();
  expect(await savedGuest(page)).toEqual(good);
});
