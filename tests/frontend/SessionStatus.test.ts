import { render, screen, fireEvent } from "@testing-library/svelte";
import { beforeEach, expect, it, vi } from "vitest";
import { get } from "svelte/store";
import SessionStatus from "$lib/components/SessionStatus.svelte";
import { authSession, authNotice, signInOpen } from "$lib/stores/auth";
import { pendingReviewInfo } from "$lib/review/pending";

vi.mock("$app/state", () => ({
  page: { url: new URL("https://app.example.test/review") },
}));
vi.mock("$app/navigation", () => ({ goto: vi.fn() }));
vi.mock("$lib/auth", () => ({ enterGuestSession: () => ({ ok: true }) }));
beforeEach(() => {
  authSession.set({
    kind: "authenticated",
    profile: { id: 1, email: "learner@example.test" },
  });
  authNotice.set(null);
  signInOpen.set(false);
  pendingReviewInfo.set({
    count: 0,
    ownerId: null,
    email: null,
    expiresAt: null,
  });
});
it("shows no strip during a healthy signed-in session", () => {
  render(SessionStatus);
  expect(screen.queryByTestId("session-status")).not.toBeInTheDocument();
});
it("shows the amber recovery strip and opens the shared sign-in dialog", async () => {
  authSession.set({
    kind: "expired",
    profile: { id: 1, email: "learner@example.test" },
  });
  pendingReviewInfo.set({
    count: 7,
    ownerId: 1,
    email: "learner@example.test",
    expiresAt: Date.now() + 1000,
  });
  render(SessionStatus);
  const strip = screen.getByTestId("session-status");
  expect(strip).toHaveAttribute("aria-live", "polite");
  expect(strip).toHaveClass("amber");
  expect(strip).toHaveTextContent(
    "7 answers are saved here and will be sent after you sign in.",
  );
  expect(
    screen.getByRole("button", { name: "Continue as guest" }),
  ).toBeVisible();
  await fireEvent.click(screen.getByRole("button", { name: "Sign in again" }));
  expect(get(signInOpen)).toBe(true);
});
it("guest pending bar names the account and cannot be dismissed", () => {
  authSession.set({ kind: "guest" });
  pendingReviewInfo.set({
    count: 7,
    ownerId: 1,
    email: "learner@example.test",
    expiresAt: Date.now() + 1000,
  });
  render(SessionStatus);
  expect(screen.getByTestId("session-status")).toHaveTextContent(
    "7 answers for learner@example.test stay on this device",
  );
  expect(screen.getByRole("button", { name: "Sign in to send" })).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Dismiss session notice" }),
  ).not.toBeInTheDocument();
});
it("allowlist rejection names the rejected account even after session expiry", () => {
  authSession.set({ kind: "expired", profile: null });
  authNotice.set({ kind: "error", email: "not-allowed@example.test" });
  render(SessionStatus);
  expect(screen.getByRole("alert")).toHaveTextContent(
    "not-allowed@example.test can't open private decks.",
  );
  expect(
    screen.getByRole("button", { name: "Continue as guest" }),
  ).toBeVisible();
});
it("expired saved answers notice remains visible until manually closed", async () => {
  authNotice.set({ kind: "pending-expired" });
  render(SessionStatus);
  expect(screen.getByTestId("session-status")).toHaveTextContent(
    "Saved answers expired and were not sent",
  );
  await fireEvent.click(
    screen.getByRole("button", { name: "Dismiss session notice" }),
  );
  expect(screen.queryByTestId("session-status")).not.toBeInTheDocument();
});
