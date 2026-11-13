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
      sub: "browser-test-assistant-scroll",
    })}.test-signature`;
    localStorage.setItem("gid_id_token", token);
    localStorage.setItem("gid_exp", String(exp));
  });
  await page.route("**/v1/me/genai-consent", (route) =>
    route.fulfill({ json: { genai_consent_at: "2026-11-13T00:00:00Z" } }),
  );
  await page.route("**/v1/assistant/messages/stream", (route) =>
    route.fulfill({
      contentType: "text/event-stream",
      body:
        event("delta", {
          text: "A long assistant reply with enough text to overflow the message column. ".repeat(
            50,
          ),
        }) +
        event("done", {
          tool_calls: [],
          stop_reason: "completed",
          usage: null,
        }),
    }),
  );
});

for (const viewport of [
  { width: 1280, height: 800, tallInput: false },
  { width: 400, height: 800, tallInput: false },
  { width: 400, height: 450, tallInput: false },
  { width: 400, height: 500, tallInput: true },
]) {
  test(`only messages scroll at ${viewport.width}x${viewport.height}${viewport.tallInput ? " with capped textarea" : ""}`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.goto("./assistant");
    const input = page.getByRole("textbox", { name: "Ask the assistant" });
    const send = page.getByRole("button", {
      name: "Send message",
      exact: true,
    });
    for (let i = 0; i < 3; i++) {
      await input.fill(`Long reply ${i + 1}`);
      await send.click();
      await expect(page.locator(".conversation .turn")).toHaveCount(i + 1);
      await expect(send).toBeVisible();
      await expect(input).not.toHaveAttribute("readonly");
    }
    await input.fill(
      viewport.tallInput
        ? Array(30).fill("Keep the composer reachable.").join("\n")
        : "Next question",
    );
    if (viewport.tallInput) {
      await expect
        .poll(() => input.evaluate((element) => element.clientHeight))
        .toBeGreaterThanOrEqual(140);
      const sizes = await input.evaluate((element) => ({
        client: element.clientHeight,
        scroll: element.scrollHeight,
      }));
      expect(sizes.client).toBeLessThanOrEqual(144);
      expect(sizes.scroll).toBeGreaterThan(sizes.client);
    }
    await expect
      .poll(() =>
        page.evaluate(() => {
          const root = document.scrollingElement!;
          return root.scrollHeight - root.clientHeight;
        }),
      )
      .toBeLessThan(1);
    const containers = await page.evaluate(() => {
      const selectors = [
        "html",
        "body",
        ".app",
        "main",
        ".assistant-page",
        ".message-list",
      ];
      return selectors.map((selector) => {
        const element = document.querySelector(selector)!;
        const css = getComputedStyle(element);
        return {
          selector,
          overflow: element.scrollHeight - element.clientHeight,
          overflowY: css.overflowY,
          overscroll: css.overscrollBehaviorY,
        };
      });
    });
    for (const container of containers.slice(0, -1)) {
      expect(
        container.overflow,
        `${container.selector} content must fit`,
      ).toBeLessThan(1);
      expect(container.overflowY, `${container.selector} must not scroll`).toBe(
        "hidden",
      );
    }
    expect(containers.at(-1)).toMatchObject({
      selector: ".message-list",
      overflowY: "auto",
      overscroll: "contain",
    });
    expect(containers.at(-1)!.overflow).toBeGreaterThan(0);
    await expect(page.locator(".composer")).toBeInViewport({ ratio: 1 });
    await expect(input).toBeInViewport({ ratio: 1 });
    await expect(send).toBeInViewport({ ratio: 1 });
    // Trial checks hit testing and clipping without changing the conversation.
    await send.click({ trial: true });
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
  });
}
