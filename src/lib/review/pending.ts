import { get, writable } from "svelte/store";
import type { ReviewResult, ReviewSubmission } from "../api/contracts";

export const PENDING_REVIEW_STORAGE_KEY = "pending_review_submission_v2";
export const PENDING_REVIEW_TTL_MS = 24 * 60 * 60 * 1000;
export const PENDING_REVIEW_METADATA_KEY = "el_review_pending_meta_v1";
const LEGACY_KEY = "pending_review_submission_v1";
const MIGRATION_KEY = "el_review_pending_migrated_v2";
const EXPIRY_SEEN_KEY = "el_review_expired_seen_v1";
const EXPIRY_NOTICE_KEY = "el_review_expired_notice_v1";

export interface PendingReviewSubmission {
  version: 2;
  ownerId: number;
  idempotencyKey: string;
  payload: ReviewSubmission;
  createdAt: number;
  expiresAt: number;
}
export interface PendingReviewInfo {
  count: number;
  ownerId: number | null;
  email: string | null;
  expiresAt: number | null;
}
const emptyInfo: PendingReviewInfo = {
  count: 0,
  ownerId: null,
  email: null,
  expiresAt: null,
};
export const pendingReviewInfo = writable<PendingReviewInfo>({ ...emptyInfo });
export const pendingReviewReplay = writable<{
  ownerId: number;
  idempotencyKey: string;
} | null>(null);
export const pendingReviewResult = writable<{
  ownerId: number;
  idempotencyKey: string;
  result: ReviewResult;
} | null>(null);
let guestMode = false;

export function setPendingGuestMode(value: boolean) {
  guestMode = value;
}

