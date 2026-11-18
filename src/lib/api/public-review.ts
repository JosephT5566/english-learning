import { GUEST_CACHE, guestLastGoodKey } from "$lib/pwa/policy";
import { base } from "$app/paths";
import { MAX_SNAPSHOT_BYTES, readGuestSnapshot } from "./guest-snapshot.mjs";
import type { PublicReviewCard, GuestSnapshot } from "./contracts";

export async function getPublicReviewCards(
  signal?: AbortSignal,
): Promise<GuestSnapshot> {
  const requestSignal = signal
    ? AbortSignal.any([signal, AbortSignal.timeout(15000)])
    : AbortSignal.timeout(15000);
  try {
    const response = await fetch(`${base}/guest/cards.json`, {
      method: "GET",
      credentials: "omit",
      redirect: "error",
      signal: requestSignal,
    });
    // Clone before strict validation consumes the response body.
    let validatedCopy: Promise<Response | undefined> | undefined;
    try {
      const copy = response.clone();
      let bytes = 0;
      // Drain the clone with the same size bound so validation can cancel its
      // branch without waiting forever for an unread tee branch.
      validatedCopy = new Response(
        copy.body?.pipeThrough(
          new TransformStream({
            transform(chunk, controller) {
              bytes += chunk.byteLength;
              if (bytes > MAX_SNAPSHOT_BYTES)
                throw new Error("Snapshot too large");
              controller.enqueue(chunk);
            },
          }),
        ),
      )
        .arrayBuffer()
        .then(
          (body) =>
            new Response(body, { status: copy.status, headers: copy.headers }),
        )
        .catch(() => undefined);
    } catch {
      // Saving a last-good copy is best effort.
    }
    try {
      const { snapshot } = await readGuestSnapshot(response);
      try {
        if (typeof caches !== "undefined" && validatedCopy) {
          const cache = await caches.open(GUEST_CACHE);
          const copy = await validatedCopy;
          if (copy) await cache.put(guestLastGoodKey(base), copy);
        }
      } catch {
        // Cache failures must not affect a validated snapshot.
      }
      return snapshot;
    } catch (error) {
      try {
        if (typeof caches !== "undefined") {
          const cache = await caches.open(GUEST_CACHE);
          const lastGood = await cache.match(guestLastGoodKey(base));
          if (lastGood) {
            await cache.put(`${base}/guest/cards.json`, lastGood);
          } else if (response.status === 200) {
            await cache.delete(`${base}/guest/cards.json`);
          }
        }
      } catch {
        /* Cache recovery must not replace the validation error. */
      }
      throw error;
    }
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new Error(
      "The card snapshot was unavailable or invalid. Please try again.",
    );
  }
}

export function sampleGuestCards(
  pool: readonly PublicReviewCard[],
): PublicReviewCard[] {
  const shuffled = [...pool];
  for (let index = shuffled.length - 1; index > 0; index--) {
    const other = Math.floor(Math.random() * (index + 1));
    [shuffled[index], shuffled[other]] = [shuffled[other], shuffled[index]];
  }
  return shuffled.slice(0, 10);
}
