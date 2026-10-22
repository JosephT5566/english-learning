import { expect, test } from "@playwright/test";

let root = "";
test.beforeEach(async ({ page, baseURL }) => {
  root = new URL(baseURL ?? "http://127.0.0.1:4173/").pathname.replace(
    /\/$/,
    "",
  );
  await page.route("https://accounts.google.com/gsi/client", (route) =>
    route.abort(),
  );
  await page.addInitScript(() => {
    Object.defineProperty(window, "google", {
      configurable: true,
      value: {
        accounts: {
          id: {
            initialize: () => {},
            renderButton: (
              container: HTMLElement,
              options: { width: number },
            ) => {
              const button = document.createElement("button");
              button.textContent = "Sign in with Google";
              button.style.width = `${options.width}px`;
              container.append(button);
            },
            disableAutoSelect: () => {},
          },
        },
      },
    });
  });
});

for (const width of [320, 390, 1280]) {
  test(`account menu and Google sign-in reopen at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 800 });
    await page.goto(`${root}/`);
    const account = page.getByRole("button", { name: "Guest account menu" });
    const box = await account.boundingBox();
    expect(box?.width).toBeGreaterThanOrEqual(44);
    expect(box?.height).toBeGreaterThanOrEqual(44);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    for (let attempt = 0; attempt < 2; attempt++) {
      await account.click();
      await page
        .getByRole("menuitem", { name: "Sign in", exact: true })
        .click();
      const dialog = page.getByRole("dialog");
      await expect(dialog).toBeVisible();
      await expect(
        dialog.getByRole("button", { name: "Sign in with Google" }),
      ).toBeVisible();
      const control = dialog.getByRole("button", {
        name: "Sign in with Google",
      });
      const dimensions = await control.evaluate((button) => {
        const parent = button.parentElement!;
        return {
          control: button.getBoundingClientRect().width,
          available: parent.clientWidth,
          overflow: parent.scrollWidth > parent.clientWidth,
        };
      });
      expect(dimensions.control).toBeLessThanOrEqual(dimensions.available);
      expect(dimensions.overflow).toBe(false);
      await dialog.getByRole("button", { name: "Close", exact: true }).click();
      await expect(dialog).not.toBeVisible();
    }
  });
}

test("explicit sign out returns home and requires a new guest selection", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const exp = Math.floor(Date.now() / 1000) + 3600;
    const token = `e30.${btoa(JSON.stringify({ sub: "browser-test-empty", exp }))}.test`;
    localStorage.setItem("gid_id_token", token);
    localStorage.setItem("gid_exp", String(exp));
  });
  await page.goto(`${root}/review`);
  const account = page.getByRole("button", { name: /Account menu for/ });
  await account.click();
  await expect(
    page.getByRole("menuitem", { name: "Public practice" }),
  ).toHaveCount(0);
  await page.getByRole("menuitem", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL(`${root}/`);
  await expect(
    page.getByRole("button", { name: "Continue as guest" }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => sessionStorage.getItem("learning_guest_session")),
  ).toBeNull();
});

for (const flipped of [false, true]) {
  test(`sign-in dialog Escape restores account focus without changing ${flipped ? "back" : "front"} review card`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 800 });
    let apiRequests = 0;
    page.on("request", (request) => {
      if (request.url().includes("/v1/")) apiRequests++;
    });
    await page.goto(`${root}/`);
    await page
      .getByRole("button", { name: "Continue as guest", exact: true })
      .click();
    const active = page.locator('.swipe--card[aria-hidden="false"]');
    await expect(active).toBeVisible();
    if (flipped) await active.click();
    await expect(active).toHaveAttribute("aria-expanded", String(flipped));
    const textBefore = await active.innerText();
    const requestsBefore = apiRequests;
    const account = page.getByRole("button", { name: "Guest account menu" });
    await account.click();
    await page.getByRole("menuitem", { name: "Sign in", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await dialog.focus();
    for (const key of [
      "1",
      "2",
      "3",
      "4",
      "ArrowLeft",
      "ArrowRight",
      "Enter",
      "Space",
    ])
      await page.keyboard.press(key);
    await expect(dialog).toBeVisible();
    await expect(active).toHaveAttribute("aria-expanded", String(flipped));
    expect(await active.innerText()).toBe(textBefore);
    await dialog.getByRole("button", { name: "Close", exact: true }).focus();
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    await expect(account).toBeFocused();
    await expect(active).toHaveAttribute("aria-expanded", String(flipped));
    expect(await active.innerText()).toBe(textBefore);
    expect(apiRequests).toBe(requestsBefore);
  });
}
