import { expect, test } from "@playwright/test";

async function answerOneCard(page: import("@playwright/test").Page) {
  const knewIt = page.getByRole("button", { name: "Knew it", exact: true });
  await expect(knewIt).toBeDisabled();
  await page.locator(".swipe--card").click();
  await expect(knewIt).toBeEnabled();
  await knewIt.click();
  await page
    .getByRole("button", { name: "Submit Results", exact: true })
    .click();
}

for (const width of [1280, 390]) {
  test(`a saved ten-card batch records account activity without claiming an empty backlog at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 850 });
    await page.route("**/v1/reviews/due?*", async (route) => {
      const response = await route.fetch();
      const data = await response.json();
      await route.fulfill({
        response,
        json: {
          ...data,
          items: Array.from({ length: 10 }, (_, index) => ({
            ...data.items[0],
            id: `aaaaaaaa-aaaa-4aaa-8aaa-${String(index + 1).padStart(12, "0")}`,
          })),
          next_cursor: "more-due-cards",
        },
      });
    });
    await page.goto("/__test__/auth/success");
    for (let index = 0; index < 10; index++) {
      const active = page.locator('.swipe--card[aria-hidden="false"]');
      await expect(active).toBeVisible();
      await expect(async () => {
        await active.press("Enter");
        await expect(active).toHaveAttribute("aria-expanded", "true", {
          timeout: 100,
        });
      }).toPass({ intervals: [200], timeout: 3000 });
      const answer = page.getByRole("button", { name: "Knew it", exact: true });
      await expect(answer).toBeEnabled();
      await answer.click();
    }
    await page
      .getByRole("button", { name: "Submit Results", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Your review batch is saved!" }),
    ).toBeVisible();
    await expect(
      page.getByText("10 answers were saved.", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText(/More cards may still be due/)).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath(`activity-saved-${width}.png`),
      fullPage: true,
    });
    const date = await page.evaluate(() => {
      const now = new Date();
      return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
    });
    expect(
      await page.evaluate(() =>
        localStorage.getItem("review_practiced_on_v1:browser-test-success"),
      ),
    ).toBe(date);
    expect(
      await page.evaluate(() => localStorage.getItem("isTestedToday")),
    ).toBeNull();
    await page.getByRole("link", { name: "Back home", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "You've practiced today" }),
    ).toBeVisible();
    await expect(page).toHaveTitle("Practiced today — English Learning");
    await expect(page.getByText(/More cards may still be due/)).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath(`activity-home-${width}.png`),
      fullPage: true,
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.evaluate(() => {
      const exp = Math.floor(Date.now() / 1000) + 3600;
      localStorage.setItem(
        "gid_id_token",
        `e30.${btoa(JSON.stringify({ sub: "browser-test-other-account", exp }))}.test`,
      );
      localStorage.setItem("gid_exp", String(exp));
      window.dispatchEvent(
        new StorageEvent("storage", { key: "gid_id_token" }),
      );
    });
    await expect(
      page.getByRole("link", { name: /Start today.s review/ }),
    ).toBeVisible();
    await expect(page).toHaveTitle("Daily review — English Learning");
  });
}

test("activity storage failure cannot turn a validated save into an unconfirmed review", async ({
  page,
}) => {
  await page.goto("/__test__/auth/success");
  await expect(page.getByText("resilient", { exact: true })).toBeVisible();
  await page.evaluate(() => {
    const setItem = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key, value) {
      if (
        key.startsWith("review_practiced_on_v1:") ||
        key === "isTestedToday"
      ) {
        throw new DOMException("Storage full", "QuotaExceededError");
      }
      setItem.call(this, key, value);
    };
  });
  await answerOneCard(page);
  await expect(
    page.getByRole("heading", { name: "Your review batch is saved!" }),
  ).toBeVisible();
  await expect(
    page.getByText("1 answers were saved.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Review not confirmed" }),
  ).toHaveCount(0);
  expect(
    await page.evaluate(() =>
      localStorage.getItem("review_practiced_on_v1:browser-test-success"),
    ),
  ).toBeNull();
});

test("the review card stack receives usable viewport height", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 700 });
  await page.goto("/__test__/auth/retryable");
  await expect(page.getByText("resilient", { exact: true })).toBeVisible();

  const cardsBox = await page.locator(".swipe--cards").boundingBox();
  const cardBox = await page.locator(".swipe--card").boundingBox();

  expect(cardsBox?.height).toBeGreaterThan(300);
  expect(cardBox?.height).toBeGreaterThan(300);
});

test("an unconfirmed submission retries the identical command and succeeds once", async ({
  page,
}) => {
  const commands: { body: unknown; key: string | undefined }[] = [];
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/v1/reviews"
    ) {
      commands.push({
        body: request.postDataJSON(),
        key: request.headers()["idempotency-key"],
      });
    }
  });
  await page.goto("/__test__/auth/retryable");
  await expect(page.getByText("resilient", { exact: true })).toBeVisible();
  await answerOneCard(page);

  await expect(
    page.getByRole("heading", { name: "Review not confirmed" }),
  ).toBeVisible();
  const firstPending = await page.evaluate(() =>
    localStorage.getItem("pending_review_submission_v1"),
  );
  expect(firstPending).not.toBeNull();
  expect(
    await page.evaluate(() =>
      localStorage.getItem("review_practiced_on_v1:browser-test-retryable"),
    ),
  ).toBeNull();

  await page
    .getByRole("button", { name: "Retry submission", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your review batch is saved!" }),
  ).toBeVisible();
  expect(
    await page.evaluate(() =>
      localStorage.getItem("pending_review_submission_v1"),
    ),
  ).toBeNull();
  expect(commands).toHaveLength(2);
  expect(commands[0]).toEqual(commands[1]);
  expect(commands[0].body).toEqual({
    items: [
      {
        card_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        decision: "yes",
        expected_version: 1,
      },
    ],
  });
});

test("a stale batch is visibly rejected and retired", async ({ page }) => {
  await page.goto("/__test__/auth/conflict");
  await answerOneCard(page);

  await expect(
    page.getByRole("heading", { name: "Review not saved" }),
  ).toBeVisible();
  await expect(
    page.getByText("None of your answers were saved.", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Reload current reviews" }),
  ).toBeVisible();
  expect(
    await page.evaluate(() =>
      localStorage.getItem("pending_review_submission_v1"),
    ),
  ).toBeNull();
});

test("empty and authentication states are distinct", async ({ page }) => {
  await page.goto("/__test__/auth/empty");
  await expect(
    page.getByRole("heading", {
      name: "We don't have any cards for you today.",
    }),
  ).toBeVisible();

  await page.goto("/__test__/auth/unauthorized");
  await expect(
    page.getByRole("heading", { name: "Sign in required" }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => localStorage.getItem("gid_id_token")),
  ).toBeNull();
});

test("loading is visible while due cards are pending", async ({ page }) => {
  await page.goto("/__test__/auth/slow");
  await expect(page.getByText("Loading...", { exact: true })).toBeVisible();
  await expect(page.getByText("resilient", { exact: true })).toBeVisible();
});

test("a submission 401 signs out but preserves the unconfirmed command", async ({
  page,
}) => {
  await page.goto("/__test__/auth/submit-unauthorized");
  await answerOneCard(page);

  await expect(
    page.getByRole("heading", { name: "Sign in required" }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => localStorage.getItem("gid_id_token")),
  ).toBeNull();
  expect(
    await page.evaluate(() =>
      localStorage.getItem("pending_review_submission_v1"),
    ),
  ).not.toBeNull();
});

for (const testCase of [
  { mode: "validation", message: "The review was rejected." },
  {
    mode: "not-found",
    message: "One or more review cards are no longer available.",
  },
]) {
  test(`${testCase.mode} rejection never appears successful`, async ({
    page,
  }) => {
    await page.goto(`/__test__/auth/${testCase.mode}`);
    await answerOneCard(page);

    await expect(
      page.getByRole("heading", { name: "Review unavailable" }),
    ).toBeVisible();
    await expect(
      page.getByText(testCase.message, { exact: false }),
    ).toBeVisible();
    expect(
      await page.evaluate(() =>
        localStorage.getItem("pending_review_submission_v1"),
      ),
    ).toBeNull();
  });
}

for (const mode of ["server-error", "invalid-response"]) {
  test(`${mode} remains unconfirmed and recoverable`, async ({ page }) => {
    await page.goto(`/__test__/auth/${mode}`);
    await answerOneCard(page);

    await expect(
      page.getByRole("heading", { name: "Review not confirmed" }),
    ).toBeVisible();
    expect(
      await page.evaluate(() =>
        localStorage.getItem("pending_review_submission_v1"),
      ),
    ).not.toBeNull();
    expect(
      await page.evaluate(
        (mode) =>
          localStorage.getItem(`review_practiced_on_v1:browser-test-${mode}`),
        mode,
      ),
    ).toBeNull();
  });
}

test("logout during private review requires sign-in without guest fallback", async ({
  page,
}) => {
  let publicFetches = 0;
  page.on("request", (request) => {
    if (request.url().includes("/guest/cards.json")) publicFetches++;
  });
  await page.goto("/__test__/auth/retryable");
  await expect(page.getByText("resilient", { exact: true })).toBeVisible();
  await page.locator(".swipe--card").click();
  await page.getByRole("button", { name: "Knew it", exact: true }).click();
  await page.evaluate(() => {
    localStorage.removeItem("gid_id_token");
    localStorage.removeItem("gid_exp");
  });
  await page
    .getByRole("button", { name: "Submit Results", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Sign in required" }),
  ).toBeVisible();
  expect(publicFetches).toBe(0);
  await expect(page).toHaveURL(/\/review$/);
});

test("changing accounts retires an uncertain private command without guest fallback", async ({
  page,
}) => {
  let publicFetches = 0;
  page.on("request", (request) => {
    if (request.url().includes("/guest/cards.json")) publicFetches++;
  });
  await page.route("**/v1/reviews", (route) =>
    route.fulfill({
      status: 503,
      json: {
        error: {
          code: "database_unavailable",
          message: "Retry later.",
          retryable: true,
          request_id: "test",
        },
      },
    }),
  );
  await page.goto("/__test__/auth/retryable");
  await expect(page.getByText("resilient", { exact: true })).toBeVisible();
  await answerOneCard(page);
  await expect(
    page.getByRole("heading", { name: "Review not confirmed" }),
  ).toBeVisible();
  await page.evaluate(() => {
    const exp = Math.floor(Date.now() / 1000) + 3600;
    localStorage.setItem(
      "gid_id_token",
      `e30.${btoa(JSON.stringify({ sub: "browser-test-other-account", exp }))}.test`,
    );
    localStorage.setItem("gid_exp", String(exp));
  });
  await page
    .getByRole("button", { name: "Retry submission", exact: true })
    .click();
  await expect(
    page.getByText(
      "The previous review session was removed after the account changed.",
    ),
  ).toBeVisible();
  expect(
    await page.evaluate(() =>
      localStorage.getItem("pending_review_submission_v1"),
    ),
  ).toBeNull();
  expect(publicFetches).toBe(0);
  await expect(page).toHaveURL(/\/review$/);
});

async function installGoogleSignIn(
  page: import("@playwright/test").Page,
  subject: string,
) {
  await page.route("https://accounts.google.com/gsi/client", (route) =>
    route.abort(),
  );
  await page.addInitScript(
    ({ subject }) => {
      let callback: ((response: { credential: string }) => void) | undefined;
      Object.defineProperty(window, "google", {
        configurable: true,
        value: {
          accounts: {
            id: {
              initialize: (options: { callback: typeof callback }) => {
                callback = options.callback;
              },
              renderButton: (container: HTMLElement) => {
                const button = document.createElement("button");
                button.textContent = "Sign in with Google";
                button.onclick = () => {
                  const exp = Math.floor(Date.now() / 1000) + 3600;
                  callback?.({
                    credential: `e30.${btoa(JSON.stringify({ sub: subject, exp, email: "browser-test@example.com", email_verified: true }))}.test`,
                  });
                };
                container.append(button);
              },
              disableAutoSelect: () => {},
            },
          },
        },
      });
    },
    { subject },
  );
}

async function signInFromMenu(page: import("@playwright/test").Page) {
  await page.getByRole("button", { name: "Guest account menu" }).click();
  await page.getByRole("menuitem", { name: "Sign in", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Sign in with Google" })
    .click();
}

test("guest login replaces its batch with owned review and sends no guest answers", async ({
  page,
  baseURL,
}) => {
  const root = new URL(baseURL ?? "http://127.0.0.1:4173/").pathname.replace(
    /\/$/,
    "",
  );
  await installGoogleSignIn(page, "browser-test-success");
  const writes: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST") writes.push(request.url());
  });
  await page.goto(`${root}/`);
  await page
    .getByRole("button", { name: "Continue as guest", exact: true })
    .click();
  await expect(page).toHaveTitle("Guest review - English Learning");
  await signInFromMenu(page);
  await expect(page).toHaveTitle("Daily English review");
  await expect(page.getByText("resilient", { exact: true })).toBeVisible();
  expect(writes).toEqual([]);
  expect(
    await page.evaluate(() => sessionStorage.getItem("learning_guest_session")),
  ).toBeNull();
  await answerOneCard(page);
  await expect(
    page.getByRole("heading", { name: "Your review batch is saved!" }),
  ).toBeVisible();
  await page.evaluate(() => {
    localStorage.removeItem("gid_id_token");
    localStorage.removeItem("gid_exp");
    window.dispatchEvent(new StorageEvent("storage", { key: "gid_id_token" }));
  });
  await expect(
    page.getByRole("heading", { name: "Your review batch is saved!" }),
  ).toBeVisible();
  expect(
    await page.evaluate(() =>
      localStorage.getItem("pending_review_submission_v1"),
    ),
  ).toBeNull();
});

test("private 401 retains exact pending bytes and retries after same-account login", async ({
  page,
}) => {
  await installGoogleSignIn(page, "browser-test-success");
  let first = true;
  const commands: { body: string | null; key: string | undefined }[] = [];
  await page.route("**/v1/reviews", async (route) => {
    commands.push({
      body: route.request().postData(),
      key: route.request().headers()["idempotency-key"],
    });
    if (first) {
      first = false;
      await route.fulfill({
        status: 401,
        json: {
          error: {
            code: "invalid_authentication",
            message: "Sign in again.",
            retryable: false,
            request_id: "test",
          },
        },
      });
    } else await route.continue();
  });
  await page.goto("/__test__/auth/success");
  await answerOneCard(page);
  await expect(
    page.getByRole("heading", { name: "Sign in required" }),
  ).toBeVisible();
  const bytes = await page.evaluate(() =>
    localStorage.getItem("pending_review_submission_v1"),
  );
  expect(bytes).not.toBeNull();
  await signInFromMenu(page);
  await expect(
    page.getByRole("heading", { name: "Review not confirmed" }),
  ).toBeVisible();
  expect(
    await page.evaluate(() =>
      localStorage.getItem("pending_review_submission_v1"),
    ),
  ).toBe(bytes);
  await page
    .getByRole("button", { name: "Retry submission", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your review batch is saved!" }),
  ).toBeVisible();
  expect(commands).toHaveLength(2);
  expect(commands[1]).toEqual(commands[0]);
});

for (const staleStatus of [200, 401]) {
  test(`an old account's delayed ${staleStatus} cannot replace or sign out the new review`, async ({
    page,
  }) => {
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    let reads = 0;
    await page.route("**/v1/reviews/due?*", async (route) => {
      reads++;
      if (reads === 1) {
        const response = await route.fetch();
        const json = await response.json();
        await held;
        if (staleStatus === 401)
          await route.fulfill({
            status: 401,
            json: {
              error: {
                code: "invalid_authentication",
                message: "Old account expired.",
                retryable: false,
                request_id: "test",
              },
            },
          });
        else
          await route.fulfill({
            response,
            json: {
              ...json,
              items: json.items.map((card: { term: string }) => ({
                ...card,
                term: "old-account-card",
              })),
            },
          });
      } else {
        const response = await route.fetch();
        const json = await response.json();
        await route.fulfill({
          response,
          json: {
            ...json,
            items: json.items.map((card: { term: string }) => ({
              ...card,
              term: "new-account-card",
            })),
          },
        });
      }
    });
    await page.goto("/__test__/auth/slow");
    await expect(page.getByText("Loading...", { exact: true })).toBeVisible();
    await expect.poll(() => reads).toBe(1);
    await page.evaluate(() => {
      const exp = Math.floor(Date.now() / 1000) + 3600;
      localStorage.setItem(
        "gid_id_token",
        `e30.${btoa(JSON.stringify({ sub: "browser-test-new-account", exp }))}.test`,
      );
      localStorage.setItem("gid_exp", String(exp));
      window.dispatchEvent(
        new StorageEvent("storage", { key: "gid_id_token" }),
      );
    });
    await expect(
      page.getByText("new-account-card", { exact: true }),
    ).toBeVisible();
    const staleResponse = page.waitForResponse(
      (response) =>
        response.url().includes("/v1/reviews/due") &&
        response.status() === staleStatus,
    );
    release();
    await (await staleResponse).finished();
    await expect.poll(() => reads).toBe(2);
    await page.waitForTimeout(250);
    await expect(
      page.getByText("new-account-card", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("old-account-card", { exact: true }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: /Account menu for/ }),
    ).toBeVisible();
    expect(
      await page.evaluate(() => localStorage.getItem("gid_id_token")),
    ).not.toBeNull();
  });
}

