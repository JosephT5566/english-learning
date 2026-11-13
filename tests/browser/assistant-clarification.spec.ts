import { expect, test, type Page } from "@playwright/test";
import type {
  AssistantMessage,
  AssistantPart,
  ClarificationQuestion,
} from "../../src/lib/api/client";

const uuid = (index: number) =>
  `10000000-0000-4000-8000-${String(index).padStart(12, "0")}`;
const term: ClarificationQuestion = {
  question_id: uuid(101),
  question: "Which meaning of bank?",
  purpose: "term",
  allow_free_text: true,
  options: [
    "Financial institution",
    "River bank",
    "A row",
    "Deposit money",
  ].map((label, index) => ({ id: uuid(index + 1), label })),
};
const deck: ClarificationQuestion = {
  question_id: uuid(102),
  question: "Which deck?",
  purpose: "deck",
  allow_free_text: false,
  options: Array.from({ length: 20 }, (_, index) => ({
    id: uuid(index + 21),
    label: `Study deck ${index + 1}`,
    deck_id: uuid(index + 61),
  })),
};
const proposal: AssistantPart = {
  id: "proposal",
  type: "card_proposal",
  payload: {
    proposal_id: uuid(103),
    deck: { id: uuid(61), title: "Travel English", target_language: "en" },
    drafts: [
      {
        term: "bank",
        meaning: "Financial institution",
        synonyms: [],
        antonyms: [],
      },
    ],
    warnings: [],
  },
};
function event(name: string, data: object) {
  return `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;
}
function stream(parts: AssistantPart[], text = "Please choose.") {
  return (
    parts.map((part) => event("part", part)).join("") +
    event("delta", { text }) +
    event("done", { tool_calls: [], stop_reason: "completed", usage: null })
  );
}
const part = (question: ClarificationQuestion): AssistantPart => ({
  id: question.question_id,
  type: "clarification_question",
  payload: question,
});
async function mockConversation(page: Page, replies: string[]) {
  const requests: { messages: AssistantMessage[] }[] = [];
  await page.route("**/v1/assistant/messages/stream", (route) => {
    requests.push(route.request().postDataJSON());
    return route.fulfill({
      contentType: "text/event-stream",
      body: replies[requests.length - 1] ?? stream([], "Ready to continue."),
    });
  });
  await page.goto("./assistant");
  await compose(page, "Make a bank card");
  return requests;
}
async function compose(page: Page, text: string) {
  await page.getByRole("textbox", { name: "Ask the assistant" }).fill(text);
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "Ask the assistant" }),
  ).not.toHaveAttribute("readonly");
}
async function tabTo(page: Page, target: ReturnType<Page["getByRole"]>) {
  // Start at a known earlier control, then use only Tab to reach the target.
  await page
    .getByRole("button", { name: "AI consent is active. Manage AI consent" })
    .focus();
  for (let index = 0; index < 35; index++) {
    await page.keyboard.press("Tab");
    if (await target.evaluate((element) => element === document.activeElement))
      return;
  }
  await expect(target).toBeFocused();
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const encode = (value: object) =>
      btoa(JSON.stringify(value))
        .replaceAll("+", "-")
        .replaceAll("/", "_")
        .replaceAll("=", "");
    const exp = Math.floor(Date.now() / 1000) + 3600;
    const token = `${encode({ alg: "none" })}.${encode({ iss: "https://accounts.google.com", aud: "browser-contract-test", exp, email: "browser-test@example.com", email_verified: true, sub: "browser-test-clarification" })}.test-signature`;
    localStorage.setItem("gid_id_token", token);
    localStorage.setItem("gid_exp", String(exp));
  });
  await page.route("**/v1/me/genai-consent", (route) =>
    route.fulfill({ json: { genai_consent_at: "2026-11-13T00:00:00Z" } }),
  );
});

for (const width of [400, 1280]) {
  test(`term chips send labels and stay locked in history at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 800 });
    const requests = await mockConversation(page, [
      stream([part(term)]),
      stream([], "Draft can be edited before confirming."),
    ]);
    const card = page.getByRole("region", { name: term.question });
    // Count only term chips. Playwright treats "Send description" (no
    // aria-pressed) as pressed:false, so a region-wide pressed:false query
    // would be 5.
    await expect(
      card.getByRole("list", { name: "Answer options" }).getByRole("button"),
    ).toHaveCount(4);
    await expect(card).toBeVisible();
    await card.getByRole("button", { name: "River bank" }).click();
    await expect(card.getByText("Answered: River bank")).toBeVisible();
    expect(requests[1].messages.at(-1)).toEqual({
      role: "user",
      content: "River bank",
      parts: [
        {
          type: "clarification_answer",
          question_id: term.question_id,
          option_id: term.options[1].id,
        },
      ],
    });
    await expect(page.locator(".question").last()).toHaveText("YouRiver bank");
    await expect(
      card.getByRole("button", { name: "River bank" }),
    ).toHaveAttribute("aria-pressed", "true");
    await expect(
      card.getByRole("button", { name: "River bank" }),
    ).toBeDisabled();
    expect(
      await card
        .getByRole("button", { name: "River bank" })
        .evaluate((element) => getComputedStyle(element).backgroundColor),
    ).toBe("rgb(49, 95, 137)");
    await compose(page, "Continue");
    await expect(card.getByText("Answered: River bank")).toBeVisible();
    expect(requests[2].messages[2].parts).toEqual(
      requests[1].messages.at(-1)!.parts,
    );
    expect(
      await page.evaluate(
        () =>
          document.scrollingElement!.scrollHeight -
          document.scrollingElement!.clientHeight,
      ),
    ).toBeLessThan(1);
    expect(
      await card.evaluate((element) => !!element.closest(".message-list")),
    ).toBe(true);
    for (const button of await card.getByRole("button").all()) {
      expect(
        await button.evaluate(
          (element) => getComputedStyle(element).backgroundColor,
        ),
      ).not.toBe("rgb(255, 62, 0)");
    }
  });
}

