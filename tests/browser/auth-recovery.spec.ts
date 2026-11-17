import { expect, test, type Page } from "@playwright/test";
import {
  apiOrigin,
  authHook,
  fixtureUserId,
  pendingKey,
  pendingMetaKey,
  profileKey,
  refreshKey,
  seedSignedIn,
} from "./auth-fixture";

const strip = (page: Page) => page.getByTestId("session-status");

async function control(
  page: Page,
  refresh_token: string,
  action = "session",
  options: { count?: number; finish?: boolean } = {},
) {
  const response = await page.request.post(
    `${apiOrigin}/__test__/auth/${action}`,
    { data: { refresh_token, ...options } },
  );
  expect(response.status()).toBe(200);
  return response.json();
}

async function currentRefresh(page: Page) {
  const token = await page.evaluate(
    (key) => localStorage.getItem(key),
    refreshKey,
  );
  expect(token).toMatch(/^elr_/);
  if (!token) throw new Error("Fixture requires a current refresh token.");
  return token;
}

async function openReview(page: Page) {
  await seedSignedIn(page);
  await page.goto("./review");
  await expect(page.getByText("resilient", { exact: true })).toBeVisible();
  return currentRefresh(page);
}

async function answerReview(page: Page) {
  await page.locator('.swipe--card[aria-hidden="false"]').click();
  await page.getByRole("button", { name: "Knew it", exact: true }).click();
  const raw = await page.evaluate(
    (key) => localStorage.getItem(key),
    pendingKey,
  );
  expect(raw).not.toBeNull();
  if (!raw) throw new Error("Answer must be saved before submission.");
  const command = JSON.parse(raw);
  expect(command.ownerId).toBe(fixtureUserId("success"));
  expect(command.payload).toEqual({
    items: [
      {
        card_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        decision: "yes",
        expected_version: 1,
      },
    ],
  });
  return { raw, command };
}

async function watchForStrip(page: Page) {
  await expect(strip(page)).toHaveCount(0);
  await page.evaluate(() => {
    document.documentElement.dataset.observedSessionStrip = "false";
    new MutationObserver(() => {
      if (document.querySelector('[data-testid="session-status"]'))
        document.documentElement.dataset.observedSessionStrip = "true";
    }).observe(document.documentElement, { childList: true, subtree: true });
  });
}

async function expectSilent(page: Page) {
  await expect(strip(page)).toHaveCount(0);
  await expect(page.locator("html")).toHaveAttribute(
    "data-observed-session-strip",
    "false",
  );
  await expect(
    page.getByRole("button", { name: /Account menu for/ }),
  ).toBeVisible();
}

test("live access expiry refreshes silently without reloading or showing a session strip", async ({
  page,
}) => {
  const token = await openReview(page);
  const before = await control(page, token);
  await watchForStrip(page);
  await authHook(page, "expire-access");
  await control(page, token, "refresh-barrier");
  const expired = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/v1/decks" &&
      response.status() === 401,
  );
  await page.getByRole("link", { name: "Decks", exact: true }).click();
  expect((await (await expired).json()).error.code).toBe(
    "access_token_expired",
  );
  await expect
    .poll(async () => (await control(page, token)).waiting_refreshes)
    .toBe(1);
  await expectSilent(page);
  await control(page, token, "release-refresh", { finish: true });
  await expect(
    page.getByRole("heading", { name: "English foundations" }),
  ).toBeVisible();
  const after = await control(page, token);
  expect(after.refresh_requests.slice(before.refresh_requests.length)).toEqual([
    { generation: before.refresh_rotations, status: 200 },
  ]);
  expect(after.access_expired - before.access_expired).toBe(1);
  expect(after.refresh_rotations - before.refresh_rotations).toBe(1);
  expect(after.revoked).toBe(false);
  await expectSilent(page);
});

