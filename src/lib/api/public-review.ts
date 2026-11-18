import { GUEST_CACHE } from "$lib/pwa/policy";
import { base } from "$app/paths";
import { readGuestSnapshot } from "./guest-snapshot.mjs";
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
    try {
      const { snapshot } = await readGuestSnapshot(response);
      return snapshot;
    } catch (error) {
      try {
        if (typeof caches !== "undefined") {
          const cache = await caches.open(GUEST_CACHE);
          await cache.delete(`${base}/guest/cards.json`);
        }
      } catch {
        /* Cache eviction must not replace the validation error. */
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
