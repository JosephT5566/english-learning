import { expect, test, type Page } from "@playwright/test";
import {
  apiOrigin,
  authHook,
  fixtureUserId,
  installMockGis,
  pendingKey,
  profileKey,
  refreshKey,
  seedSignedIn,
} from "./auth-fixture";

const strip = (page: Page) => page.getByTestId("session-status");

async function openPrivateReview(page: Page) {
  await seedSignedIn(page);
  await page.goto("./review");
  await expect(page.getByText("resilient", { exact: true })).toBeVisible();
}

async function createPendingThenExpire(page: Page) {
  const commands: { body: string | null; key: string | undefined }[] = [];
  let first = true;
  await page.route("**/v1/reviews", async (route) => {
    commands.push({
      body: route.request().postData(),
      key: route.request().headers()["idempotency-key"],
    });
    if (first) {
      first = false;
      return route.fulfill({
        status: 503,
        json: {
          error: {
            code: "database_unavailable",
            message: "Synthetic interrupted submission.",
            retryable: true,
            request_id: "99999999-9999-4999-8999-999999999999",
          },
        },
      });
    }
    return route.continue();
  });
  await openPrivateReview(page);
  await page.locator('.swipe--card[aria-hidden="false"]').click();
  await page.getByRole("button", { name: "Knew it", exact: true }).click();
  await page
    .getByRole("button", { name: "Submit Results", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Review not confirmed" }),
  ).toBeVisible();
  const pending = await page.evaluate(
    (key) => localStorage.getItem(key),
    pendingKey,
  );
  expect(pending).not.toBeNull();
  const profile = await page.evaluate(
    (key) => localStorage.getItem(key),
    profileKey,
  );
  await authHook(page, "revoke");
  await page
    .getByRole("button", { name: "Retry submission", exact: true })
    .click();
  await expect(strip(page)).toContainText("Session ended.");
  return { pending, profile, commands };
}

async function chooseGuest(page: Page) {
  await strip(page)
    .getByRole("button", { name: "Continue as guest", exact: true })
    .click();
  await expect(page).toHaveURL(/\/review$/);
  await expect(page).toHaveTitle("Guest review - English Learning");
}

async function signInAgain(page: Page) {
  await strip(page)
    .getByRole("button", { name: /Sign in again|Sign in to send/ })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Sign in with Google" })
    .click();
}

test("reload restores the app session by rotating refresh without persisting Google or access tokens", async ({
  page,
}) => {
  const requests: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/v1/auth/refresh")
      requests.push(request.method());
  });
  await openPrivateReview(page);
  const before = await page.evaluate(
    (key) => localStorage.getItem(key),
    refreshKey,
  );
  await page.reload();
  await expect(page.getByText("resilient", { exact: true })).toBeVisible();
  const after = await page.evaluate(
    (key) => localStorage.getItem(key),
    refreshKey,
  );
  expect(after).toMatch(/^elr_/);
  expect(after).not.toBe(before);
  expect(requests.length).toBeGreaterThanOrEqual(2);
  const storage = await page.evaluate(() => ({ ...localStorage }));
  expect(Object.values(storage).some((value) => value.startsWith("ela_"))).toBe(
    false,
  );
  expect(storage.gid_id_token).toBeUndefined();
  expect(storage.gid_exp).toBeUndefined();
  expect(JSON.parse(storage.el_auth_profile_v1).id).toBe(
    fixtureUserId("success"),
  );
  await expect(strip(page)).toHaveCount(0);
});

test("two tabs refreshing at once stay signed in with one rotating family", async ({
  page,
  context,
}) => {
  await seedSignedIn(page);
  await page.goto("./decks?language=en");
  await expect(
    page.getByRole("heading", { name: "English foundations" }),
  ).toBeVisible();
  const second = await context.newPage();
  await second.goto("./decks?language=en");
  await expect(
    second.getByRole("heading", { name: "English foundations" }),
  ).toBeVisible();
  await Promise.all([page.reload(), second.reload()]);
  for (const tab of [page, second]) {
    await expect(
      tab.getByRole("heading", { name: "English foundations" }),
    ).toBeVisible();
    await expect(
      tab.getByRole("button", { name: /Account menu for/ }),
    ).toBeVisible();
    await expect(strip(tab)).toHaveCount(0);
  }
  const token = await page.evaluate(
    (key) => localStorage.getItem(key),
    refreshKey,
  );
  const session = await page.request.post(
    `${apiOrigin}/__test__/auth/session`,
    { data: { refresh_token: token } },
  );
  expect(session.status()).toBe(200);
  expect((await session.json()).revoked).toBe(false);
});

