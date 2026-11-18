import { fireEvent, render, screen } from "@testing-library/svelte";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { tick } from "svelte";
import Header from "../../src/routes/Header.svelte";
import HomePage from "../../src/routes/+page.svelte";
import GuestReview from "$lib/components/GuestReview.svelte";
import {
  authSession,
  authOffline,
  authNotice,
  signInOpen,
  type AuthSession,
} from "$lib/stores/auth";
import { pendingReviewInfo } from "$lib/review/pending";
import { pwaUpdate, reloadForUpdate } from "$lib/pwa/register";
import { enterGuestSession, renderGoogleButton } from "$lib/auth";
import { goto } from "$app/navigation";
import type { GuestSnapshot } from "$lib/api/contracts";
import { getPublicReviewCards } from "$lib/api/public-review";
import fixture from "../browser/fixtures/guest-cards.json";

vi.mock("$app/state", () => ({
  page: { url: new URL("https://example.test/review") },
}));
vi.mock("$app/navigation", () => ({ goto: vi.fn() }));
vi.mock("$lib/auth", () => ({
  enterGuestSession: vi.fn(() => ({ ok: true })),
  getGuestTimeRemaining: () => 10000,
  leaveGuestSession: vi.fn(),
  signOut: vi.fn(),
  initGsiOnce: vi.fn(),
  renderGoogleButton: vi.fn(),
  onSignInError: () => () => {},
}));
vi.mock("$lib/pwa/register", async (original) => ({
  ...(await original<typeof import("$lib/pwa/register")>()),
  reloadForUpdate: vi.fn(),
}));
vi.mock("$lib/api/public-review", async (original) => ({
  ...(await original<typeof import("$lib/api/public-review")>()),
  getPublicReviewCards: vi.fn(async () => fixture),
}));

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  authSession.set({ kind: "signed-out" });
  authOffline.set(false);
  authNotice.set(null);
  signInOpen.set(false);
  pwaUpdate.set(false);
  pendingReviewInfo.set({
    count: 0,
    ownerId: null,
    email: null,
    expiresAt: null,
  });
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

