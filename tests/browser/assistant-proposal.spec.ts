import { expect, test, type Page } from "@playwright/test";

const deckId = "10000000-0000-4000-8000-000000000098";
const proposalId = "30000000-0000-4000-8000-000000000098";
const existingId = "20000000-0000-4000-8000-000000000097";
const storageKey = "pending_assistant_proposal_v1";
const deck = {
  id: deckId,
  title: "Travel English",
  target_language: "en",
  explanation_language: "zh-TW",
  archived_at: null,
};
const drafts = ["wander", "itinerary", "souvenir"].map((term) => ({
  term,
  meaning: `${term} meaning`,
  synonyms: [],
  antonyms: [],
}));
function event(name: string, data: object) {
  return `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;
}
function stream() {
  return (
    event("part", {
      id: "proposal",
      type: "card_proposal",
      payload: {
        proposal_id: proposalId,
        deck: { id: deckId, title: deck.title, target_language: "en" },
        drafts,
        warnings: [
          {
            code: "duplicate_term",
            term: "itinerary",
            draft_index: 1,
            existing_card_ids: [existingId],
          },
        ],
      },
    }) +
    event("delta", { text: "Review these drafts." }) +
    event("done", {
      tool_calls: [
        { name: "propose_cards", arguments: {}, duration_ms: 0, status: "ok" },
      ],
      stop_reason: "completed",
      usage: null,
    })
  );
}
function card(fields: (typeof drafts)[number], index: number) {
  return {
    ...fields,
    id: `20000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
    deck,
    reading: null,
    pronunciation: null,
    romanization: null,
    target_language_definition: null,
    part_of_speech: null,
    part_of_speech_detail: null,
    example_sentence: null,
    example_translation: null,
    example_source: null,
    note: null,
    supplementary_note: null,
    learned_on: null,
    archived_at: null,
    version: 1,
    tags: [],
    review_state: null,
    created_at: "2026-11-12T00:00:00Z",
    updated_at: "2026-11-12T00:00:00Z",
  };
}
async function openProposal(page: Page) {
  await page.goto("./assistant");
  await page
    .getByRole("textbox", { name: "Ask the assistant" })
    .fill("Make travel drafts");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Add to Travel English · 3 cards" }),
  ).toBeVisible();
}
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const encode = (value: object) =>
      btoa(JSON.stringify(value))
        .replaceAll("+", "-")
        .replaceAll("/", "_")
        .replaceAll("=", "");
    const exp = Math.floor(Date.now() / 1000) + 3600;
    const token = `${encode({ alg: "none" })}.${encode({ iss: "https://accounts.google.com", aud: "browser-contract-test", exp, email: "browser-test@example.com", email_verified: true, sub: "browser-test-assistant" })}.test-signature`;
    localStorage.setItem("gid_id_token", token);
    localStorage.setItem("gid_exp", String(exp));
  });
  await page.route("**/v1/me/genai-consent", (route) =>
    route.fulfill({ json: { genai_consent_at: "2026-11-12T00:00:00Z" } }),
  );
  await page.route("**/v1/assistant/messages/stream", (route) =>
    route.fulfill({ contentType: "text/event-stream", body: stream() }),
  );
});

