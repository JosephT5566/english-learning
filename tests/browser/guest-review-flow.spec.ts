import { expect, test, type Page } from "@playwright/test";

let root = "";
let guest = "/review";
test.beforeEach(({ page, baseURL }, testInfo) => {
  root = new URL(
    baseURL ?? testInfo.project.use.baseURL ?? "http://127.0.0.1:4173/",
  ).pathname.replace(/\/$/, "");
  guest = `${root}/review`;
  page.on("pageerror", (error) => {
    throw error;
  });
});
const pending = '{"sentinel":"private pending bytes"}';
const daily = "private-daily-sentinel";
const publicPath = "**/v1/public/review-cards";

async function seed(page: Page, signedIn = false) {
  await page.addInitScript(
    ({ pending, daily, signedIn }) => {
      localStorage.setItem("pending_review_submission_v1", pending);
      localStorage.setItem("isTestedToday", daily);
      if (signedIn) {
        const exp = Math.floor(Date.now() / 1000) + 3600;
        const token = `e30.${btoa(JSON.stringify({ sub: "browser-test-empty", exp }))}.test`;
        localStorage.setItem("gid_id_token", token);
        localStorage.setItem("gid_exp", String(exp));
      }
    },
    { pending, daily, signedIn },
  );
}

async function enterGuest(page: Page) {
  await page.goto(`${root}/`);
  await page
    .getByRole("button", { name: "Continue as guest", exact: true })
    .click();
  await expect(page).toHaveURL(new RegExp(`${root}/review$`));
}

async function answerBatch(page: Page) {
  for (let i = 0; i < 2; i++) {
    const answer = page.getByRole("button", { name: "Knew it", exact: true });
    await expect(answer).toBeDisabled();
    const active = page.locator('.swipe--card[aria-hidden="false"]');
    await expect(async () => {
      await active.press("Enter");
      await expect(active).toHaveAttribute("aria-expanded", "true", {
        timeout: 100,
      });
    }).toPass({ intervals: [200], timeout: 3000 });
    await expect(answer).toBeEnabled();
    await answer.click();
  }
  await expect(
    page.getByRole("button", { name: "Practice again" }),
  ).toBeVisible();
}

for (const width of [1280, 390]) {
  test(`guest temporary batch preserves private state and uses public GET only at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 850 });
    await seed(page);
    await page.context().addCookies([
      {
        name: "private_cookie",
        value: "do-not-send",
        url: "http://127.0.0.1:8001",
      },
    ]);
    const requests: import("@playwright/test").Request[] = [];
    page.on("request", (request) => {
      if (
        request.url().includes("/v1/") ||
        request.url().includes("script.google.com")
      )
        requests.push(request);
    });
    await enterGuest(page);
    await expect(
      page.getByText("Progress is not saved.", { exact: false }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("link", { name: "Guest review", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Decks", exact: true }),
    ).toHaveCount(0);
    await answerBatch(page);
    await page.waitForTimeout(1100);
    expect(requests).toHaveLength(1);
    await page.getByRole("button", { name: "Practice again" }).dblclick();
    await expect(
      page.getByRole("button", { name: "Knew it", exact: true }),
    ).toBeVisible();
    expect(requests).toHaveLength(2);
    for (const request of requests) {
      expect(new URL(request.url()).pathname).toBe("/v1/public/review-cards");
      expect(request.method()).toBe("GET");
      const headers = await request.allHeaders();
      expect(headers.authorization).toBeUndefined();
      expect(headers.cookie).toBeUndefined();
    }
    expect(
      await page.evaluate(() => [
        localStorage.getItem("pending_review_submission_v1"),
        localStorage.getItem("isTestedToday"),
      ]),
    ).toEqual([pending, daily]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  });
}

for (const status of [429, 503]) {
  test(`${status} counts down then requires a manual retry`, async ({
    page,
  }) => {
    let calls = 0;
    await page.route(publicPath, (route) => {
      calls++;
      return route.fulfill({
        status,
        headers: { "Retry-After": "1" },
        json: {
          error: {
            code: status === 429 ? "rate_limited" : "public_review_busy",
            message: "Please wait.",
            retryable: true,
            request_id: "test",
          },
        },
      });
    });
    await enterGuest(page);
    await expect(
      page.getByRole("button", { name: "Try again in 1s" }),
    ).toBeDisabled();
    await expect(
      page.getByRole("button", { name: "Try again", exact: true }),
    ).toBeEnabled();
    await page.waitForTimeout(300);
    expect(calls).toBe(1);
    await page.getByRole("button", { name: "Try again", exact: true }).click();
    expect(calls).toBe(2);
  });
}

test("empty and network errors have distinct manual recovery", async ({
  page,
}) => {
  await page.route(publicPath, (route) => route.abort());
  await enterGuest(page);
  await expect(
    page.getByRole("heading", { name: "Review unavailable" }),
  ).toBeVisible();
  await page.unroute(publicPath);
  await page.route(publicPath, (route) =>
    route.fulfill({ json: { items: [] } }),
  );
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "No public cards available" }),
  ).toBeVisible();
});

test("legacy guest route requires explicit choice and signed-in users get private review", async ({
  page,
}) => {
  await page.goto(`${root}/review/guest`);
  await expect(page).toHaveURL(`http://127.0.0.1:4173${root}/`);
  await seed(page, true);
  const publicCalls: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/v1/public/")) publicCalls.push(request.url());
  });
  await page.goto(`${root}/review/guest`);
  await expect(page).toHaveURL(`http://127.0.0.1:4173${root}/review`);
  await expect(
    page.getByRole("heading", {
      name: "We don't have any cards for you today.",
    }),
  ).toBeVisible();
  expect(publicCalls).toEqual([]);
});

