import { afterEach, expect, it, vi } from "vitest";
import { get } from "svelte/store";
import {
  pwaUpdate,
  registerPwa,
  reloadForUpdate,
} from "../../src/lib/pwa/register";

afterEach(() => vi.unstubAllGlobals());
it("skips development and unsupported browsers", () => {
  const register = vi.fn();
  vi.stubGlobal("navigator", { serviceWorker: { register } });
  registerPwa("/study", true)();
  expect(register).not.toHaveBeenCalled();
  vi.stubGlobal("navigator", {});
  expect(() => registerPwa("", false)()).not.toThrow();
});
it("reports a waiting update without activating it and checks on visibility", async () => {
  const worker = { postMessage: vi.fn() };
  const registration = Object.assign(new EventTarget(), {
    waiting: worker,
    installing: null,
    update: vi.fn().mockResolvedValue(undefined),
  });
  const container = Object.assign(new EventTarget(), {
    controller: {},
    register: vi.fn().mockResolvedValue(registration),
  });
  vi.stubGlobal("navigator", { serviceWorker: container });
  const dispose = registerPwa("/study", false);
  await Promise.resolve();
  expect(container.register).toHaveBeenCalledWith("/study/service-worker.js", {
    scope: "/study/",
  });
  expect(get(pwaUpdate)).toBe(true);
  expect(worker.postMessage).not.toHaveBeenCalled();
  document.dispatchEvent(new Event("visibilitychange"));
  expect(registration.update).toHaveBeenCalledOnce();
  const reload = vi.fn();
  vi.stubGlobal("window", { location: { reload } });
  reloadForUpdate();
  reloadForUpdate();
  expect(worker.postMessage).toHaveBeenCalledExactlyOnceWith({
    type: "SKIP_WAITING",
  });
  container.dispatchEvent(new Event("controllerchange"));
  container.dispatchEvent(new Event("controllerchange"));
  expect(reload).toHaveBeenCalledOnce();
  dispose();
  expect(get(pwaUpdate)).toBe(false);
});