for (const path of ["card", "composer"]) {
  test(`${path} free text answers a term question`, async ({ page }) => {
    const requests = await mockConversation(page, [stream([part(term)])]);
    const input = page.getByRole("textbox", {
      name: path === "card" ? "Or describe it yourself" : "Ask the assistant",
    });
    await input.fill("  River edge  ");
    await page
      .getByRole("button", {
        name: path === "card" ? "Send description" : "Send message",
        exact: true,
      })
      .click();
    await expect(page.getByText("Answered: River edge")).toBeVisible();
    expect(requests[1].messages.at(-1)).toEqual({
      role: "user",
      content: "River edge",
      parts: [
        {
          type: "clarification_answer",
          question_id: term.question_id,
          text: "River edge",
        },
      ],
    });
    await expect(page.locator(".question").last()).toHaveText("YouRiver edge");
  });
}

test("deck picker scrolls locally, keeps composer ordinary, and sends only after confirmation", async ({
  page,
}) => {
  await page.setViewportSize({ width: 400, height: 800 });
  const requests = await mockConversation(page, [stream([part(deck)])]);
  const group = page.getByRole("radiogroup", { name: deck.question });
  await expect(group.getByRole("radio")).toHaveCount(20);
  expect(
    await group.evaluate((element) => ({
      overflow: getComputedStyle(element).overflowY,
      overscroll: getComputedStyle(element).overscrollBehaviorY,
      scrolls: element.scrollHeight > element.clientHeight,
    })),
  ).toEqual({ overflow: "auto", overscroll: "contain", scrolls: true });
  await expect(
    page.getByRole("button", { name: "Use this deck" }),
  ).toBeDisabled();
  await compose(page, "Study deck 12");
  expect(requests[1].messages.at(-1)).toEqual({
    role: "user",
    content: "Study deck 12",
  });
  await expect(group.getByRole("radio").first()).toBeEnabled();
  await group
    .getByRole("radio", { name: "Study deck 20", exact: true })
    .check();
  expect(requests).toHaveLength(2);
  await page.getByRole("button", { name: "Use this deck" }).click();
  await expect(page.getByText("Answered: Study deck 20")).toBeVisible();
  expect(requests[2].messages.at(-1)).toEqual({
    role: "user",
    content: "Study deck 20",
    parts: [
      {
        type: "clarification_answer",
        question_id: deck.question_id,
        option_id: deck.options[19].id,
        deck_id: deck.options[19].deck_id,
      },
    ],
  });
  await expect(
    group.getByRole("radio", { name: "Study deck 20", exact: true }),
  ).toBeDisabled();
  expect(
    await group
      .getByRole("radio", { name: "Study deck 20", exact: true })
      .evaluate(
        (element) => getComputedStyle(element.parentElement!).backgroundColor,
      ),
  ).toBe("rgb(49, 95, 137)");
  expect(
    await page.evaluate(
      () =>
        document.scrollingElement!.scrollHeight -
        document.scrollingElement!.clientHeight,
    ),
  ).toBeLessThan(1);
});