function isPendingSubmission(value: unknown): value is PendingReviewSubmission {
  if (typeof value !== "object" || value === null) return false;
  const pending = value as Partial<PendingReviewSubmission>;
  const items = pending.payload?.items;
  const decisions = new Set(["no", "no_a_bit", "yes_a_bit", "yes"]);
  return (
    pending.version === 2 &&
    Number.isSafeInteger(pending.ownerId) &&
    (pending.ownerId ?? 0) > 0 &&
    typeof pending.idempotencyKey === "string" &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
      pending.idempotencyKey,
    ) &&
    typeof pending.createdAt === "number" &&
    Number.isFinite(pending.createdAt) &&
    typeof pending.expiresAt === "number" &&
    Number.isFinite(pending.expiresAt) &&
    pending.expiresAt === pending.createdAt + PENDING_REVIEW_TTL_MS &&
    Array.isArray(items) &&
    items.length >= 1 &&
    items.length <= 10 &&
    items.every(
      (item) =>
        typeof item === "object" &&
        item !== null &&
        typeof item.card_id === "string" &&
        decisions.has(item.decision) &&
        Number.isInteger(item.expected_version) &&
        item.expected_version >= 1,
    ) &&
    new Set(items.map((item) => item.card_id)).size === items.length
  );
}
function metadata(storage: Storage): PendingReviewInfo {
  try {
    const value: unknown = JSON.parse(
      storage.getItem(PENDING_REVIEW_METADATA_KEY) ?? "null",
    );
    if (typeof value !== "object" || value === null) return { ...emptyInfo };
    const item = value as Partial<PendingReviewInfo>;
    if (
      typeof item.count !== "number" ||
      !Number.isInteger(item.count) ||
      item.count < 0 ||
      item.count > 10 ||
      typeof item.ownerId !== "number" ||
      !Number.isSafeInteger(item.ownerId) ||
      item.ownerId <= 0 ||
      (item.email !== null && typeof item.email !== "string") ||
      typeof item.expiresAt !== "number" ||
      !Number.isFinite(item.expiresAt)
    )
      return { ...emptyInfo };
    return {
      count: item.count,
      ownerId: item.ownerId,
      email: item.email ?? null,
      expiresAt: item.expiresAt,
    };
  } catch {
    return { ...emptyInfo };
  }
}
function expireInfo(info: PendingReviewInfo, storage: Storage) {
  if (info.count && info.expiresAt !== null) {
    const fingerprint = `${info.ownerId}:${info.expiresAt}`;
    if (storage.getItem(EXPIRY_SEEN_KEY) !== fingerprint) {
      storage.setItem(EXPIRY_SEEN_KEY, fingerprint);
      storage.setItem(EXPIRY_NOTICE_KEY, "1");
    }
  }
  storage.removeItem(PENDING_REVIEW_METADATA_KEY);
  pendingReviewInfo.set({ ...emptyInfo });
}
export function consumePendingExpiredNotice(
  storage: Storage = localStorage,
): boolean {
  const show = storage.getItem(EXPIRY_NOTICE_KEY) === "1";
  if (show) storage.removeItem(EXPIRY_NOTICE_KEY);
  return show;
}
function migrateLegacy(storage: Storage) {
  if (!storage.getItem(MIGRATION_KEY)) {
    storage.removeItem(LEGACY_KEY);
    storage.setItem(MIGRATION_KEY, "1");
  }
}
function readPending(
  now: number,
  storage: Storage,
): PendingReviewSubmission | null {
  migrateLegacy(storage);
  const raw = storage.getItem(PENDING_REVIEW_STORAGE_KEY);
  if (!raw) return null;
  try {
    const item: unknown = JSON.parse(raw);
    if (isPendingSubmission(item)) {
      if (item.expiresAt > now) return item;
      expireInfo(
        {
          count: item.payload.items.length,
          ownerId: item.ownerId,
          email: metadata(storage).email,
          expiresAt: item.expiresAt,
        },
        storage,
      );
    }
  } catch {
    /* Invalid commands cannot be replayed. */
  }
  storage.removeItem(PENDING_REVIEW_STORAGE_KEY);
  storage.removeItem(PENDING_REVIEW_METADATA_KEY);
  pendingReviewInfo.set({ ...emptyInfo });
  return null;
}
export function inspectPendingReviews(
  now = Date.now(),
  storage: Storage = localStorage,
): PendingReviewInfo {
  if (guestMode) {
    const info = metadata(storage);
    if (info.expiresAt !== null && info.expiresAt <= now) {
      expireInfo(info, storage);
      return { ...emptyInfo };
    }
    pendingReviewInfo.set(info);
    return info;
  }
  const pending = readPending(now, storage);
  const previous = metadata(storage);
  const info = pending
    ? {
        count: pending.payload.items.length,
        ownerId: pending.ownerId,
        email: previous.ownerId === pending.ownerId ? previous.email : null,
        expiresAt: pending.expiresAt,
      }
    : { ...emptyInfo };
  pendingReviewInfo.set(info);
  return info;
}
export function createPendingSubmission(
  ownerId: number,
  payload: ReviewSubmission,
  now = Date.now(),
  idempotencyKey = crypto.randomUUID(),
): PendingReviewSubmission {
  return {
    version: 2,
    ownerId,
    idempotencyKey,
    payload,
    createdAt: now,
    expiresAt: now + PENDING_REVIEW_TTL_MS,
  };
}
export function savePendingSubmission(
  pending: PendingReviewSubmission,
  storage: Storage = localStorage,
): void {
  if (guestMode) return;
  storage.setItem(PENDING_REVIEW_STORAGE_KEY, JSON.stringify(pending));
  const current = get(pendingReviewInfo);
  let email = current.ownerId === pending.ownerId ? current.email : null;
  try {
    const profile: unknown = JSON.parse(
      storage.getItem("el_auth_profile_v1") ?? "null",
    );
    if (
      typeof profile === "object" &&
      profile !== null &&
      "id" in profile &&
      profile.id === pending.ownerId &&
      "email" in profile &&
      typeof profile.email === "string"
    )
      email = profile.email;
  } catch {
    /* Display metadata is optional; answers remain intact. */
  }
  const info = {
    count: pending.payload.items.length,
    ownerId: pending.ownerId,
    email,
    expiresAt: pending.expiresAt,
  };
  storage.setItem(PENDING_REVIEW_METADATA_KEY, JSON.stringify(info));
  pendingReviewInfo.set(info);
}
export function loadPendingSubmission(
  ownerId: number,
  now = Date.now(),
  storage: Storage = localStorage,
): PendingReviewSubmission | null {
  if (guestMode) return null;
  const pending = readPending(now, storage);
  if (pending && pending.ownerId !== ownerId) {
    clearPendingSubmission(storage);
    return null;
  }
  if (pending) inspectPendingReviews(now, storage);
  return pending;
}
export function clearPendingSubmission(storage: Storage = localStorage): void {
  if (guestMode) return;
  storage.removeItem(PENDING_REVIEW_STORAGE_KEY);
  storage.removeItem(PENDING_REVIEW_METADATA_KEY);
  pendingReviewInfo.set({ ...emptyInfo });
}
export function reconcilePendingOwner(
  ownerId: number,
  email: string,
  storage: Storage = localStorage,
): { cleared: number; previousEmail?: string } {
  if (guestMode) return { cleared: 0 };
  const info = inspectPendingReviews(Date.now(), storage);
  if (info.ownerId !== null && info.ownerId !== ownerId) {
    clearPendingSubmission(storage);
    return {
      cleared: info.count,
      ...(info.email ? { previousEmail: info.email } : {}),
    };
  }
  const next = { ...info, ownerId, email };
  pendingReviewInfo.set(next);
  if (next.count)
    storage.setItem(PENDING_REVIEW_METADATA_KEY, JSON.stringify(next));
  return { cleared: 0 };
}
