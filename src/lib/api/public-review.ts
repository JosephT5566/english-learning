import { env } from "$env/dynamic/public";
import {
  isApiErrorEnvelope,
  isPublicReviewCards,
  type PublicReviewCards,
} from "./contracts";

export class PublicReviewError extends Error {
  constructor(
    message: string,
    readonly retryAfterSeconds = 0,
    readonly status?: number,
  ) {
    super(message);
    this.name = "PublicReviewError";
  }
}

function retryDelay(header: string | null): number {
  if (!header || !/^\d+$/.test(header)) return 1;
  const seconds = Number(header);
  return Number.isSafeInteger(seconds) && seconds > 0 && seconds <= 3600
    ? seconds
    : 1;
}

export async function getPublicReviewCards(
  signal?: AbortSignal,
): Promise<PublicReviewCards> {
  const base = (env.PUBLIC_API_BASE_URL ?? "").trim().replace(/\/+$/, "");
  if (!base) throw new PublicReviewError("Card review is not configured.");
  let response: Response;
  try {
    response = await fetch(`${base}/v1/public/review-cards`, {
      method: "GET",
      credentials: "omit",
      cache: "no-store",
      signal,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new PublicReviewError(
      "We could not reach the service. Please try again.",
    );
  }
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const cooldown = response.status === 429 || response.status === 503;
    throw new PublicReviewError(
      isApiErrorEnvelope(data)
        ? data.error.message
        : "Card review is unavailable. Please try again.",
      cooldown ? retryDelay(response.headers.get("Retry-After")) : 0,
      response.status,
    );
  }
  if (!isPublicReviewCards(data))
    throw new PublicReviewError(
      "The card response was invalid. Please try again.",
    );
  return data;
}
