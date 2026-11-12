import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const encode = (value: object) =>
      btoa(JSON.stringify(value))
        .replaceAll("+", "-")
        .replaceAll("/", "_")
        .replaceAll("=", "");
    const exp = Math.floor(Date.now() / 1000) + 60 * 60;
    const token = `${encode({ alg: "none" })}.${encode({
      iss: "https://accounts.google.com",
      aud: "browser-contract-test",
      exp,
      email: "browser-test@example.com",
      email_verified: true,
      sub: "browser-test-semantic-search",
    })}.test-signature`;
    localStorage.setItem("gid_id_token", token);
    localStorage.setItem("gid_exp", String(exp));
  });
  await page.route("**/v1/me/genai-consent", (route) =>
    route.fulfill({ json: { genai_consent_at: "2026-11-05T00:00:00Z" } }),
  );
});

test("semantic search preserves static routing and shows partial owned results", async ({
  page,
}) => {
  const requests: { url: string; body: string | null }[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/v1/cards/semantic-search") {
      requests.push({ url: request.url(), body: request.postData() });
    }
  });

  await page.goto("/search");
  await page
    .getByRole("button", { name: "Meaning & concepts", exact: true })
    .click();
  await expect(
    page.getByText("Meaning search currently uses English cards only.", {
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByLabel("Describe the meaning or idea")
    .fill("recover after difficulty");
  await page.getByRole("button", { name: "Search cards", exact: true }).click();

  await expect(page.getByText("resilient", { exact: true })).toBeVisible();
  await expect(page.getByText("Strong match", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /resilient/ })).toHaveAttribute(
    "href",
    "/cards/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa?language=en",
  );
  await expect(page.getByRole("status")).toContainText(
    "Meaning search is ready for 2 of your 3 English cards",
  );
  expect(requests).toHaveLength(1);
  expect(requests[0].url).toBe(
    "http://127.0.0.1:8001/v1/cards/semantic-search",
  );
  expect(JSON.parse(requests[0].body ?? "{}")).toEqual({
    query: "recover after difficulty",
    target_language: "en",
    limit: 10,
  });

  await page.setViewportSize({ width: 390, height: 700 });
  const searchPage = await page.locator(".search-page").boundingBox();
  expect(searchPage?.width).toBeLessThanOrEqual(366);
  await expect(
    page.getByRole("button", { name: "Meaning & concepts" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: /resilient/ })).toBeVisible();
});

test("inline consent gates meaning search and withdrawal requires confirmation", async ({
  page,
}) => {
  let consented = false;
  const methods: string[] = [];
  let searches = 0;
  await page.route("**/v1/me/genai-consent", (route) => {
    const method = route.request().method();
    methods.push(method);
    if (method === "PUT") consented = true;
    if (method === "DELETE") consented = false;
    return route.fulfill({
      json: { genai_consent_at: consented ? "2026-11-05T00:00:00Z" : null },
    });
  });
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/v1/cards/semantic-search")
      searches++;
  });
  await page.setViewportSize({ width: 390, height: 700 });
  await page.goto("/search");
  await page.getByRole("button", { name: "Meaning & concepts" }).click();
  await expect(
    page.getByText(/card text and search queries are sent to Google Vertex AI/),
  ).toBeVisible();
  await expect(page.getByLabel("Describe the meaning or idea")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Search cards", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Allow AI meaning search?" }),
  ).toBeVisible();
  await page.getByText("Details", { exact: true }).click();
  await expect(
    page.getByText(/deletes your existing embeddings/),
  ).toBeVisible();
  expect(searches).toBe(0);
  await page.getByRole("button", { name: "Grant consent" }).click();
  await expect(page.getByLabel("Describe the meaning or idea")).toBeVisible();
  expect(searches).toBe(0);
  await page
    .getByLabel("Describe the meaning or idea")
    .fill("recover after difficulty");
  await page.getByRole("button", { name: "Search cards", exact: true }).click();
  await expect(page.getByText("resilient", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: /AI meaning search is allowed/ })
    .click();
  await expect(
    page.getByText(/deletes your existing embeddings/),
  ).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(methods).toEqual(["GET", "PUT"]);
  await page.getByRole("button", { name: "Keep consent" }).click();
  expect(methods).toEqual(["GET", "PUT"]);
  await expect(
    page.getByRole("button", { name: /AI meaning search is allowed/ }),
  ).toBeFocused();
  await page
    .getByRole("button", { name: /AI meaning search is allowed/ })
    .click();
  await page.getByRole("button", { name: "Confirm withdrawal" }).click();
  await expect(
    page.getByRole("button", { name: "Grant consent" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: /resilient/ })).toHaveCount(0);
  expect(methods).toEqual(["GET", "PUT", "DELETE"]);
  expect(searches).toBe(1);
  await expect(page.getByLabel("Describe the meaning or idea")).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Allow AI meaning search?" }),
  ).toBeFocused();
});

