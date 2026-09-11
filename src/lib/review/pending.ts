import type { ReviewSubmission } from '../api/contracts';

export const PENDING_REVIEW_STORAGE_KEY = 'pending_review_submission_v1';
export const PENDING_REVIEW_TTL_MS = 24 * 60 * 60 * 1000;

export interface PendingReviewSubmission {
	version: 1;
	ownerSubject: string;
	idempotencyKey: string;
	payload: ReviewSubmission;
	createdAt: number;
	expiresAt: number;
}

function isPendingSubmission(value: unknown): value is PendingReviewSubmission {
	if (typeof value !== 'object' || value === null) return false;
	const pending = value as Partial<PendingReviewSubmission>;
	const items = pending.payload?.items;
	const decisions = new Set(['no', 'no_a_bit', 'yes_a_bit', 'yes']);
	return (
		pending.version === 1 &&
		typeof pending.ownerSubject === 'string' &&
		pending.ownerSubject.length > 0 &&
		typeof pending.idempotencyKey === 'string' &&
		/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
			pending.idempotencyKey
		) &&
		typeof pending.createdAt === 'number' &&
		Number.isFinite(pending.createdAt) &&
		typeof pending.expiresAt === 'number' &&
		Number.isFinite(pending.expiresAt) &&
		pending.expiresAt === pending.createdAt + PENDING_REVIEW_TTL_MS &&
		Array.isArray(items) &&
		items.length >= 1 &&
		items.length <= 10 &&
		items.every(
			(item) =>
				typeof item === 'object' &&
				item !== null &&
				typeof item.card_id === 'string' &&
				decisions.has(item.decision) &&
				Number.isInteger(item.expected_version) &&
				item.expected_version >= 1
		) &&
		new Set(items.map((item) => item.card_id)).size === items.length
	);
}

export function createPendingSubmission(
	ownerSubject: string,
	payload: ReviewSubmission,
	now = Date.now(),
	idempotencyKey = crypto.randomUUID()
): PendingReviewSubmission {
	return {
		version: 1,
		ownerSubject,
		idempotencyKey,
		payload,
		createdAt: now,
		expiresAt: now + PENDING_REVIEW_TTL_MS,
	};
}

export function savePendingSubmission(
	pending: PendingReviewSubmission,
	storage: Storage = localStorage
): void {
	storage.setItem(PENDING_REVIEW_STORAGE_KEY, JSON.stringify(pending));
}

export function loadPendingSubmission(
	ownerSubject: string,
	now = Date.now(),
	storage: Storage = localStorage
): PendingReviewSubmission | null {
	const raw = storage.getItem(PENDING_REVIEW_STORAGE_KEY);
	if (!raw) return null;
	try {
		const pending: unknown = JSON.parse(raw);
		if (
			!isPendingSubmission(pending) ||
			pending.expiresAt <= now ||
			pending.ownerSubject !== ownerSubject
		) {
			storage.removeItem(PENDING_REVIEW_STORAGE_KEY);
			return null;
		}
		return pending;
	} catch {
		storage.removeItem(PENDING_REVIEW_STORAGE_KEY);
		return null;
	}
}

export function clearPendingSubmission(storage: Storage = localStorage): void {
	storage.removeItem(PENDING_REVIEW_STORAGE_KEY);
}