test("review access-expiry retry sends exactly the same pending body and idempotency key", async ({
  page,
}) => {
  const token = await openReview(page);
  const saved = await answerReview(page);
  const before = await control(page, token);
  const requests: { body: string | null; key: string | undefined }[] = [];
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/v1/reviews"
    )
      requests.push({
        body: request.postData(),
        key: request.headers()["idempotency-key"],
      });
  });
  await watchForStrip(page);
  await authHook(page, "expire-access");
  await control(page, token, "refresh-barrier");
  const expired = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/v1/reviews" &&
      response.status() === 401,
  );
  await page
    .getByRole("button", { name: "Submit Results", exact: true })
    .click();
  expect((await (await expired).json()).error.code).toBe(
    "access_token_expired",
  );
  await expect
    .poll(async () => (await control(page, token)).waiting_refreshes)
    .toBe(1);
  expect(
    await page.evaluate((key) => localStorage.getItem(key), pendingKey),
  ).toBe(saved.raw);
  await control(page, token, "release-refresh", { finish: true });
  await expect(
    page.getByRole("heading", { name: "Your review batch is saved!" }),
  ).toBeVisible();
  expect(requests).toEqual([
    {
      body: JSON.stringify(saved.command.payload),
      key: saved.command.idempotencyKey,
    },
    {
      body: JSON.stringify(saved.command.payload),
      key: saved.command.idempotencyKey,
    },
  ]);
  expect(
    await page.evaluate((key) => localStorage.getItem(key), pendingKey),
  ).toBeNull();
  const after = await control(page, token);
  expect(after.refresh_requests.slice(before.refresh_requests.length)).toEqual([
    { generation: before.refresh_rotations, status: 200 },
  ]);
  expect(after.access_expired - before.access_expired).toBe(1);
  expect(after.id).toBe(fixtureUserId("success"));
  await expectSilent(page);
});

test("assistant pre-stream 401 refreshes once and retries unchanged messages without duplicate deltas", async ({
  page,
}) => {
  await seedSignedIn(page);
  await page.goto("./assistant");
  const input = page.getByRole("textbox", { name: "Ask the assistant" });
  await expect(input).toBeEnabled();
  const token = await currentRefresh(page);
  const before = await control(page, token);
  const bodies: (string | null)[] = [];
  const statuses: number[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/v1/assistant/messages/stream")
      bodies.push(request.postData());
  });
  page.on("response", (response) => {
    if (new URL(response.url()).pathname === "/v1/assistant/messages/stream")
      statuses.push(response.status());
  });
  await watchForStrip(page);
  await authHook(page, "expire-access");
  await input.fill("What should I practise?");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.getByText("Recovered assistant reply.", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".conversation .turn")).toHaveCount(1);
  expect(statuses).toEqual([401, 200]);
  expect(bodies).toHaveLength(2);
  expect(bodies[1]).toBe(bodies[0]);
  expect(JSON.parse(bodies[0] ?? "null")).toEqual({
    messages: [{ role: "user", content: "What should I practise?" }],
    capabilities: ["parts.v1"],
  });
  const after = await control(page, token);
  expect(after.refresh_requests.slice(before.refresh_requests.length)).toEqual([
    { generation: before.refresh_rotations, status: 200 },
  ]);
  expect(after.access_expired - before.access_expired).toBe(1);
  await expectSilent(page);
});