test("private direct routes remain protected and do not fetch private APIs", async ({
  page,
}) => {
  const reads: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/v1/")) reads.push(request.url());
  });
  for (const route of [
    "/review",
    "/review/other",
    "/decks",
    "/decks/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "/cards/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "/search",
  ]) {
    await page.goto(`${root}${route}`);
    await expect(page).toHaveURL(`http://127.0.0.1:4173${root}/`);
  }
  expect(reads).toEqual([]);
});

test("guest completion is not restored into a later private review", async ({
  page,
}) => {
  await enterGuest(page);
  await answerBatch(page);
  await page.evaluate(() => {
    const exp = Math.floor(Date.now() / 1000) + 3600;
    localStorage.setItem(
      "gid_id_token",
      `e30.${btoa(JSON.stringify({ sub: "browser-test-empty", exp }))}.test`,
    );
    localStorage.setItem("gid_exp", String(exp));
  });
  const mutations: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST") mutations.push(request.url());
  });
  await page.goto(`${root}/review`);
  await expect(
    page.getByRole("heading", {
      name: "We don't have any cards for you today.",
    }),
  ).toBeVisible();
  expect(mutations).toEqual([]);
  expect(
    await page.evaluate(() => localStorage.getItem("isTestedToday")),
  ).toBeNull();
});

test("navigating away cancels the pending guest session", async ({ page }) => {
  let calls = 0;
  await page.route(publicPath, async (route) => {
    calls++;
    await new Promise((resolve) => setTimeout(resolve, 400));
    await route.fulfill({ json: { items: [] } }).catch(() => {});
  });
  await enterGuest(page);
  await expect(page.getByText("Loading cards...")).toBeVisible();
  await page.getByRole("link", { name: "Home", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Continue as guest", exact: true }),
  ).toBeVisible();
  await page.waitForTimeout(600);
  expect(calls).toBe(1);
  await expect(page.getByText("No public cards available")).toHaveCount(0);
});

test("a later authenticated submission contains only its newly answered owned card", async ({
  page,
}) => {
  await enterGuest(page);
  await answerBatch(page);
  await page.evaluate(() => {
    const exp = Math.floor(Date.now() / 1000) + 3600;
    localStorage.setItem(
      "gid_id_token",
      `e30.${btoa(JSON.stringify({ sub: "browser-test-success", exp }))}.test`,
    );
    localStorage.setItem("gid_exp", String(exp));
  });
  await page.goto(`${root}/review`);
  await expect(page.getByText("resilient", { exact: true })).toBeVisible();
  await page.locator(".swipe--card").click();
  await page.getByRole("button", { name: "Forgot", exact: true }).click();
  const submitted = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/v1/reviews",
  );
  await page
    .getByRole("button", { name: "Submit Results", exact: true })
    .click();
  expect((await submitted).postDataJSON()).toEqual({
    items: [
      {
        card_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        decision: "no",
        expected_version: 1,
      },
    ],
  });
  await expect(
    page.getByRole("heading", { name: "You've completed today's review!" }),
  ).toBeVisible();
});

test("explicit guest choice survives reload, but is isolated from a fresh tab", async ({
  page,
  context,
}) => {
  await page.goto(guest);
  await expect(page).toHaveURL(`http://127.0.0.1:4173${root}/`);
  await enterGuest(page);
  await answerBatch(page);
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Knew it", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Practice again" }),
  ).toHaveCount(0);
  const otherTab = await context.newPage();
  await otherTab.goto(guest);
  await expect(otherTab).toHaveURL(`http://127.0.0.1:4173${root}/`);
  await otherTab.close();
  await page.close();
  const laterTab = await context.newPage();
  await laterTab.goto(guest);
  await expect(laterTab).toHaveURL(`http://127.0.0.1:4173${root}/`);
  await laterTab.close();
});

