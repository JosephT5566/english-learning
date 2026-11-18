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
  let timer: ReturnType<typeof setTimeout> | undefined;
  let result: { response: Response; cacheable: boolean };
  try {
    result = await Promise.race([
      // Keep the original request semantics. Late work has no cache side effects;
      // Promise.race observes its rejection even after the deadline wins.
      (async () => {
        const response = await fetch(request);
        return { response, cacheable: await cacheableSnapshot(response) };
      })(),
      new Promise<never>((_, reject) => {
        timer = setTimeout(
          () => reject(new Error("Snapshot timeout")),
          GUEST_TIMEOUT_MS,
        );
      }),
    ]);
  } catch (error) {
    const saved = await caches
      .open(GUEST_CACHE)
      .then((cache) => cache.match(guestUrl))
      .catch(() => undefined);
    if (saved) return saved;
    throw error;
  } finally {
    clearTimeout(timer);
  }
  if (result.cacheable) {
    try {
      const cache = await caches.open(GUEST_CACHE);
      await cache.put(guestUrl, result.response.clone());
    } catch {
      // Persistence is best effort; a live response remains authoritative.
    }
  }
  return result.response;
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
          let response: Response;
          try {
            response = await fetch(event.request);
          } catch (error) {
            const saved = await caches
              .open(SHELL_CACHE)
              .then(
                async (cache) =>
                  (precache.includes(url.pathname)
                    ? await cache.match(url.pathname)
                    : undefined) ?? (await cache.match(fallback)),
              )
              .catch(() => undefined);
            if (saved) return saved;
            throw error;
          }
          // Only known prerendered pages belong in the shell cache.
          if (response.ok && precache.includes(url.pathname)) {
            try {
              const cache = await caches.open(SHELL_CACHE);
              await cache.put(url.pathname, response.clone());
            } catch {
              // Cache failures must not replace live HTML with a stale page.
            }
          }
          return response;
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
