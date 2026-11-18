import workerSource from "../../src/service-worker.ts?raw";
import ts from "typescript";
import { expect, it, vi } from "vitest";
import * as policy from "../../src/lib/pwa/policy";

// Execute the real worker source with browser boundaries supplied by the test.
function worker(enabled = true) {
  const listeners = new Map<string, (event: unknown) => void>();
  const shell = {
    addAll: vi.fn().mockResolvedValue(undefined),
    match: vi.fn(),
    put: vi.fn(),
  };
  const guest = { match: vi.fn(), put: vi.fn() };
  const caches = {
    keys: vi
      .fn()
      .mockResolvedValue([
        "foreign",
        "english-learning-shell-old",
        policy.GUEST_CACHE,
      ]),
    delete: vi.fn().mockResolvedValue(true),
    open: vi.fn(async (name: string) =>
      name === policy.GUEST_CACHE ? guest : shell,
    ),
  };
  const self = {
    location: { origin: "https://example.com" },
    addEventListener: (type: string, listener: (event: unknown) => void) =>
      listeners.set(type, listener),
    skipWaiting: vi.fn(),
    registration: { unregister: vi.fn() },
  };
  const fetch = vi.fn().mockRejectedValue(new Error("offline"));
  const source = workerSource.replace(
    "const PWA_ENABLED = true",
    `const PWA_ENABLED = ${enabled}`,
  );
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const runtime = {
    exports: {},
    require: (name: string) =>
      name === "$service-worker"
        ? {
            base: "/study",
            build: ["/study/asset.js"],
            files: ["/study/guest/cards.json", "/study/manifest.webmanifest"],
            prerendered: ["/study/"],
            version: "test",
          }
        : policy,
    self,
    caches,
    fetch,
    URL,
    Request,
    Response,
    setTimeout,
    clearTimeout,
  };
  new Function(...Object.keys(runtime), compiled)(...Object.values(runtime));
  async function lifecycle(type: string) {
    let pending: Promise<unknown> | undefined;
    listeners.get(type)!({
      waitUntil: (promise: Promise<unknown>) => {
        pending = promise;
      },
    });
    await pending;
  }
  async function request(path: string, navigate = false) {
    let response: Promise<Response> | undefined;
    const request = new Request(`https://example.com${path}`);
    if (navigate) Object.defineProperty(request, "mode", { value: "navigate" });
    listeners.get("fetch")!({
      request,
      respondWith: (promise: Promise<Response>) => {
        response = promise;
      },
    });
    return response;
  }
  return { self, caches, shell, guest, fetch, lifecycle, request, listeners };
}
it("install survives failed warm-up, precaches fallback and never activates early", async () => {
  const w = worker();
  await w.lifecycle("install");
  expect(w.shell.addAll).toHaveBeenCalledWith([
    "/study/asset.js",
    "/study/manifest.webmanifest",
    "/study/",
    "/study/404.html",
    "/study/_app/env.js",
  ]);
  expect(w.self.skipWaiting).not.toHaveBeenCalled();
});
it("serves the generated startup environment from shell cache while offline", async () => {
  const w = worker();
  w.shell.match.mockResolvedValue(new Response("export const env = {};"));
  const response = await w.request("/study/_app/env.js");
  expect(response).toBeDefined();
  expect(await response!.text()).toBe("export const env = {};");
  expect(w.fetch).not.toHaveBeenCalled();
});
it("offline navigations use exact shell pages or fallback, non-OK online HTML stays unchanged", async () => {
  const w = worker();
  w.shell.match.mockImplementation(async (key) =>
    key === "/study/404.html" ? new Response("fallback") : undefined,
  );
  expect(await (await w.request("/study/deep", true))!.text()).toBe("fallback");
  w.fetch.mockResolvedValue(new Response("live 404", { status: 404 }));
  const response = await w.request("/study/", true);
  expect(response!.status).toBe(404);
  expect(w.shell.put).not.toHaveBeenCalled();
  expect(await w.request("/study/_app/version.json")).toBeUndefined();
});
it("guest fetch uses the original request, replaces empty snapshots and falls back on failure", async () => {
  const w = worker();
  const empty = '{"schema_version":1,"items":[]}';
  w.fetch.mockResolvedValue(new Response(empty));
  await w.request("/study/guest/cards.json");
  expect(w.fetch.mock.calls[0][0]).toBeInstanceOf(Request);
  expect(w.guest.put).toHaveBeenCalledOnce();
  w.fetch.mockRejectedValue(new Error("offline"));
  w.guest.match.mockResolvedValue(new Response(empty));
  expect(await (await w.request("/study/guest/cards.json"))!.text()).toBe(
    empty,
  );
});
it("disabled worker deletes only owned caches, unregisters and never intercepts fetch", async () => {
  const w = worker(false);
  await w.lifecycle("install");
  expect(w.caches.open).not.toHaveBeenCalled();
  await w.lifecycle("activate");
  expect(w.caches.delete.mock.calls.map(([name]) => name)).toEqual([
    "english-learning-shell-old",
    policy.GUEST_CACHE,
  ]);
  expect(w.self.registration.unregister).toHaveBeenCalledOnce();
  expect(await w.request("/study/", true)).toBeUndefined();
});

it("guest timeout returns the saved copy before the page deadline", async () => {
  vi.useFakeTimers();
  try {
    const w = worker();
    w.fetch.mockImplementation(() => new Promise(() => {}));
    w.guest.match.mockResolvedValue(new Response("saved"));
    const pending = w.request("/study/guest/cards.json");
    await vi.advanceTimersByTimeAsync(policy.GUEST_TIMEOUT_MS);
    expect(await (await pending)!.text()).toBe("saved");
    expect(policy.GUEST_TIMEOUT_MS).toBeLessThan(15000);
  } finally {
    vi.useRealTimers();
  }
});
