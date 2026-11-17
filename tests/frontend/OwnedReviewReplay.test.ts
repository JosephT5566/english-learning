import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { get } from "svelte/store";
import OwnedReview from "$lib/components/OwnedReview.svelte";
import { exchangeCredential, expireSession, signOut } from "$lib/auth";
import { authNotice } from "$lib/stores/auth";
import {
  createPendingSubmission,
  savePendingSubmission,
  PENDING_REVIEW_STORAGE_KEY,
  setPendingGuestMode,
} from "$lib/review/pending";
import { card } from "./review-fixture";

vi.mock("$app/environment", () => ({ browser: true }));
vi.mock("$env/static/public", () => ({
  PUBLIC_GOOGLE_AUTH_CLIENT_ID: "test-client",
  PUBLIC_EMAIL_WHITE_LIST: "learner@example.test",
}));
vi.mock("$env/dynamic/public", () => ({
  env: { PUBLIC_API_BASE_URL: "https://api.example.test" },
}));

let finish: (response: Response) => void;
let fail: (error: Error) => void;
let writes: RequestInit[];
const json = (body: unknown) => new Response(JSON.stringify(body));
beforeEach(async () => {
  await signOut();
  localStorage.clear();
  sessionStorage.clear();
  setPendingGuestMode(false);
  authNotice.set(null);
  writes = [];
  const replay = new Promise<Response>((resolve, reject) => {
    finish = resolve;
    fail = reject;
  });
  vi.spyOn(Math, "random").mockReturnValue(0.5);
  let session = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url, init: RequestInit = {}) => {
      const path = String(url);
      if (path.endsWith("/auth/logout"))
        return new Response(null, { status: 204 });
      if (path.endsWith("/auth/session")) {
        session++;
        return json({
          access_token: `ela_session_${session}`,
          access_expires_at: new Date(Date.now() + 900_000).toISOString(),
          refresh_token: `elr_session_${session}`,
          refresh_expires_at: new Date(Date.now() + 604800_000).toISOString(),
          user: { id: 1, email: "learner@example.test" },
          profile: { name: "Learner", picture: null },
        });
      }
      if (path.endsWith("/v1/reviews")) {
        writes.push(init);
        return replay;
      }
      return json({
        items: [
          card,
          {
            ...card,
            id: "ffffffff-ffff-4fff-8fff-ffffffffffff",
            term: "reliable",
          },
        ],
        next_cursor: null,
      });
    }),
  );
  await exchangeCredential("synthetic-google-credential");
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

async function startReplay() {
  const { container } = render(OwnedReview, { ownerId: 1 });
  await screen.findByText("resilient", { exact: true });
  await fireEvent.click(container.querySelector(".swipe--card")!);
  vi.useFakeTimers({
    toFake: [
      "setTimeout",
      "clearTimeout",
      "requestAnimationFrame",
      "cancelAnimationFrame",
    ],
  });
  await fireEvent.click(screen.getByRole("button", { name: "Knew it" }));
  await vi.advanceTimersByTimeAsync(1100);
  vi.useRealTimers();
  await screen.findByText("2 / 2");
  await fireEvent.click(
    container.querySelector('.swipe--card[aria-hidden="false"]')!,
  );
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Knew it" })).toBeEnabled(),
  );
  const original = localStorage.getItem(PENDING_REVIEW_STORAGE_KEY)!;
  expireSession();
  const login = exchangeCredential("synthetic-google-credential");
  await waitFor(() => expect(writes).toHaveLength(1));
  return { original, login };
}

it.each(["success", "ambiguous failure"] as const)(
  "keeps a re-login replay immutable during %s",
  async (outcome) => {
    const { original, login } = await startReplay();
    const command = JSON.parse(original);
    const answer = screen.queryByRole("button", { name: "Knew it" });
    expect(answer === null || answer.hasAttribute("disabled")).toBe(true);
    await fireEvent.keyDown(window, { key: "ArrowUp" });
    if (answer) await fireEvent.click(answer);
    expect(localStorage.getItem(PENDING_REVIEW_STORAGE_KEY)).toBe(original);
    expect(writes[0].body).toBe(JSON.stringify(command.payload));
    expect(writes[0].headers).toMatchObject({
      "Idempotency-Key": command.idempotencyKey,
    });
    if (outcome === "success") {
      const state = card.review_state;
      finish(
        json({
          batch_id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
          reviewed_at: "2026-11-17T00:00:00Z",
          algorithm_version: "srs-v1",
          items: [
            {
              event_id: 1,
              card_id: command.payload.items[0].card_id,
              decision: "yes",
              quality: 5,
              previous_state: state,
              resulting_state: { ...state, version: 8 },
            },
          ],
        }),
      );
      await login;
      expect(localStorage.getItem(PENDING_REVIEW_STORAGE_KEY)).toBeNull();
      expect(get(authNotice)).toEqual({ kind: "saved", count: 1 });
    } else {
      fail(new Error("Connection lost after sending"));
      await login;
      expect(localStorage.getItem(PENDING_REVIEW_STORAGE_KEY)).toBe(original);
      expect(
        await screen.findByRole("button", { name: "Retry submission" }),
      ).toBeEnabled();
      expect(
        screen.queryByRole("button", { name: "Knew it" }),
      ).not.toBeInTheDocument();
      await fireEvent.click(
        screen.getByRole("button", { name: "Retry submission" }),
      );
      await waitFor(() => expect(writes).toHaveLength(2));
      expect(writes[1].body).toBe(writes[0].body);
      expect(writes[1].headers).toMatchObject({
        "Idempotency-Key": command.idempotencyKey,
      });
    }
    expect(writes).toHaveLength(outcome === "success" ? 1 : 2);
  },
);

it("allowlist removal during submission retains exact pending bytes and disables retry", async () => {
  const command = createPendingSubmission(1, {
    items: [
      {
        card_id: card.id,
        decision: "yes",
        expected_version: card.review_state.version,
      },
    ],
  });
  savePendingSubmission(command);
  const raw = localStorage.getItem(PENDING_REVIEW_STORAGE_KEY);
  render(OwnedReview, { ownerId: 1 });
  await fireEvent.click(
    await screen.findByRole("button", { name: "Retry submission" }),
  );
  await waitFor(() => expect(writes).toHaveLength(1));
  finish(
    new Response(
      JSON.stringify({
        error: {
          code: "account_not_allowed",
          message: "Account is not allowed.",
          retryable: false,
          request_id: "test",
        },
      }),
      { status: 403 },
    ),
  );
  await screen.findByRole("heading", {
    name: /Review not confirmed|Review unavailable/,
  });
  expect(localStorage.getItem(PENDING_REVIEW_STORAGE_KEY)).toBe(raw);
  expect(get(authNotice)).toEqual({
    kind: "error",
    email: "learner@example.test",
  });
  expect(
    await screen.findByRole("button", { name: "Retry submission" }),
  ).toBeDisabled();
  expect(writes).toHaveLength(1);
});