for (const width of [1280, 390]) {
  test(`mid-session allowlist 403 retains exact owned pending answers and disables writes at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 800 });
    const token = await openReview(page);
    const saved = await answerReview(page);
    const profile = await page.evaluate(
      (key) => localStorage.getItem(key),
      profileKey,
    );
    const meta = await page.evaluate(
      (key) => localStorage.getItem(key),
      pendingMetaKey,
    );
    const before = await control(page, token);
    let submissions = 0;
    page.on("request", (request) => {
      if (
        request.method() === "POST" &&
        new URL(request.url()).pathname === "/v1/reviews"
      )
        submissions++;
    });
    await authHook(page, "allowlist", false);
    try {
      const denied = page.waitForResponse(
        (response) =>
          new URL(response.url()).pathname === "/v1/reviews" &&
          response.status() === 403,
      );
      await page
        .getByRole("button", { name: "Submit Results", exact: true })
        .click();
      expect((await (await denied).json()).error.code).toBe(
        "account_not_allowed",
      );
      await expect(strip(page)).toHaveAttribute("role", "alert");
      await expect(strip(page)).toContainText("browser-test@example.com");
      await expect(strip(page)).toContainText("can't open private decks");
      await expect(
        strip(page).getByRole("button", { name: "Sign in again", exact: true }),
      ).toBeVisible();
      await expect(
        strip(page).getByRole("button", {
          name: "Continue as guest",
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: /Retry submission|Submit Results/ }),
      ).toBeDisabled();
      await expect(page).toHaveURL(/\/review$/);
      expect(
        await page.evaluate((key) => localStorage.getItem(key), pendingKey),
      ).toBe(saved.raw);
      expect(
        await page.evaluate((key) => localStorage.getItem(key), pendingMetaKey),
      ).toBe(meta);
      expect(
        await page.evaluate((key) => localStorage.getItem(key), profileKey),
      ).toBe(profile);
      expect(
        await page.evaluate((key) => localStorage.getItem(key), refreshKey),
      ).toBeNull();
      expect(
        await page.evaluate(() =>
          sessionStorage.getItem("learning_guest_session"),
        ),
      ).toBeNull();
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBeLessThanOrEqual(width);
      const after = await control(page, token);
      expect(after.account_denied - before.account_denied).toBe(1);
      expect(after.refresh_requests).toEqual(before.refresh_requests);
      expect(after.revoked).toBe(true);
      expect(submissions).toBe(1);
    } finally {
      const restored = await page.request.post(
        `${apiOrigin}/__test__/auth/allowlist`,
        {
          data: { refresh_token: token, allowed: true },
        },
      );
      expect(restored.status()).toBe(200);
    }
  });
}

for (const webLocks of [true, false]) {
  test(`overlapping two-tab refresh ${webLocks ? "with Web Locks serializes" : "without Web Locks retries one deterministic 409"} without forking the family`, async ({
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
    const token = await currentRefresh(page);
    const before = await control(page, token);
    for (const tab of [page, second]) {
      await tab.addInitScript(
        ({ webLocks }) => {
          if (!webLocks) {
            Object.defineProperty(navigator, "locks", {
              value: undefined,
              configurable: true,
            });
            return;
          }
          const original = navigator.locks.request;
          Object.defineProperty(navigator.locks, "request", {
            configurable: true,
            value: (...args: unknown[]) => {
              if (args[0] === "el_auth_refresh_v1")
                Reflect.set(
                  window,
                  "__fixtureRefreshLockRequests",
                  Number(
                    Reflect.get(window, "__fixtureRefreshLockRequests") ?? 0,
                  ) + 1,
                );
              return Reflect.apply(original, navigator.locks, args);
            },
          });
        },
        { webLocks },
      );
    }
    await control(page, token, "refresh-barrier");
    // Wait for new documents before evaluating lock instrumentation; API replies stay gated.
    await Promise.all([
      page.reload({ waitUntil: "domcontentloaded" }),
      second.reload({ waitUntil: "domcontentloaded" }),
    ]);
    if (webLocks) {
      for (const tab of [page, second])
        await expect
          .poll(() =>
            tab.evaluate(() =>
              Reflect.get(window, "__fixtureRefreshLockRequests"),
            ),
          )
          .toBe(1);
    } else {
      for (const tab of [page, second])
        await expect
          .poll(() => tab.evaluate(() => navigator.locks))
          .toBeUndefined();
    }
    await expect
      .poll(async () => (await control(page, token)).waiting_refreshes)
      .toBe(webLocks ? 1 : 2);
    const blocked = await control(page, token);
    expect(blocked.refresh_rotations).toBe(before.refresh_rotations);
    expect(
      blocked.refresh_requests.slice(before.refresh_requests.length),
    ).toEqual(
      Array.from({ length: webLocks ? 1 : 2 }, () => ({
        generation: before.refresh_rotations,
        status: null,
      })),
    );
    await control(page, token, "release-refresh", { finish: webLocks });
    if (!webLocks) {
      // Let the winner persist R1 before delivering the loser's R0 409.
      await expect
        .poll(() =>
          page.evaluate((key) => localStorage.getItem(key), refreshKey),
        )
        .not.toBe(token);
      const once = await control(page, token);
      expect(once.refresh_rotations - before.refresh_rotations).toBe(1);
      expect(
        once.refresh_requests.slice(before.refresh_requests.length),
      ).toEqual([
        { generation: before.refresh_rotations, status: 200 },
        { generation: before.refresh_rotations, status: null },
      ]);
      await control(page, token, "release-refresh", { finish: true });
    }
    for (const tab of [page, second]) {
      await expect(
        tab.getByRole("heading", { name: "English foundations" }),
      ).toBeVisible();
      await expect(
        tab.getByRole("button", { name: /Account menu for/ }),
      ).toBeVisible();
      await expect(strip(tab)).toHaveCount(0);
      expect(
        await tab.evaluate(
          (key) => JSON.parse(localStorage.getItem(key) ?? "null").id,
          profileKey,
        ),
      ).toBe(fixtureUserId("success"));
    }
    const after = await control(page, token);
    // Each tab needs its own memory-only access token, so R1 also rotates once.
    expect(
      after.refresh_requests.slice(before.refresh_requests.length),
    ).toEqual([
      { generation: before.refresh_rotations, status: 200 },
      ...(!webLocks
        ? [{ generation: before.refresh_rotations, status: 409 }]
        : []),
      { generation: before.refresh_rotations + 1, status: 200 },
    ]);
    expect(after.refresh_rotations - before.refresh_rotations).toBe(2);
    expect(after.revoked).toBe(false);
    expect(await currentRefresh(second)).toBe(await currentRefresh(page));
    await second.close();
  });
}