for (const mode of ["conflict", "validation"]) {
  test(`a retired ${mode} restores its original explanation after reauthentication`, async ({
    page,
  }) => {
    await installGoogleSignIn(page, `browser-test-${mode}`);
    await page.goto(`/__test__/auth/${mode}`);
    await answerOneCard(page);
    const heading =
      mode === "conflict" ? "Review not saved" : "Review unavailable";
    const explanation =
      mode === "conflict"
        ? "A card changed after this review started. None of your answers were saved."
        : "The review was rejected. No answers were saved.";
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    await expect(page.getByText(explanation, { exact: true })).toBeVisible();
    await page.evaluate(() => {
      localStorage.removeItem("gid_id_token");
      localStorage.removeItem("gid_exp");
      window.dispatchEvent(
        new StorageEvent("storage", { key: "gid_id_token" }),
      );
    });
    await expect(
      page.getByRole("heading", { name: "Sign in required" }),
    ).toBeVisible();
    expect(
      await page.evaluate(() =>
        localStorage.getItem("pending_review_submission_v1"),
      ),
    ).toBeNull();
    await signInFromMenu(page);
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    await expect(page.getByText(explanation, { exact: true })).toBeVisible();
    await expect(
      page.getByText("Request ID: 99999999-9999-4999-8999-999999999999", {
        exact: true,
      }),
    ).toBeVisible();
    expect(
      await page.evaluate(() =>
        localStorage.getItem("pending_review_submission_v1"),
      ),
    ).toBeNull();
  });
}

