import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  hasPracticedToday,
  localReviewDate,
  markPracticedToday,
} from "$lib/review/activity";

describe("private review activity", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 0, 2, 0, 5));
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("stores the full browser-local date for only the submitting account", () => {
    markPracticedToday("account-a");
    expect(localStorage.getItem("review_practiced_on_v1:account-a")).toBe(
      "2026-01-02",
    );
    expect(hasPracticedToday("account-a")).toBe(true);
    expect(hasPracticedToday("account-b")).toBe(false);
    expect(localReviewDate(new Date(2026, 0, 2, 23, 59))).toBe("2026-01-02");
  });

  it("does not reuse activity on the next local day or the same day in another year", () => {
    markPracticedToday("account-a");
    expect(hasPracticedToday("account-a", new Date(2026, 0, 3))).toBe(false);
    expect(hasPracticedToday("account-a", new Date(2027, 0, 2))).toBe(false);
    vi.setSystemTime(new Date(2026, 11, 31, 23, 59));
    markPracticedToday("account-a");
    expect(hasPracticedToday("account-a", new Date(2027, 0, 1))).toBe(false);
  });

  it.each(["01/02", "2026-1-2", "invalid", '{"date":"2026-01-02"}'])(
    "ignores malformed or legacy date %s",
    (value) => {
      localStorage.setItem("review_practiced_on_v1:account-a", value);
      localStorage.setItem("isTestedToday", "01/02");
      expect(hasPracticedToday("account-a")).toBe(false);
    },
  );

  it("treats storage read and write failures as an unavailable activity hint", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("Storage unavailable", "QuotaExceededError");
    });
    expect(() => markPracticedToday("account-a")).not.toThrow();
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("Storage unavailable", "SecurityError");
    });
    expect(hasPracticedToday("account-a")).toBe(false);
  });
});