test("selects, edits and confirms one atomic bulk request, then sends committed history", async ({
  page,
}) => {
  const writes: {
    cards: { fields: (typeof drafts)[number]; idempotency_key: string }[];
  }[] = [];
  await page.route(`**/v1/decks/${deckId}/cards/bulk`, async (route) => {
    const body = route.request().postDataJSON();
    writes.push(body);
    expect(
      await page.evaluate((key) => localStorage.getItem(key), storageKey),
    ).not.toBeNull();
    await route.fulfill({
      status: 201,
      json: {
        cards: body.cards.map(
          (entry: (typeof body.cards)[number], i: number) => ({
            idempotency_key: entry.idempotency_key,
            card: card(entry.fields, i),
          }),
        ),
      },
    });
  });
  await openProposal(page);
  expect(writes).toHaveLength(0);
  expect(
    await page.evaluate((key) => localStorage.getItem(key), storageKey),
  ).toBeNull();
  await expect(page.getByRole("checkbox")).toHaveCount(3);
  await expect(page.getByText("duplicate term")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Existing card: itinerary" }),
  ).toHaveAttribute("href", new RegExp(`/cards/${existingId}$`));
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("checkbox", { name: "Select souvenir" }).uncheck();
  await page.getByRole("button", { name: "Edit wander" }).click();
  await expect(page.getByLabel("Term", { exact: true })).toBeFocused();
  await page.getByLabel("Term", { exact: true }).fill("roam");
  await page.getByLabel("Meaning", { exact: true }).fill("walk freely");
  await page.getByRole("button", { name: "Apply draft edits" }).click();
  await expect(page.getByRole("button", { name: "Edit roam" })).toBeFocused();
  expect(writes).toHaveLength(0);
  await page
    .getByRole("button", { name: "Add to Travel English · 2 cards" })
    .press("Enter");
  await expect(
    page.getByRole("heading", { name: "Added to Travel English · 2 cards" }),
  ).toBeFocused();
  expect(writes).toHaveLength(1);
  expect(writes[0].cards.map((item) => item.fields.term)).toEqual([
    "roam",
    "itinerary",
  ]);
  expect(writes[0].cards[0].fields.meaning).toBe("walk freely");
  expect(
    new Set(writes[0].cards.map((item) => item.idempotency_key)).size,
  ).toBe(2);
  for (const item of writes[0].cards)
    expect(item.idempotency_key).toMatch(/^[0-9a-f-]{36}$/);
  await expect(
    page.getByRole("link", { name: "roam", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /^Add to/ })).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: /start reviewing/i }),
  ).toHaveCount(0);
  expect(
    await page.evaluate((key) => localStorage.getItem(key), storageKey),
  ).toBeNull();
  let next: { messages: { parts?: unknown[] }[] } | undefined;
  await page.route("**/v1/assistant/messages/stream", (route) => {
    next = route.request().postDataJSON();
    return route.fulfill({
      contentType: "text/event-stream",
      body:
        event("delta", { text: "Added cards acknowledged." }) +
        event("done", {
          tool_calls: [],
          stop_reason: "completed",
          usage: null,
        }),
    });
  });
  await page
    .getByRole("textbox", { name: "Ask the assistant" })
    .fill("What did I add?");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect
    .poll(() => next?.messages[1].parts)
    .toEqual([
      {
        type: "proposal_state",
        proposal_id: proposalId,
        status: "committed",
        created_card_ids: [card(drafts[0], 0).id, card(drafts[1], 1).id],
      },
    ]);
  await expect(
    page.getByText("Added cards acknowledged.", { exact: true }),
  ).toBeVisible();
  await page.evaluate(() => {
    const token = localStorage.getItem("gid_id_token")!;
    const payload = JSON.parse(
      atob(token.split(".")[1].replaceAll("-", "+").replaceAll("_", "/")),
    );
    payload.sub = "browser-test-assistant-second-account";
    const encoded = btoa(JSON.stringify(payload))
      .replaceAll("+", "-")
      .replaceAll("/", "_")
      .replaceAll("=", "");
    localStorage.setItem(
      "gid_id_token",
      `${token.split(".")[0]}.${encoded}.test-signature`,
    );
    window.dispatchEvent(new StorageEvent("storage", { key: "gid_id_token" }));
  });
  await expect(
    page.getByText("Added cards acknowledged.", { exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("textbox", { name: "Ask the assistant" })
    .fill("New account question");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect
    .poll(() => next?.messages)
    .toEqual([{ role: "user", content: "New account question" }]);
});

test("archive recovery preserves exact keys and body and focuses the alert", async ({
  page,
}) => {
  const writes: unknown[] = [];
  await page.route(`**/v1/decks/${deckId}/cards/bulk`, (route) => {
    const body = route.request().postDataJSON();
    writes.push(body);
    return writes.length === 1
      ? route.fulfill({
          status: 409,
          json: {
            error: {
              code: "deck_archived",
              message: "archived",
              retryable: false,
              request_id: "test",
            },
          },
        })
      : route.fulfill({
          status: 201,
          json: {
            cards: body.cards.map(
              (entry: (typeof body.cards)[number], i: number) => ({
                idempotency_key: entry.idempotency_key,
                card: card(entry.fields, i),
              }),
            ),
          },
        });
  });
  await openProposal(page);
  await page
    .getByRole("button", { name: "Add to Travel English · 3 cards" })
    .click();
  await expect(page.getByRole("alert")).toBeFocused();
  await expect(page.getByRole("alert")).toContainText(
    "This deck is archived. Cards cannot be added. Your drafts are still here.",
  );
  await expect(
    page.getByRole("link", { name: "Open deck management" }),
  ).toHaveAttribute(
    "href",
    new RegExp("/decks\\?language=en&status=archived$"),
  );
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Added to Travel English · 3 cards" }),
  ).toBeVisible();
  expect(writes).toHaveLength(2);
  expect(writes[1]).toEqual(writes[0]);
});

test("reload restores only unfinished commit, waits for Retry and replays unchanged", async ({
  page,
}) => {
  const writes: unknown[] = [];
  await page.route(`**/v1/decks/${deckId}/cards/bulk`, (route) => {
    const body = route.request().postDataJSON();
    writes.push(body);
    return writes.length === 1
      ? route.abort("failed")
      : route.fulfill({
          status: 201,
          json: {
            cards: body.cards.map(
              (entry: (typeof body.cards)[number], i: number) => ({
                idempotency_key: entry.idempotency_key,
                card: card(entry.fields, i),
              }),
            ),
          },
        });
  });
  await openProposal(page);
  await page
    .getByRole("button", { name: "Add to Travel English · 3 cards" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Result not confirmed" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByText(
      "Your values are restored. Confirm again to retry the same request safely.",
    ),
  ).toBeVisible();
  await expect(
    page.getByText("Refreshing the page clears this conversation."),
  ).toBeVisible();
  await expect(
    page.getByText("Make travel drafts", { exact: true }),
  ).toHaveCount(0);
  expect(writes).toHaveLength(1);
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Added to Travel English · 3 cards" }),
  ).toBeVisible();
  expect(writes).toHaveLength(2);
  expect(writes[1]).toEqual(writes[0]);
});

test("native keyboard selection, Escape edit cancellation, undo and dismiss keep writes absent", async ({
  page,
}) => {
  const writes: string[] = [];
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      /\/v1\/(cards|decks\/[^/]+\/cards)/.test(request.url())
    )
      writes.push(request.url());
  });
  await openProposal(page);
  const select = page.getByRole("checkbox", { name: "Select wander" });
  await select.focus();
  await select.press("Space");
  await expect(select).not.toBeChecked();
  await select.press("Tab");
  await expect(page.getByRole("button", { name: "Edit wander" })).toBeFocused();
  await page.keyboard.press("Enter");
  await page.getByLabel("Term", { exact: true }).fill("discard me");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Edit wander" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("button", { name: "Remove wander" }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("button", { name: "Edit itinerary" }),
  ).toBeFocused();
  await expect(page.getByText("duplicate term")).toBeVisible();
  await page.getByRole("button", { name: "Undo remove wander" }).click();
  await page.getByRole("button", { name: "Dismiss", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "Skipped. No cards were added." }),
  ).toBeFocused();
  expect(writes).toEqual([]);
});
