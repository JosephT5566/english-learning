// @ts-expect-error Node built-in types are absent; Playwright runs this import in Node.
import { readFileSync } from "node:fs";
import {
  expect,
  test,
  type Page,
  type APIRequestContext,
} from "@playwright/test";
import { seedSignedIn, refreshKey, pendingKey } from "./auth-fixture";

const origin = "http://127.0.0.1:4173";
const fixture = JSON.parse(
  readFileSync("tests/browser/fixtures/guest-cards.json", "utf8"),
);
let home = `${origin}/`;
let guestPath = "/guest/cards.json";
async function settings(request: APIRequestContext, data: object) {
  expect((await request.post(`${origin}/__test__/pwa`, { data })).ok()).toBe(
    true,
  );
}
async function controlled(page: Page) {
  await page.goto(home);
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await page.waitForFunction(() => !!navigator.serviceWorker.controller);
}
async function offlineLaunch(page: Page, request: APIRequestContext) {
  await seedSignedIn(page);
  await controlled(page);
  await expect(
    page.getByRole("button", { name: /Account menu for/ }),
  ).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(async (path) => {
        const cached = await (
          await caches.open("english-learning-guest-v1")
        ).match(path);
        return cached ? (await cached.json()).generated_at : null;
      }, guestPath),
    )
    .toBe(fixture.generated_at);
  const refresh = await page.evaluate(
    (key) => localStorage.getItem(key),
    refreshKey,
  );
  await settings(request, { networkDown: true });
  await page.context().setOffline(true);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "You're offline" }),
  ).toBeVisible();
  return refresh;
}
test.beforeEach(async ({ request, baseURL }) => {
  home = baseURL!;
  guestPath = `${new URL(home).pathname.replace(/\/$/, "")}/guest/cards.json`;
  await settings(request, { reset: true });
});
test.afterEach(async ({ context, request }) => {
  await context.setOffline(false);
  await settings(request, { reset: true });
});

test("no update dot or menu action without a waiting worker", async ({
  page,
}) => {
  await controlled(page);
  const avatar = page.getByRole("button", { name: /account menu/i });
  await expect(avatar).not.toHaveClass(/update-ready/);
  await expect(avatar).not.toHaveAttribute("title", /update available/);
  await avatar.click();
  await expect(
    page.getByRole("menuitem", { name: "Reload to update" }),
  ).toHaveCount(0);
});

test("second worker shows a passive review cue and menu reload activates exactly once", async ({
  page,
  request,
}) => {
  await controlled(page);
  await page.getByRole("button", { name: /Continue as guest/ }).click();
  const card = page.locator('.swipe--card[aria-hidden="false"]');
  await expect(card).toBeVisible();
  await card.focus();
  await page.evaluate((key) => {
    localStorage.setItem(key, "pending-answer-sentinel");
    sessionStorage.setItem("pwa-ui-loads", "0");
  }, pendingKey);
  await page.addInitScript(() =>
    sessionStorage.setItem(
      "pwa-ui-loads",
      String(Number(sessionStorage.getItem("pwa-ui-loads")) + 1),
    ),
  );
  const original = await page.evaluateHandle(
    () => navigator.serviceWorker.controller,
  );
  await settings(request, { worker: "update" });
  await page.evaluate(async () => {
    await (await navigator.serviceWorker.getRegistration())!.update();
  });
  const avatar = page.getByRole("button", { name: /update available/ });
  await expect(avatar).toHaveClass(/update-ready/);
  await expect(avatar).toHaveAttribute("title", /update available/);
  await expect
    .poll(() =>
      avatar.evaluate(
        (element) => getComputedStyle(element, "::before").backgroundColor,
      ),
    )
    .toBe("rgb(64, 117, 166)");
  await expect(card).toBeFocused();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(
    await page.evaluate(
      (controller) => navigator.serviceWorker.controller === controller,
      original,
    ),
  ).toBe(true);
  expect(
    await page.evaluate(() => sessionStorage.getItem("pwa-ui-loads")),
  ).toBe("0");
  await avatar.click();
  const item = page.getByRole("menuitem").first();
  await expect(item).toHaveText("Reload to update");
  expect(
    await item.evaluate((element) => element.getBoundingClientRect().height),
  ).toBeGreaterThanOrEqual(44);
  await Promise.all([page.waitForEvent("load"), item.click()]);
  await expect(
    page.getByRole("button", { name: /account menu/i }),
  ).not.toHaveClass(/update-ready/);
  await expect(
    page.getByRole("button", { name: /update available/ }),
  ).toHaveCount(0);
  await expect
    .poll(() =>
      page.evaluate(async () => {
        const registration = await navigator.serviceWorker.getRegistration();
        return (
          !!registration &&
          !registration.waiting &&
          registration.active === navigator.serviceWorker.controller
        );
      }),
    )
    .toBe(true);
  expect(await page.evaluate(() => caches.keys())).toEqual(
    expect.arrayContaining([
      expect.stringMatching(/english-learning-shell-.*-test-update$/),
    ]),
  );
  expect(
    await page.evaluate(() => sessionStorage.getItem("pwa-ui-loads")),
  ).toBe("1");
  expect(
    await page.evaluate((key) => localStorage.getItem(key), pendingKey),
  ).toBe("pending-answer-sentinel");
  await page.getByRole("button", { name: /account menu/i }).click();
  await expect(
    page.getByRole("menuitem", { name: "Reload to update" }),
  ).toHaveCount(0);
});

test("real offline launch shows the session card and online recovery silently removes it", async ({
  page,
  request,
}) => {
  await offlineLaunch(page, request);
  await expect(
    page.getByText(
      "Your session is kept on this device. Reconnect to open your decks and send answers.",
    ),
  ).toBeVisible();
  await expect(page.getByText("We'll reconnect automatically.")).toBeVisible();
  await expect(page.locator(".google-signin-container")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: /Continue as guest/ }),
  ).toHaveCount(0);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await settings(request, { networkDown: false });
  await page.context().setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await expect(
    page.getByRole("button", { name: /Account menu for/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "You're offline" }),
  ).toHaveCount(0);
  await expect(page.getByText(/back online/i)).toHaveCount(0);
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("offline card enters the saved guest snapshot and keeps the refresh token", async ({
  page,
  request,
}) => {
  const refresh = await offlineLaunch(page, request);
  const button = page.getByRole("button", { name: "Practice public cards" });
  expect(
    await button.evaluate((element) => element.getBoundingClientRect().height),
  ).toBeGreaterThanOrEqual(44);
  await button.click();
  await expect(page.locator('.swipe--card[aria-hidden="false"]')).toBeVisible({
    timeout: 15000,
  });
  await expect(
    page.getByText("Offline · saved copy from Oct 23, 2026"),
  ).toBeVisible();
  expect(
    await page.evaluate((key) => localStorage.getItem(key), refreshKey),
  ).toBe(refresh);
  await settings(request, { networkDown: false });
  await page.context().setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await expect(page.getByText(/Offline · saved copy/)).toHaveCount(0);
});
