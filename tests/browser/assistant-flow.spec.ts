import { expect, test } from "@playwright/test";

function event(name: string, data: object): string {
  return `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const encode = (value: object) =>
      btoa(JSON.stringify(value))
        .replaceAll("+", "-")
        .replaceAll("/", "_")
        .replaceAll("=", "");
    const exp = Math.floor(Date.now() / 1000) + 3600;
    const token = `${encode({ alg: "none" })}.${encode({
      iss: "https://accounts.google.com",
      aud: "browser-contract-test",
      exp,
      email: "browser-test@example.com",
      email_verified: true,
      sub: "browser-test-assistant",
    })}.test-signature`;
    localStorage.setItem("gid_id_token", token);
    localStorage.setItem("gid_exp", String(exp));
  });
  await page.route("**/v1/me/genai-consent", (route) =>
    route.fulfill({ json: { genai_consent_at: "2026-11-08T00:00:00Z" } }),
  );
});

test("opens from navigation, shows tools and sends only text history", async ({
  page,
}, testInfo) => {
  const requests: unknown[] = [];
  await page.route("**/v1/assistant/messages/stream", (route) => {
    requests.push(route.request().postDataJSON());
    return route.fulfill({
      contentType: "text/event-stream",
      body:
        event("delta", { text: "Start with " }) +
        event("delta", { text: "間に合う." }) +
        event("done", {
          tool_calls: [
            {
              name: "get_due_cards",
              arguments: {},
              duration_ms: 1,
              status: "ok",
            },
          ],
          stop_reason: "completed",
          usage: null,
        }),
    });
  });
  await page.setViewportSize({ width: 390, height: 700 });
  await page.goto("./");
  await page.getByRole("link", { name: "Assistant" }).click();
  await expect(
    page.getByRole("heading", { name: "Learning assistant" }),
  ).toBeVisible();
  const input = page.getByRole("textbox", { name: "Ask the assistant" });
  await input.fill("What should I review?");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByText("Start with 間に合う.")).toBeVisible();
  await page.getByText("Tools used · 1 call").click();
  await expect(page.getByText("Get due cards")).toBeVisible();
  for (const width of [390, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(page.locator(".assistant-page")).toBeInViewport();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width);
    await testInfo.attach(`assistant-${width}`, {
      body: await page.screenshot({ fullPage: true }),
      contentType: "image/png",
    });
  }
  await input.fill("What does it mean?");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect.poll(() => requests.length).toBe(2);
  expect(requests[1]).toEqual({
    messages: [
      { role: "user", content: "What should I review?" },
      { role: "assistant", content: "Start with 間に合う." },
      { role: "user", content: "What does it mean?" },
    ],
  });
  await page.reload();
  await expect(
    page.getByText("What should I review?", { exact: true }),
  ).toHaveCount(0);
});

test("handles consent 403, then keeps a partial reply on timeout and stream failure", async ({
  page,
}) => {
  let attempts = 0;
  await page.route("**/v1/assistant/messages/stream", (route) => {
    attempts++;
    if (attempts === 1) {
      return route.fulfill({
        status: 403,
        json: {
          error: {
            code: "genai_consent_required",
            message: "Consent required",
            retryable: false,
            request_id: "test",
          },
        },
      });
    }
    return route.fulfill({
      contentType: "text/event-stream",
      body:
        attempts === 2
          ? event("delta", { text: "Partial reply" }) +
            event("done", {
              tool_calls: [],
              stop_reason: "timeout",
              usage: null,
            })
          : event("delta", { text: "Another partial reply" }) +
            event("error", {
              code: "generation_unavailable",
              message: "The assistant is unavailable.",
              retryable: true,
            }),
    });
  });
  await page.goto("./assistant");
  const input = page.getByRole("textbox", { name: "Ask the assistant" });
  const send = page.getByRole("button", { name: "Send", exact: true });
  await input.fill("What is due?");
  await send.click();
  await expect(
    page.getByRole("button", { name: "Grant consent" }),
  ).toBeVisible();
  await expect(send).toBeDisabled();
  await expect(input).toHaveValue("What is due?");
  await page.getByRole("button", { name: "Grant consent" }).click();
  await send.click();
  await expect(page.getByText("Partial reply", { exact: true })).toBeVisible();
  await expect(page.getByText(/timed out/i)).toBeVisible();
  await input.fill("How many Japanese cards?");
  await send.click();
  await expect(page.getByText("Another partial reply")).toBeVisible();
  await expect(page.getByText("The assistant is unavailable.")).toBeVisible();
});
