import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
import { beforeEach, expect, it, vi } from "vitest";
import { get } from "svelte/store";
import OwnedReview from "$lib/components/OwnedReview.svelte";
import { card } from "./review-fixture";
import { authSession } from "$lib/stores/auth";
import {
  pendingReviewInfo,
  pendingReviewResult,
  setPendingGuestMode,
  PENDING_REVIEW_STORAGE_KEY,
} from "$lib/review/pending";
vi.mock("$env/dynamic/public", () => ({
  env: { PUBLIC_API_BASE_URL: "https://api.example.test" },
}));
const api = vi.hoisted(() => ({
  getDueReviews: vi.fn(),
  submitReviews: vi.fn(),
}));
vi.mock("$lib/api/client", async (original) => ({
  ...(await original<typeof import("$lib/api/client")>()),
  ...api,
}));
vi.mock("$lib/auth", () => ({
  getProfile: () => {
    const session = get(authSession);
    return session.kind === "authenticated" || session.kind === "expired"
      ? session.profile
      : null;
  },
}));
beforeEach(() => {
  localStorage.clear();
  setPendingGuestMode(false);
  pendingReviewResult.set(null);
  pendingReviewInfo.set({
    count: 0,
    ownerId: null,
    email: null,
    expiresAt: null,
  });
  authSession.set({
    kind: "authenticated",
    profile: { id: 1, email: "learner@example.test" },
  });
  localStorage.setItem(
    "el_auth_profile_v1",
    JSON.stringify({ id: 1, email: "learner@example.test" }),
  );
  api.getDueReviews
    .mockReset()
    .mockResolvedValue({ items: [card], next_cursor: null });
  api.submitReviews.mockReset();
});
it("retains answered cards as fixed-TTL pending and disables submission on expiry", async () => {
  const { container } = render(OwnedReview, { ownerId: 1 });
  await screen.findByText("resilient", { exact: true });
  await fireEvent.click(container.querySelector(".swipe--card")!);
  await fireEvent.click(screen.getByRole("button", { name: "Knew it" }));
  await waitFor(() => expect(get(pendingReviewInfo).count).toBe(1));
  const saved = localStorage.getItem(PENDING_REVIEW_STORAGE_KEY);
  authSession.set({
    kind: "expired",
    profile: { id: 1, email: "learner@example.test" },
  });
  expect(
    await screen.findByRole("button", { name: "Submit Results" }),
  ).toBeDisabled();
  expect(localStorage.getItem(PENDING_REVIEW_STORAGE_KEY)).toBe(saved);
  expect(api.submitReviews).not.toHaveBeenCalled();
  expect(api.getDueReviews).toHaveBeenCalledTimes(1);
});

it("starts a fresh review without consuming a historical replay result", async () => {
  pendingReviewResult.set({
    ownerId: 1,
    idempotencyKey: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    result: {
      batch_id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
      reviewed_at: "2026-11-17T00:00:00Z",
      algorithm_version: "srs-v1",
      items: [],
    },
  });
  render(OwnedReview, { ownerId: 1 });
  await screen.findByText("resilient", { exact: true });
  expect(
    screen.queryByText("Your review batch is saved!"),
  ).not.toBeInTheDocument();
  expect(api.getDueReviews).toHaveBeenCalledTimes(1);
});
