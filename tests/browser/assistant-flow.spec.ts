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
  await page.getByRole("button", { name: "Send message", exact: true }).click();
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
  await page.getByRole("button", { name: "Send message", exact: true }).click();
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
  await page.getByRole("button", { name: "Send message", exact: true }).click();
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
  await page.getByRole("button", { name: "Send message", exact: true }).click();
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
  const send = page.getByRole("button", { name: "Send message", exact: true });
  await input.fill("What is due?");
  await send.click();
  await expect(
    page.getByRole("button", { name: "Grant consent" }),
  ).toBeVisible();
  await expect(send).toHaveCount(0);
  await expect(input).toHaveCount(0);
  await page.getByRole("button", { name: "Grant consent" }).click();
  await expect(input).toHaveValue("What is due?");
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
  await page.getByRole("button", { name: "Send message", exact: true }).click();
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
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.getByText("Review harbor.", { exact: true })).toBeVisible();
  await page.getByText("Tool call attempts · 1", { exact: true }).click();
  await expect(page.getByText("Get due cards", { exact: true })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("renders a proposal without writing or persisting drafts before Confirm", async ({
  page,
}) => {
  const errors: string[] = [];
  const writes: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      /\/v1\/(cards|decks\/[^/]+\/cards)/.test(request.url())
    )
      writes.push(request.url());
  });
  const proposal = {
    id: "p1",
    type: "card_proposal",
    payload: {
      proposal_id: "30000000-0000-0000-0000-000000000097",
      deck: {
        id: "10000000-0000-0000-0000-000000000097",
        title: "Travel English",
        target_language: "en",
      },
      drafts: [
        {
          term: "wander",
          meaning: "walk without a destination",
          synonyms: [],
          antonyms: [],
        },
      ],
      warnings: [],
    },
  };
  await page.route("**/v1/assistant/messages/stream", (route) =>
    route.fulfill({
      contentType: "text/event-stream",
      body:
        ": ping\n\n" +
        event("part", proposal) +
        ": ping\n\n" +
        event("delta", { text: "A draft is " }) +
        ": ping\n\n" +
        event("delta", { text: "ready for confirmation." }) +
        event("done", {
          tool_calls: [
            {
              name: "propose_cards",
              arguments: {},
              duration_ms: 0,
              status: "ok",
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
    .fill("Propose a card");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.getByText("A draft is ready for confirmation.", { exact: true }),
  ).toBeVisible();
  await page.getByText("Tool call attempts · 1", { exact: true }).click();
  await expect(page.getByText("Propose cards", { exact: true })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.locator(".conversation .turn")).toHaveCount(1);
  await expect(page.getByRole("checkbox")).toBeChecked();
  await expect(
    page.getByRole("button", { name: "Edit wander", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Remove wander", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Add to Travel English.*1 card/ }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /Dismiss/ })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByText(proposal.payload.drafts[0].term, { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(proposal.payload.drafts[0].meaning, { exact: true }),
  ).toBeVisible();
  const storage = await page.evaluate(() =>
    JSON.stringify({
      local: { ...localStorage },
      session: { ...sessionStorage },
    }),
  );
  for (const text of [
    proposal.payload.proposal_id,
    proposal.payload.deck.title,
    proposal.payload.drafts[0].term,
    proposal.payload.drafts[0].meaning,
    "Propose a card",
    "A draft is ready for confirmation.",
  ])
    expect(storage).not.toContain(text);
  expect(writes).toEqual([]);
  expect(errors).toEqual([]);
  await page.reload();
  await expect(page.locator(".conversation")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("composer reserves space, grows, and ignores IME confirmation and Shift+Enter", async ({
  page,
}) => {
  let requests = 0;
  await page.route("**/v1/assistant/messages/stream", async (route) => {
    requests++;
    await route.fulfill({
      contentType: "text/event-stream",
      body:
        event("delta", { text: "Ready." }) +
        event("done", {
          tool_calls: [],
          stop_reason: "completed",
          usage: null,
        }),
    });
  });
  await page.goto("./assistant");
  const input = page.getByRole("textbox", { name: "Ask the assistant" });
  await expect(input).toHaveAttribute("rows", "1");
  const before = await input.boundingBox();
  await input.fill(
    "first\nsecond\nthird\nfourth\nfifth\nsixth\nseventh\neighth\nninth\ntenth",
  );
  await expect
    .poll(async () => (await input.boundingBox())!.height)
    .toBeGreaterThan(before!.height);
  const style = await input.evaluate((element) => {
    const css = getComputedStyle(element);
    return {
      max: css.maxHeight,
      overflow: css.overflowY,
      resize: css.resize,
      height: element.clientHeight,
      scroll: element.scrollHeight,
    };
  });
  expect(style.max).toMatch(/144px/);
  expect(style.overflow).toBe("auto");
  expect(style.resize).toBe("none");
  expect(style.height).toBeLessThanOrEqual(144);
  expect(style.scroll).toBeGreaterThan(style.height);
  expect(
    await page
      .locator(".composer")
      .evaluate((element) => getComputedStyle(element).position),
  ).not.toBe("fixed");
  expect(
    await page
      .locator(".message-list")
      .evaluate((element) => getComputedStyle(element).overflowY),
  ).toBe("auto");
  const send = page.getByRole("button", { name: "Send message", exact: true });
  const box = await send.boundingBox();
  expect(box!.width).toBeGreaterThanOrEqual(44);
  expect(box!.height).toBeGreaterThanOrEqual(44);
  await input.fill("test");
  await input.press("Shift+Enter");
  await expect(input).toHaveValue("test\n");
  await input.dispatchEvent("keydown", { key: "Enter", isComposing: true });
  await input.dispatchEvent("keydown", { key: "Enter", keyCode: 229 });
  await input.dispatchEvent("compositionstart");
  await input.dispatchEvent("keydown", { key: "Enter" });
  expect(requests).toBe(0);
  await input.dispatchEvent("compositionend");
  await input.press("Enter");
  await expect.poll(() => requests).toBe(1);
  await expect(page.getByText("Ready.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Stop/ })).toHaveCount(0);
  await expect(
    page.getByText("Refreshing the page clears this conversation."),
  ).toBeVisible();
});

test("assistant compact consent explicitly grants, retries failures and preserves turns on failed withdrawal", async ({
  page,
}) => {
  let granted = false;
  let grantAttempts = 0;
  let withdrawAttempts = 0;
  let messages = 0;
  await page.route("**/v1/me/genai-consent", (route) => {
    const method = route.request().method();
    if (method === "PUT") {
      grantAttempts++;
      if (grantAttempts === 1)
        return route.fulfill({
          status: 503,
          json: {
            error: {
              code: "unavailable",
              request_id: "test",
              message: "Grant failed",
              retryable: true,
            },
          },
        });
      granted = true;
    }
    if (method === "DELETE") {
      withdrawAttempts++;
      if (withdrawAttempts === 1)
        return route.fulfill({
          status: 503,
          json: {
            error: {
              code: "unavailable",
              request_id: "test",
              message: "Withdrawal failed",
              retryable: true,
            },
          },
        });
      granted = false;
    }
    return route.fulfill({
      json: { genai_consent_at: granted ? "2026-11-12T00:00:00Z" : null },
    });
  });
  await page.route("**/v1/assistant/messages/stream", (route) => {
    messages++;
    return route.fulfill({
      contentType: "text/event-stream",
      body:
        event("delta", { text: "Keep this reply." }) +
        event("done", {
          tool_calls: [],
          stop_reason: "completed",
          usage: null,
        }),
    });
  });
  await page.goto("./assistant");
  await expect(
    page.getByRole("button", { name: "Grant consent" }),
  ).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "Ask the assistant" }),
  ).toHaveCount(0);
  await expect(
    page.getByText(
      "Your messages and relevant card information are sent to Google Vertex AI. You can withdraw consent here at any time.",
    ),
  ).toBeVisible();
  await page.getByText("Details", { exact: true }).click();
  await expect(
    page.getByText(
      /Withdrawing consent deletes your existing embeddings and stops AI features/,
    ),
  ).toBeVisible();
  await page.getByRole("button", { name: "Grant consent" }).click();
  await expect(page.getByRole("alert")).toContainText("Grant failed");
  await expect(page.getByRole("alert")).toBeFocused();
  await page.getByRole("button", { name: "Retry grant" }).click();
  const manage = page.getByRole("button", { name: /AI consent is active/ });
  await expect(manage).toBeVisible();
  expect(messages).toBe(0);
  await page.getByRole("textbox", { name: "Ask the assistant" }).fill("hello");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(
    page.getByText("Keep this reply.", { exact: true }),
  ).toBeVisible();
  await manage.click();
  await expect(
    page.getByRole("heading", { name: "Withdraw AI consent?" }),
  ).toBeFocused();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Keep consent" }).click();
  await expect(manage).toBeFocused();
  expect(withdrawAttempts).toBe(0);
  await manage.click();
  await page.getByRole("button", { name: "Confirm withdrawal" }).click();
  await expect(page.getByRole("alert")).toContainText("Withdrawal failed");
  await expect(
    page.getByText("Keep this reply.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Retry withdrawal" }).click();
  await expect(
    page.getByRole("heading", { name: "Allow the learning assistant?" }),
  ).toBeFocused();
  await expect(page.getByText("Keep this reply.", { exact: true })).toHaveCount(
    0,
  );
});

test("initial consent check is visible and hides the composer", async ({
  page,
}) => {
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/v1/me/genai-consent", async (route) => {
    await gate;
    await route.fulfill({ json: { genai_consent_at: null } });
  });
  await page.goto("./assistant");
  await expect(
    page.getByRole("heading", { name: "Checking AI consent…" }),
  ).toBeVisible();
  await expect(
    page.getByRole("status").filter({ hasText: /Please wait/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "Ask the assistant" }),
  ).toHaveCount(0);
  release();
  await expect(
    page.getByRole("button", { name: "Grant consent" }),
  ).toBeVisible();
});

test("stream in flight is readonly with disabled Replying and no Stop", async ({
  page,
}) => {
  let requests = 0;
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/v1/assistant/messages/stream", async (route) => {
    requests++;
    await gate;
    await route.fulfill({
      contentType: "text/event-stream",
      body:
        event("delta", { text: "Reply finished." }) +
        event("done", {
          tool_calls: [],
          stop_reason: "completed",
          usage: null,
        }),
    });
  });
  await page.goto("./assistant");
  const input = page.getByRole("textbox", { name: "Ask the assistant" });
  await input.fill("help");
  await input.press("Enter");
  await expect(page.getByRole("button", { name: "Replying…" })).toBeDisabled();
  await expect(input).toHaveAttribute("readonly", "");
  await expect(page.getByRole("button", { name: /Stop/ })).toHaveCount(0);
  await input.press("Enter");
  expect(requests).toBe(1);
  const rules = await page.evaluate(() => {
    const texts: string[] = [];
    for (const sheet of document.styleSheets) {
      try {
        texts.push(...Array.from(sheet.cssRules, (rule) => rule.cssText));
      } catch {
        /* Cross-origin stylesheets throw on cssRules. */
      }
    }
    for (const style of document.querySelectorAll("style")) {
      texts.push(style.textContent ?? "");
    }
    return texts.join("\n");
  });
  expect(rules).toContain("safe-area-inset-bottom");
  release();
  await expect(
    page.getByText("Reply finished.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Send message" }),
  ).toBeVisible();
});

test("a stream consent error keeps an already-shown partial reply beside the grant card", async ({
  page,
}) => {
  await page.route("**/v1/assistant/messages/stream", (route) =>
    route.fulfill({
      contentType: "text/event-stream",
      body:
        event("delta", { text: "A partial answer." }) +
        event("error", {
          code: "genai_consent_required",
          message: "Please grant consent.",
          retryable: false,
        }),
    }),
  );
  await page.goto("./assistant");
  await page.getByRole("textbox", { name: "Ask the assistant" }).fill("help");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(
    page.getByText("A partial answer.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Grant consent" }),
  ).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "Ask the assistant" }),
  ).toHaveCount(0);
});