const sessions: AuthSession[] = [
  { kind: "authenticated", profile: { id: 1, email: "a@example.test" } },
  { kind: "signed-out" },
  { kind: "initializing" },
  { kind: "guest" },
];
it.each(sessions)(
  "offers the update first in $kind menu, with an accessible blue dot",
  async (session) => {
    authSession.set(session);
    render(Header);
    const trigger = screen.getByRole("button", { name: /account menu/i });
    trigger.focus();
    localStorage.setItem("pending_review_submission_v2", "unchanged");
    pwaUpdate.set(true);
    await tick();
    expect(trigger).toHaveFocus();
    expect(trigger).toHaveAccessibleName(/update available/);
    expect(trigger).toHaveAttribute(
      "title",
      expect.stringContaining("update available"),
    );
    expect(trigger).toHaveClass("update-ready");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    await fireEvent.keyDown(trigger, { key: "ArrowDown" });
    const item = await screen.findByRole("menuitem", {
      name: "Reload to update",
    });
    expect(screen.getAllByRole("menuitem")[0]).toBe(item);
    expect(item).toHaveClass("min-h-11");
    expect(reloadForUpdate).not.toHaveBeenCalled();
    item.focus();
    await fireEvent.keyDown(item, { key: "Enter" });
    expect(reloadForUpdate).toHaveBeenCalledOnce();
    expect(localStorage.getItem("pending_review_submission_v2")).toBe(
      "unchanged",
    );
  },
);
it("keeps the amber indicator when expired and still offers the update", async () => {
  authSession.set({ kind: "expired", profile: null });
  pwaUpdate.set(true);
  render(Header);
  const trigger = screen.getByRole("button", { name: /update available/ });
  expect(trigger).toHaveClass("session-expired");
  expect(trigger).not.toHaveClass("update-ready");
  await fireEvent.click(trigger);
  expect(
    await screen.findByRole("menuitem", { name: "Reload to update" }),
  ).toBeVisible();
});
it("has no update cue when no worker is waiting", async () => {
  render(Header);
  const trigger = screen.getByRole("button", { name: /account menu/i });
  expect(trigger).not.toHaveClass("update-ready");
  expect(trigger).not.toHaveAccessibleName(/update available/);
  await fireEvent.click(trigger);
  expect(
    screen.queryByRole("menuitem", { name: "Reload to update" }),
  ).not.toBeInTheDocument();
});
it.each([0, 1, 3])(
  "shows the offline card with %i pending answers and keeps guest entry safe",
  async (count) => {
    authSession.set({ kind: "initializing" });
    authOffline.set(true);
    pendingReviewInfo.set({
      count,
      ownerId: 1,
      email: null,
      expiresAt: Date.now() + 10000,
    });
    const { container } = render(HomePage);
    expect(
      screen.getByRole("heading", { name: "You're offline" }),
    ).toBeVisible();
    expect(
      screen.getByText(
        "Your session is kept on this device. Reconnect to open your decks and send answers.",
      ),
    ).toBeVisible();
    expect(screen.getByText("We'll reconnect automatically.")).toBeVisible();
    if (count)
      expect(
        screen.getByText(
          `${count} ${count === 1 ? "answer is" : "answers are"} saved here and will be sent when you're back.`,
        ),
      ).toBeVisible();
    else expect(screen.queryByText(/saved here/)).not.toBeInTheDocument();
    expect(container.querySelector(".google-signin-container")).toBeNull();
    expect(renderGoogleButton).not.toHaveBeenCalled();
    expect(screen.queryByText(/Sign in to load/)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Continue as guest/ }),
    ).not.toBeInTheDocument();
    await fireEvent.click(
      screen.getByRole("button", { name: "Practice public cards" }),
    );
    expect(enterGuestSession).toHaveBeenCalledWith({ keepRefreshToken: true });
    expect(goto).toHaveBeenCalled();
  },
);
it("removes the offline card silently when the session recovers", async () => {
  authOffline.set(true);
  render(HomePage);
  expect(screen.getByRole("heading", { name: "You're offline" })).toBeVisible();
  authOffline.set(false);
  authSession.set({
    kind: "authenticated",
    profile: { id: 1, email: "a@example.test" },
  });
  await tick();
  expect(
    screen.queryByRole("heading", { name: "You're offline" }),
  ).not.toBeInTheDocument();
  expect(screen.queryByText(/back online/i)).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Start today/ })).toBeVisible();
});
it.each([
  ["2026-12-31T23:30:00Z", "Dec 31, 2026"],
  ["2027-01-01T00:30:00Z", "Jan 1, 2027"],
])(
  "shows snapshot date %s only offline and responds to connectivity events",
  async (generated_at, caption) => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2028-06-15T12:00:00Z"));
    vi.mocked(getPublicReviewCards).mockResolvedValueOnce({
      ...(fixture as GuestSnapshot),
      generated_at,
    });
    const online = vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    const { unmount } = render(GuestReview);
    expect(
      await screen.findByText(`Offline · saved copy from ${caption}`),
    ).toBeVisible();
    online.mockReturnValue(true);
    window.dispatchEvent(new Event("online"));
    await tick();
    expect(screen.queryByText(/Offline ·/)).not.toBeInTheDocument();
    online.mockReturnValue(false);
    window.dispatchEvent(new Event("offline"));
    await tick();
    expect(screen.getByText(/Offline · saved copy/)).toBeVisible();
    const remove = vi.spyOn(window, "removeEventListener");
    unmount();
    expect(remove).toHaveBeenCalledWith("online", expect.any(Function));
    expect(remove).toHaveBeenCalledWith("offline", expect.any(Function));
  },
);
it("omits the guest caption online", async () => {
  vi.spyOn(navigator, "onLine", "get").mockReturnValue(true);
  render(GuestReview);
  await screen.findByText("Flip the card to reveal the answer.");
  expect(screen.queryByText(/Offline ·/)).not.toBeInTheDocument();
});
