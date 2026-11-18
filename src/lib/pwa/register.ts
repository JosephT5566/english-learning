import { writable } from "svelte/store";

export const pwaUpdate = writable(false);
let waiting: ServiceWorker | null = null;
let reloading = false;

export function reloadForUpdate(): void {
  if (!waiting || reloading || !navigator.serviceWorker.controller) return;
  reloading = true;
  navigator.serviceWorker.addEventListener(
    "controllerchange",
    () => window.location.reload(),
    { once: true },
  );
  waiting.postMessage({ type: "SKIP_WAITING" });
}

export function registerPwa(base: string, dev: boolean): () => void {
  if (
    dev ||
    typeof navigator === "undefined" ||
    !("serviceWorker" in navigator)
  )
    return () => {};
  let disposed = false;
  let registration: ServiceWorkerRegistration | undefined;
  const removers: (() => void)[] = [];
  const observe = () => {
    if (disposed) return;
    waiting = navigator.serviceWorker.controller
      ? (registration?.waiting ?? null)
      : null;
    pwaUpdate.set(waiting !== null);
  };
  const watchInstalling = () => {
    observe();
    const worker = registration?.installing;
    if (worker) {
      worker.addEventListener("statechange", observe);
      removers.push(() => worker.removeEventListener("statechange", observe));
    }
  };
  const visible = () => {
    if (document.visibilityState === "visible")
      void registration?.update().catch(() => {});
  };
  void navigator.serviceWorker
    .register(`${base}/service-worker.js`, { scope: `${base}/` })
    .then((value) => {
      if (disposed) return;
      registration = value;
      watchInstalling();
      value.addEventListener("updatefound", watchInstalling);
      removers.push(() =>
        value.removeEventListener("updatefound", watchInstalling),
      );
      document.addEventListener("visibilitychange", visible);
      removers.push(() =>
        document.removeEventListener("visibilitychange", visible),
      );
    })
    .catch(() => {});
  return () => {
    disposed = true;
    for (const remove of removers) remove();
    waiting = null;
    pwaUpdate.set(false);
  };
}
