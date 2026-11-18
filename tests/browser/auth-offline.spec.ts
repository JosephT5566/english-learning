import { expect, test, type Page } from "@playwright/test";
import { profileKey, refreshKey, seedSignedIn } from "./auth-fixture";

async function launchWithFailedRefresh(page: Page) {
  const session = await seedSignedIn(page);
  let failures = 0;
  await page.route("**/v1/auth/refresh", async (route) => {
    await route.abort("internetdisconnected");
    failures++;
  });
  await page.goto("./");
  await expect.poll(() => failures).toBeGreaterThan(0);
  // Let the rejected fetch and the resulting Svelte store update settle.
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  );
  expect(
    await page.evaluate((key) => localStorage.getItem(key), refreshKey),
  ).toBe(session.refresh);
  expect(
    await page.evaluate((key) => localStorage.getItem(key), profileKey),
  ).toBe(JSON.stringify(session.profile));
  await expect(page.getByText("Session ended", { exact: true })).toHaveCount(0);
  return session;
}

for (const event of ["online", "focus"]) {
  test(`offline auth startup retains session and restores on ${event}`, async ({
    page,
  }) => {
    const session = await launchWithFailedRefresh(page);
    await page.unroute("**/v1/auth/refresh");
    const refreshed = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === "/v1/auth/refresh" &&
        response.status() === 200,
    );
    await page.evaluate((name) => window.dispatchEvent(new Event(name)), event);
    await refreshed;
    await expect(
      page.getByRole("button", { name: /Account menu for/ }),
    ).toBeVisible();
    await expect
      .poll(() => page.evaluate((key) => localStorage.getItem(key), refreshKey))
      .not.toBe(session.refresh);
    await expect(page.getByText("Session ended", { exact: true })).toHaveCount(
      0,
    );
  });
}

test("offline home guest entry retains refresh and Leave guest practice restores it", async ({
  page,
}) => {
  const session = await launchWithFailedRefresh(page);
  await page
    .getByRole("button", { name: "Practice public cards", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: /Guest account menu/i }),
  ).toBeVisible();
  expect(
    await page.evaluate((key) => localStorage.getItem(key), refreshKey),
  ).toBe(session.refresh);
  await page.unroute("**/v1/auth/refresh");
  const refreshed = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/v1/auth/refresh" &&
      response.status() === 200,
  );
  await page.getByRole("button", { name: /Guest account menu/i }).click();
  await page
    .getByRole("menuitem", { name: "Leave guest practice", exact: true })
    .click();
  await refreshed;
  await expect(
    page.getByRole("button", { name: /Account menu for/ }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => sessionStorage.getItem("learning_guest_session")),
  ).toBeNull();
});
