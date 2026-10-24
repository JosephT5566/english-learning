import { render, screen, waitFor } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import HomePage from "../../src/routes/+page.svelte";
import { authSession, setSignIn } from "$lib/stores/auth";
import { tick } from "svelte";

vi.mock("$app/navigation", () => ({ goto: vi.fn() }));
vi.mock("$lib/auth", () => ({
  enterGuestSession: vi.fn(),
  initGsiOnce: vi.fn(),
  renderGoogleButton: vi.fn(),
  onSignInError: () => () => {},
}));

describe("home practice activity", () => {
  beforeEach(() => {
    localStorage.clear();
    setSignIn({ sub: "account-a" });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
    authSession.set({ kind: "signed-out" });
  });

  it("ignores the legacy shared marker", async () => {
    const now = new Date();
    localStorage.setItem(
      "isTestedToday",
      `${String(now.getMonth() + 1).padStart(2, "0")}/${String(now.getDate()).padStart(2, "0")}`,
    );
    render(HomePage);
    await waitFor(() =>
      expect(
        screen.getByRole("link", { name: /Start today.s review/ }),
      ).toBeVisible(),
    );
  });

  it("refreshes practice status when the account changes on the mounted homepage", async () => {
    const now = new Date();
    localStorage.setItem(
      "review_practiced_on_v1:account-a",
      `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`,
    );
    render(HomePage);
    expect(
      await screen.findByRole("heading", { name: "You've practiced today" }),
    ).toBeVisible();
    setSignIn({ sub: "account-b" });
    expect(
      await screen.findByRole("link", { name: /Start today.s review/ }),
    ).toBeVisible();
    setSignIn({ sub: "account-a" });
    expect(
      await screen.findByRole("heading", { name: "You've practiced today" }),
    ).toBeVisible();
  });

  it("never reads activity storage for guests", async () => {
    authSession.set({ kind: "guest" });
    const read = vi.spyOn(Storage.prototype, "getItem");
    render(HomePage);
    expect(
      await screen.findByRole("button", { name: /Continue as guest/ }),
    ).toBeVisible();
    expect(read).not.toHaveBeenCalled();
  });

  it("expires the hint and updates the date at local midnight while mounted", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 11, 31, 23, 59, 59));
    localStorage.setItem("review_practiced_on_v1:account-a", "2026-12-31");
    const { container } = render(HomePage);
    await tick();
    expect(
      screen.getByRole("heading", { name: "You've practiced today" }),
    ).toBeVisible();
    await vi.advanceTimersByTimeAsync(1000);
    await tick();
    expect(
      screen.getByRole("link", { name: /Start today.s review/ }),
    ).toBeVisible();
    expect(container.querySelector("time")).toHaveAttribute(
      "datetime",
      "2027-01-01",
    );
  });
});
