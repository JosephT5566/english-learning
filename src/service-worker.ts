/// <reference lib="webworker" />
import { base, build, files, prerendered, version } from "$service-worker";
import {
  cachesToDelete,
  cacheableSnapshot,
  eligibleRequest,
  shellPrecache,
  SHELL_PREFIX,
  GUEST_CACHE,
  GUEST_TIMEOUT_MS,
} from "./lib/pwa/policy";

declare const self: ServiceWorkerGlobalScope;
const PWA_ENABLED = true;
const SHELL_CACHE = `${SHELL_PREFIX}${version}`;
const fallback = `${base}/404.html`;
const guestUrl = `${base}/guest/cards.json`;
const precache = shellPrecache(base, build, files, prerendered);

async function clean(current: string | null) {
  await Promise.all(
    cachesToDelete(await caches.keys(), current).map((name) =>
      caches.delete(name),
    ),
  );
}

async function guest(request: Request): Promise<Response> {
  const cache = await caches.open(GUEST_CACHE);
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const response = await Promise.race([
      fetch(request),
      new Promise<never>((_, reject) => {
        timer = setTimeout(
          () => reject(new Error("Snapshot timeout")),
          GUEST_TIMEOUT_MS,
        );
      }),
    ]);
    if (await cacheableSnapshot(response))
      await cache.put(guestUrl, response.clone());
    return response;
  } catch (error) {
    const saved = await cache.match(guestUrl);
    if (saved) return saved;
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

function startWorker(enabled: boolean) {
  self.addEventListener("install", (event) => {
    if (!enabled) return;
    event.waitUntil(
      (async () => {
        const cache = await caches.open(SHELL_CACHE);
        await cache.addAll(precache);
        await guest(
          new Request(new URL(guestUrl, self.location.origin), {
            credentials: "omit",
            redirect: "error",
          }),
        ).catch(() => undefined);
      })(),
    );
  });

  self.addEventListener("activate", (event) => {
    event.waitUntil(
      (async () => {
        await clean(enabled ? SHELL_CACHE : null);
        if (!enabled) await self.registration.unregister();
      })(),
    );
  });

  self.addEventListener("message", (event) => {
    if (event.data?.type === "SKIP_WAITING")
      event.waitUntil(self.skipWaiting());
  });

  self.addEventListener("fetch", (event) => {
    if (!enabled || !eligibleRequest(event.request, self.location.origin, base))
      return;
    const url = new URL(event.request.url);
    if (url.pathname === guestUrl) {
      event.respondWith(guest(event.request));
      return;
    }
    if (event.request.mode === "navigate") {
      event.respondWith(
        (async () => {
          const cache = await caches.open(SHELL_CACHE);
          try {
            const response = await fetch(event.request);
            // Only known prerendered pages belong in the shell cache.
            if (response.ok && precache.includes(url.pathname))
              await cache.put(url.pathname, response.clone());
            return response;
          } catch (error) {
            const saved =
              (precache.includes(url.pathname)
                ? await cache.match(url.pathname)
                : undefined) ?? (await cache.match(fallback));
            if (saved) return saved;
            throw error;
          }
        })(),
      );
    } else if (precache.includes(url.pathname)) {
      event.respondWith(
        (async () =>
          (await (await caches.open(SHELL_CACHE)).match(url.pathname)) ??
          fetch(event.request))(),
      );
    }
  });
}
startWorker(PWA_ENABLED);