test("consent checks and failed grant keep meaning search unavailable", async ({
  page,
}) => {
  let releaseRead: () => void = () => {};
  const readGate = new Promise<void>((resolve) => {
    releaseRead = resolve;
  });
  let grants = 0;
  let searches = 0;
  await page.route("**/v1/me/genai-consent", async (route) => {
    const method = route.request().method();
    if (method === "GET") {
      await readGate;
      return route.fulfill({ json: { genai_consent_at: null } });
    }
    grants++;
    if (grants === 1)
      return route.fulfill({
        status: 503,
        json: {
          error: {
            code: "unavailable",
            request_id: "test-consent-error",
            message: "Could not grant AI consent.",
            retryable: true,
          },
        },
      });
    return route.fulfill({
      json: { genai_consent_at: "2026-11-12T00:00:00Z" },
    });
  });
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/v1/cards/semantic-search")
      searches++;
  });
  await page.goto("/search");
  await page.getByRole("button", { name: "Meaning & concepts" }).click();
  await expect(
    page.getByRole("heading", { name: "Checking AI consent…" }),
  ).toBeVisible();
  await expect(page.getByRole("status")).toBeVisible();
  await expect(page.getByLabel("Describe the meaning or idea")).toHaveCount(0);
  releaseRead();
  await page.getByRole("button", { name: "Grant consent" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByRole("alert")).toBeFocused();
  await expect(page.getByLabel("Describe the meaning or idea")).toHaveCount(0);
  await page.getByRole("button", { name: "Retry grant" }).click();
  await expect(page.getByLabel("Describe the meaning or idea")).toBeVisible();
  expect(searches).toBe(0);
});

test("withdrawal failure preserves meaning results until successful retry", async ({
  page,
}) => {
  let deletes = 0;
  await page.route("**/v1/me/genai-consent", (route) => {
    if (route.request().method() === "DELETE") {
      deletes++;
      if (deletes === 1)
        return route.fulfill({
          status: 503,
          json: {
            error: {
              code: "unavailable",
              message: "Could not withdraw AI consent.",
              retryable: true,
            },
          },
        });
      return route.fulfill({ json: { genai_consent_at: null } });
    }
    return route.fulfill({
      json: { genai_consent_at: "2026-11-12T00:00:00Z" },
    });
  });
  await page.goto("/search");
  await page.getByRole("button", { name: "Meaning & concepts" }).click();
  await page
    .getByLabel("Describe the meaning or idea")
    .fill("recover after difficulty");
  await page.getByRole("button", { name: "Search cards", exact: true }).click();
  await expect(page.getByRole("link", { name: /resilient/ })).toBeVisible();
  const manage = page.getByRole("button", {
    name: /AI meaning search is allowed/,
  });
  await expect(page.locator(".heading-row")).toContainText("AI on · Manage");
  await manage.click();
  await page.getByRole("button", { name: "Confirm withdrawal" }).click();
  await expect(page.getByRole("alert")).toBeFocused();
  await expect(page.getByRole("link", { name: /resilient/ })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Retry withdrawal" }).click();
  await expect(
    page.getByRole("button", { name: "Grant consent" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: /resilient/ })).toHaveCount(0);
  expect(deletes).toBe(2);
});
