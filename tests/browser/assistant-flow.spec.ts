import { expect, test } from "@playwright/test";

const historyCardId = "20000000-0000-0000-0000-000000000096";

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

test("opens from navigation, shows tools and round trips memory-only card refs", async ({
  page,
}, testInfo) => {
  const requests: unknown[] = [];
  await page.route("**/v1/assistant/messages/stream", (route) => {
    requests.push(route.request().postDataJSON());
    return route.fulfill({
      contentType: "text/event-stream",
      body:
        ": ping\n\n" +
        event("part", {
          id: "p1",
          type: "card_list",
          payload: {
            purpose: "due",
            items: [
              {
                id: historyCardId,
                deck_id: "10000000-0000-0000-0000-000000000001",
                term: "Unrendered card term",
                meaning: "Unrendered card meaning",
              },
            ],
          },
        }) +
        event("delta", { text: "Start with " }) +
        ": ping\n\n" +
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
  await page.getByText("Tool call attempts · 1").click();
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
      {
        role: "assistant",
        content: "Start with 間に合う.",
        parts: [{ type: "card_refs", card_ids: [historyCardId] }],
      },
      { role: "user", content: "What does it mean?" },
    ],
    capabilities: ["parts.v1"],
  });
  await expect(page.locator(".conversation .turn")).toHaveCount(2);
  await expect(
    page.locator(".conversation ol, .conversation table, .conversation a"),
  ).toHaveCount(0);
  await expect(
    page.getByText("Unrendered card term", { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByText("Unrendered card meaning", { exact: true }),
  ).toHaveCount(0);
  const storage = await page.evaluate(() =>
    JSON.stringify({
      local: { ...localStorage },
      session: { ...sessionStorage },
    }),
  );
  for (const privateText of [
    historyCardId,
    "What should I review?",
    "What does it mean?",
    "Start with 間に合う.",
  ])
    expect(storage).not.toContain(privateText);
  await page.reload();
  await expect(
    page.getByText("What should I review?", { exact: true }),
  ).toHaveCount(0);
  await input.fill("Before switching account");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(
    page.getByText("Start with 間に合う.", { exact: true }),
  ).toBeVisible();
  await page.evaluate(() => {
    const old = localStorage.getItem("gid_id_token")!;
    const payload = JSON.parse(
      atob(old.split(".")[1].replaceAll("-", "+").replaceAll("_", "/")),
    );
    payload.sub = "browser-test-assistant-second-account";
    payload.email = "second-account@example.com";
    const encoded = btoa(JSON.stringify(payload))
      .replaceAll("+", "-")
      .replaceAll("/", "_")
      .replaceAll("=", "");
    localStorage.setItem(
      "gid_id_token",
      `${old.split(".")[0]}.${encoded}.test-signature`,
    );
    window.dispatchEvent(new StorageEvent("storage", { key: "gid_id_token" }));
  });
  await expect(
    page.getByText("Before switching account", { exact: true }),
  ).toHaveCount(0);
  await input.fill("New account question");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect.poll(() => requests.length).toBe(4);
  expect(requests[3]).toEqual({
    messages: [{ role: "user", content: "New account question" }],
    capabilities: ["parts.v1"],
  });
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

test("shows a rejected tool batch as attempts", async ({ page }) => {
  await page.route("**/v1/assistant/messages/stream", (route) =>
    route.fulfill({
      contentType: "text/event-stream",
      body:
        event("delta", { text: "Try asking about one deck." }) +
        event("done", {
          tool_calls: Array.from({ length: 4 }, () => ({
            name: "get_due_cards",
            arguments: null,
            duration_ms: 0,
            status: "too_many_calls",
          })),
          stop_reason: "completed",
          usage: null,
        }),
    }),
  );
  await page.goto("./assistant");
  await page
    .getByRole("textbox", { name: "Ask the assistant" })
    .fill("What is due?");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByText("Try asking about one deck.")).toBeVisible();
  const summary = page.getByText("Tool call attempts · 4", { exact: true });
  await expect(summary).toBeVisible();
  await summary.click();
  await expect(
    page.getByText("Get due cards · Rejected", { exact: true }),
  ).toHaveCount(4);
});

test("keeps text and tools with part and future events between deltas", async ({
  page,
}) => {
  await page.route("**/v1/assistant/messages/stream", (route) =>
    route.fulfill({
      contentType: "text/event-stream",
      body:
        event("delta", { text: "Review " }) +
        event("part", {
          id: "p1",
          type: "card_list",
          payload: {
            purpose: "due",
            items: [
              { id: "card", deck_id: "deck", term: "harbor", meaning: "port" },
            ],
          },
        }) +
        event("future", { value: true }) +
        event("delta", { text: "harbor." }) +
        event("done", {
          tool_calls: [
            {
              name: "get_due_cards",
              status: "ok",
              arguments: {},
              duration_ms: 0,
            },
          ],
          stop_reason: "completed",
          usage: null,
        }),
    }),
  );
  await page.goto("./assistant");
  await page
    .getByRole("textbox", { name: "Ask the assistant" })
    .fill("What is due?");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByText("Review harbor.", { exact: true })).toBeVisible();
  await page.getByText("Tool call attempts · 1", { exact: true }).click();
  await expect(page.getByText("Get due cards", { exact: true })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});