test("Tab reaches a native term chip and Enter sends", async ({ page }) => {
  const requests = await mockConversation(page, [stream([part(term)])]);
  const chip = page.getByRole("button", { name: "River bank" });
  await tabTo(page, chip);
  await page.keyboard.press("Enter");
  await expect(page.getByText("Answered: River bank")).toBeVisible();
  expect(requests[1].messages.at(-1)!.parts).toEqual([
    {
      type: "clarification_answer",
      question_id: term.question_id,
      option_id: term.options[1].id,
    },
  ]);
});

test("Tab reaches deck radios and confirm, Enter confirms the selected deck", async ({
  page,
}) => {
  const requests = await mockConversation(page, [stream([part(deck)])]);
  const first = page.getByRole("radio", { name: "Study deck 1", exact: true });
  await tabTo(page, first);
  await page.keyboard.press("Space");
  await expect(first).toBeChecked();
  expect(requests).toHaveLength(1);
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("button", { name: "Use this deck" }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Answered: Study deck 1")).toBeVisible();
  expect(requests[1].messages.at(-1)!.parts).toEqual([
    {
      type: "clarification_answer",
      question_id: deck.question_id,
      option_id: deck.options[0].id,
      deck_id: deck.options[0].deck_id,
    },
  ]);
});

test("three locked questions are followed by reply text and the existing draft card, with no fourth question", async ({
  page,
}) => {
  const questions = [0, 1, 2].map((index) => ({
    ...term,
    question_id: uuid(110 + index),
    question: `Question ${index + 1}?`,
  }));
  const limitText =
    "I've asked 3 times. Here is the closest draft. You can still edit it before confirming.";
  await mockConversation(page, [
    ...questions.map((q) => stream([part(q)])),
    stream([proposal], limitText),
    stream([part(deck)]),
  ]);
  for (const q of questions) {
    const card = page.getByRole("region", { name: q.question });
    await card.getByRole("button", { name: "River bank" }).click();
    await expect(card.getByText("Answered: River bank")).toBeVisible();
    await expect(
      page.getByRole("textbox", { name: "Ask the assistant" }),
    ).not.toHaveAttribute("readonly");
  }
  await expect(page.getByText(limitText)).toBeVisible();
  await expect(page.locator(".clarify")).toHaveCount(3);
  await expect(
    page.getByRole("heading", { name: "Review drafts before adding" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "Add to Travel English · 1 card",
      exact: true,
    }),
  ).toBeVisible();
  await compose(page, "Use another deck");
  await expect(
    page.getByRole("radiogroup", { name: deck.question }),
  ).toBeVisible();
});
