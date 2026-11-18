import { beforeEach, expect, it, vi } from "vitest";
import { authOffline } from "$lib/stores/auth";
const initializeSession = vi.hoisted(() => vi.fn());
vi.mock("$app/environment", () => ({ browser: true }));
vi.mock("$app/paths", () => ({ base: "" }));
vi.mock("$lib/auth", () => ({ initializeSession, getIsSignedIn: () => false }));
import { load } from "../../src/routes/+layout";

beforeEach(() => {
  initializeSession.mockReset();
  authOffline.set(false);
});
it("does not retry refresh when an offline redirect runs layout load", async () => {
  authOffline.set(true);
  await load({
    url: new URL("https://example.com/"),
    params: {},
    route: { id: "/" },
    data: null,
    get tracing(): never {
      throw new Error("Client layout must not access server tracing");
    },
    fetch,
    setHeaders: () => {},
    depends: () => {},
    parent: async () => ({}),
    untrack: (fn) => fn(),
  });
  expect(initializeSession).not.toHaveBeenCalled();
});
it("still initializes a normal home navigation", async () => {
  await load({
    url: new URL("https://example.com/"),
    params: {},
    route: { id: "/" },
    data: null,
    get tracing(): never {
      throw new Error("Client layout must not access server tracing");
    },
    fetch,
    setHeaders: () => {},
    depends: () => {},
    parent: async () => ({}),
    untrack: (fn) => fn(),
  });
  expect(initializeSession).toHaveBeenCalledOnce();
});