test("a delayed private 401 after explicit sign-out cannot remove the new guest session", async ({
  page,
  baseURL,
}) => {
  const root = new URL(baseURL ?? "http://127.0.0.1:4173/").pathname.replace(
    /\/$/,
    "",
  );
  let release: () => void = () => {};
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  let started = false;
  let publicReads = 0;
  page.on("request", (request) => {
    if (request.url().includes("/guest/cards.json")) publicReads++;
  });
  await page.route("**/v1/reviews/due?*", async (route) => {
    started = true;
    await held;
    await route.fulfill({
      status: 401,
      json: {
        error: {
          code: "invalid_authentication",
          message: "Old request expired.",
          retryable: false,
          request_id: "test",
        },
      },
    });
  });
  await page.goto("/__test__/auth/success");
  await expect.poll(() => started).toBe(true);
  await page.getByRole("button", { name: /Account menu for/ }).click();
  await page.getByRole("menuitem", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL(`${root}/`);
  await page
    .getByRole("button", { name: "Continue as guest", exact: true })
    .click();
  await expect(page).toHaveTitle("Guest review - English Learning");
  const guestDeadline = await page.evaluate(() =>
    sessionStorage.getItem("learning_guest_session"),
  );
  expect(Number(guestDeadline)).toBeGreaterThan(Date.now());
  const activeCard = page.locator('.swipe--card[aria-hidden="false"]');
  await expect(
    page.getByRole("button", { name: "Knew it", exact: true }),
  ).toBeDisabled();
  await activeCard.click();
  await expect(activeCard).toHaveAttribute("aria-expanded", "true");
  const staleResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/v1/reviews/due") && response.status() === 401,
  );
  release();
  await (await staleResponse).finished();
  await page.waitForTimeout(250);
  await expect(page).toHaveTitle("Guest review - English Learning");
  await expect(page).toHaveURL(`${root}/review`);
  await expect(activeCard).toHaveAttribute("aria-expanded", "true");
  expect(publicReads).toBe(1);
  expect(
    await page.evaluate(() => sessionStorage.getItem("learning_guest_session")),
  ).toBe(guestDeadline);
  expect(
    await page.evaluate(() => localStorage.getItem("gid_id_token")),
  ).toBeNull();
});