test("corrupted stored credentials do not block explicit guest choice", async ({
  page,
}) => {
  await page.addInitScript(() => {
    localStorage.setItem("gid_id_token", "not-a-jwt");
    localStorage.setItem(
      "gid_exp",
      String(Math.floor(Date.now() / 1000) + 3600),
    );
  });
  await enterGuest(page);
  await expect(page).toHaveTitle("Guest review - English Learning");
  await expect(
    page.getByRole("button", { name: "Knew it", exact: true }),
  ).toBeDisabled();
  expect(
    await page.evaluate(
      () =>
        Number(sessionStorage.getItem("learning_guest_session")) > Date.now(),
    ),
  ).toBe(true);
});

for (const width of [1280, 390]) {
  test(`guest expires after 30 minutes without extending on activity at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 850 });
    await seed(page);
    await page.clock.install();
    const requests: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes("/v1/")) requests.push(request.url());
    });
    await enterGuest(page);
    const deadline = await page.evaluate(() =>
      sessionStorage.getItem("learning_guest_session"),
    );
    await answerBatch(page);
    await page.getByRole("button", { name: "Practice again" }).click();
    await expect(
      page.getByRole("button", { name: "Knew it", exact: true }),
    ).toBeVisible();
    await page.clock.setSystemTime(Number(deadline) - 60_000);
    await page.reload();
    await expect(
      page.getByRole("navigation", { name: "Primary navigation" }),
    ).toBeVisible();
    expect(
      await page.evaluate(() =>
        sessionStorage.getItem("learning_guest_session"),
      ),
    ).toBe(deadline);
    await expect(
      page.getByRole("button", { name: "Knew it", exact: true }),
    ).toBeVisible();
    const count = requests.length;
    await page.clock.setSystemTime(Number(deadline));
    await page.clock.runFor(1000);
    await expect(page).toHaveURL(`http://127.0.0.1:4173${root}/`);
    await expect(page.locator(".swipe--card")).toHaveCount(0);
    await expect(
      page.getByRole("navigation", { name: "Primary navigation" }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Guest account menu" }),
    ).toBeVisible();
    expect(
      await page.evaluate(() =>
        sessionStorage.getItem("learning_guest_session"),
      ),
    ).toBeNull();
    expect(
      await page.evaluate(() => [
        localStorage.getItem("pending_review_submission_v1"),
        localStorage.getItem("isTestedToday"),
      ]),
    ).toEqual([pending, daily]);
    await page.goto(guest);
    await expect(page).toHaveURL(`http://127.0.0.1:4173${root}/`);
    expect(requests.length).toBe(count);
    await enterGuest(page);
    await expect(
      page.getByRole("navigation", { name: "Primary navigation" }),
    ).toBeVisible();
    expect(
      await page.evaluate(() =>
        Number(sessionStorage.getItem("learning_guest_session")),
      ),
    ).toBeGreaterThan(Number(deadline));
  });
}

test("expired guest focus cancels an in-flight public request without another API call", async ({
  page,
}) => {
  await seed(page);
  await page.clock.install();
  let calls = 0;
  let cancelled = false;
  page.on("requestfailed", (request) => {
    if (request.url().includes("/v1/public/review-cards")) cancelled = true;
  });
  await page.route(publicPath, async (route) => {
    calls++;
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await route.fulfill({ json: { items: [] } }).catch(() => {});
  });
  await enterGuest(page);
  await expect(page.getByText("Loading cards...")).toBeVisible();
  const deadline = await page.evaluate(() =>
    Number(sessionStorage.getItem("learning_guest_session")),
  );
  await page.clock.setSystemTime(deadline);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page).toHaveURL(`http://127.0.0.1:4173${root}/`);
  await expect.poll(() => cancelled).toBe(true);
  expect(calls).toBe(1);
  await expect(page.getByText("No public cards available")).toHaveCount(0);
});

for (const marker of ["1", "bad-deadline", "expired"]) {
  test(`invalid guest marker ${marker} cannot hydrate review`, async ({
    page,
  }) => {
    await page.addInitScript(
      (marker) =>
        sessionStorage.setItem(
          "learning_guest_session",
          marker === "expired" ? String(Date.now() - 1) : marker,
        ),
      marker,
    );
    const requests: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes("/v1/")) requests.push(request.url());
    });
    await page.goto(guest);
    await expect(page).toHaveURL(`http://127.0.0.1:4173${root}/`);
    await expect(
      page.getByRole("navigation", { name: "Primary navigation" }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Guest account menu" }),
    ).toBeVisible();
    expect(
      await page.evaluate(() =>
        sessionStorage.getItem("learning_guest_session"),
      ),
    ).toBeNull();
    expect(requests).toEqual([]);
  });
}