test("expired session shows the amber recovery bar and disables private writes", async ({
  page,
}) => {
  await installMockGis(page);
  await createPendingThenExpire(page);
  await expect(strip(page)).toContainText("1 answers are saved here");
  await expect(
    strip(page).getByRole("button", { name: "Sign in again", exact: true }),
  ).toBeVisible();
  await expect(
    strip(page).getByRole("button", { name: "Continue as guest", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Retry submission|Submit Results/ }),
  ).toBeDisabled();
  await expect(page).toHaveURL(/\/review$/);
});

test("Continue as guest keeps exact pending answers and profile with a non-dismissible Sign in to send bar", async ({
  page,
}) => {
  await installMockGis(page);
  const saved = await createPendingThenExpire(page);
  await chooseGuest(page);
  expect(
    await page.evaluate((key) => localStorage.getItem(key), pendingKey),
  ).toBe(saved.pending);
  expect(
    await page.evaluate((key) => localStorage.getItem(key), profileKey),
  ).toBe(saved.profile);
  expect(
    await page.evaluate((key) => localStorage.getItem(key), refreshKey),
  ).toBeNull();
  await expect(strip(page)).toContainText("Guest practice.");
  await expect(strip(page)).toContainText(
    "1 answers for browser-test@example.com stay on this device",
  );
  await expect(
    strip(page).getByRole("button", { name: "Sign in to send", exact: true }),
  ).toBeVisible();
  await expect(
    strip(page).getByRole("button", { name: /Dismiss/ }),
  ).toHaveCount(0);
  await page.reload();
  await expect(
    strip(page).getByRole("button", { name: "Sign in to send", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate((key) => localStorage.getItem(key), pendingKey),
  ).toBe(saved.pending);
});

test("same internal user signing back in from guest sends the exact pending command once", async ({
  page,
}) => {
  await installMockGis(page);
  const saved = await createPendingThenExpire(page);
  await chooseGuest(page);
  const before = saved.commands.length;
  await signInAgain(page);
  await expect(strip(page)).toContainText("Your 1 saved answers were sent.");
  expect(
    await page.evaluate((key) => localStorage.getItem(key), pendingKey),
  ).toBeNull();
  expect(saved.commands).toHaveLength(before + 1);
  expect(saved.commands.at(-1)).toEqual(saved.commands[0]);
  expect(
    await page.evaluate(() => sessionStorage.getItem("learning_guest_session")),
  ).toBeNull();
});

test("different internal user clears pending answers and reports the removed count", async ({
  page,
}) => {
  await installMockGis(page, "other-account");
  const saved = await createPendingThenExpire(page);
  await chooseGuest(page);
  const before = saved.commands.length;
  await signInAgain(page);
  await expect(strip(page)).toContainText("1 unsent answers");
  await expect(strip(page)).toContainText("were removed.");
  expect(
    await page.evaluate((key) => localStorage.getItem(key), pendingKey),
  ).toBeNull();
  expect(saved.commands).toHaveLength(before);
  const profile = await page.evaluate(
    (key) => JSON.parse(localStorage.getItem(key) ?? "null"),
    profileKey,
  );
  expect(profile.id).toBe(fixtureUserId("other-account"));
});

test("sign-out in another tab keeps the current page and offers explicit guest practice", async ({
  page,
  context,
}) => {
  await openPrivateReview(page);
  const second = await context.newPage();
  await second.goto("./decks?language=en");
  await expect(
    second.getByRole("button", { name: /Account menu for/ }),
  ).toBeVisible();
  await second.getByRole("button", { name: /Account menu for/ }).click();
  await second.getByRole("menuitem", { name: "Sign out", exact: true }).click();
  await expect(strip(page)).toContainText("You signed out in another tab.");
  await expect(page).toHaveURL(/\/review$/);
  await expect(
    strip(page).getByRole("button", { name: "Continue as guest", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => sessionStorage.getItem("learning_guest_session")),
  ).toBeNull();
});

test("allowlist rejection displays the rejected email and keeps the guest choice explicit", async ({
  page,
}) => {
  await installMockGis(page, "success", "not-allowed@example.invalid");
  await page.goto("./");
  await page
    .getByRole("button", { name: "Sign in with Google", exact: true })
    .click();
  await expect(strip(page)).toContainText("not-allowed@example.invalid");
  await expect(strip(page)).toContainText("can't open private decks");
  await expect(
    strip(page).getByRole("button", { name: "Continue as guest", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => sessionStorage.getItem("learning_guest_session")),
  ).toBeNull();
});

test("guest header has Sign in and menu-only time remaining; Leave guest practice preserves pending", async ({
  page,
}) => {
  await installMockGis(page);
  const saved = await createPendingThenExpire(page);
  await chooseGuest(page);
  await expect(
    page
      .locator("header")
      .getByRole("button", { name: "Sign in", exact: true }),
  ).toBeVisible();
  await expect(page.locator("header")).not.toContainText(/ends in/);
  await page.getByRole("button", { name: "Guest account menu" }).click();
  await expect(page.getByRole("menu")).toContainText(/ends in \d+ min/);
  await page
    .getByRole("menuitem", { name: "Leave guest practice", exact: true })
    .click();
  await expect(page).toHaveURL(/\/$/);
  expect(
    await page.evaluate(() => sessionStorage.getItem("learning_guest_session")),
  ).toBeNull();
  expect(
    await page.evaluate((key) => localStorage.getItem(key), pendingKey),
  ).toBe(saved.pending);
});

test("legacy Google storage is removed and Session ended appears once without auto-dismiss", async ({
  page,
}) => {
  await page.clock.install();
  await page.addInitScript(() => {
    if (sessionStorage.getItem("fixture-legacy-once")) return;
    sessionStorage.setItem("fixture-legacy-once", "1");
    localStorage.setItem("gid_id_token", "legacy-synthetic-token");
    localStorage.setItem("gid_exp", "9999999999");
  });
  await page.goto("./");
  await expect(strip(page)).toContainText("Session ended.");
  await page.clock.fastForward(60_000);
  await expect(strip(page)).toContainText("Session ended.");
  expect(
    await page.evaluate(() => [
      localStorage.getItem("gid_id_token"),
      localStorage.getItem("gid_exp"),
    ]),
  ).toEqual([null, null]);
  await page.reload();
  await expect(strip(page)).toHaveCount(0);
});

test("pending 24-hour expiry reports once and never extends the saved deadline", async ({
  page,
}) => {
  const expiry = Date.now() - 1;
  await page.addInitScript(
    ({ expiry, ownerId }) => {
      if (sessionStorage.getItem("fixture-expired-once")) return;
      sessionStorage.setItem("fixture-expired-once", "1");
      localStorage.setItem(
        "pending_review_submission_v2",
        JSON.stringify({
          version: 2,
          ownerId,
          idempotencyKey: "11111111-1111-4111-8111-111111111111",
          createdAt: expiry - 86_400_000,
          expiresAt: expiry,
          payload: {
            items: [
              {
                card_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                decision: "yes",
                expected_version: 1,
              },
            ],
          },
        }),
      );
      localStorage.setItem(
        "el_review_pending_meta_v1",
        JSON.stringify({
          count: 1,
          ownerId,
          email: "browser-test@example.com",
          expiresAt: expiry,
        }),
      );
    },
    { expiry, ownerId: fixtureUserId("success") },
  );
  await page.goto("./");
  await expect(strip(page)).toContainText(
    "Saved answers expired and were not sent",
  );
  expect(
    await page.evaluate((key) => localStorage.getItem(key), pendingKey),
  ).toBeNull();
  await page.reload();
  await expect(
    page.getByText("Saved answers expired and were not sent", { exact: true }),
  ).toHaveCount(0);
});

test("sign-out warns only when pending answers exist and reports their count", async ({
  page,
}) => {
  await openPrivateReview(page);
  await page.locator('.swipe--card[aria-hidden="false"]').click();
  await page.getByRole("button", { name: "Knew it", exact: true }).click();
  await page.getByRole("button", { name: /Account menu for/ }).click();
  await expect(
    page.getByRole("menuitem", { name: "Switch account", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("menuitem", { name: "Sign out", exact: true }).click();
  const warning = page.getByRole("dialog", { name: "Sign out?", exact: true });
  await expect(warning).toContainText("1");
  await expect(warning).toContainText(/different account/);
  await warning.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(strip(page)).toContainText("You signed out on this device.");
  expect(
    await page.evaluate((key) => localStorage.getItem(key), pendingKey),
  ).not.toBeNull();
});

test("mock Google script loads and GIS button exchanges once without persisting the credential", async ({
  page,
}) => {
  await installMockGis(page);
  const exchanges: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/v1/auth/session")
      exchanges.push(request.postData() ?? "");
  });
  await page.goto("./");
  await expect
    .poll(() =>
      page.evaluate(() => Reflect.get(window, "__mockGisScriptLoaded")),
    )
    .toBe(true);
  await page
    .getByRole("button", { name: "Sign in with Google", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: /Account menu for/ }),
  ).toBeVisible();
  expect(exchanges).toHaveLength(1);
  const credential = JSON.parse(exchanges[0]).credential;
  expect(
    JSON.parse(
      atob(credential.split(".")[1].replaceAll("-", "+").replaceAll("_", "/")),
    ).sub,
  ).toBe("browser-test-success");
  const values = await page.evaluate(() => Object.values({ ...localStorage }));
  expect(
    values.some(
      (value) => value.includes("test-signature") || value.startsWith("ela_"),
    ),
  ).toBe(false);
});
