import type { CardCreate, DeckCreate } from '$lib/api/contracts';

export const PENDING_MANAGEMENT_STORAGE_KEY = 'pending_management_creation_v1';
export const PENDING_MANAGEMENT_TTL_MS = 24 * 60 * 60 * 1000;

export type PendingManagementCreation = {
	version: 1;
	ownerSubject: string;
	kind: 'deck' | 'card';
	idempotencyKey: string;
	payload: DeckCreate | CardCreate;
	createdAt: number;
	expiresAt: number;
};

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isDeckPayload(value: unknown): value is DeckCreate {
	return (
		isRecord(value) &&
		typeof value.title === 'string' &&
		(value.target_language === 'en' || value.target_language === 'ja') &&
		(value.explanation_language === 'en' ||
			value.explanation_language === 'ja' ||
			value.explanation_language === 'zh-TW')
	);
}

function isCardPayload(value: unknown): value is CardCreate {
	return (
		isRecord(value) &&
		typeof value.deck_id === 'string' &&
		typeof value.term === 'string' &&
		typeof value.meaning === 'string' &&
		Array.isArray(value.synonyms) &&
		value.synonyms.every((item) => typeof item === 'string') &&
		Array.isArray(value.antonyms) &&
		value.antonyms.every((item) => typeof item === 'string')
	);
}

function isPending(value: unknown): value is PendingManagementCreation {
	if (!isRecord(value)) return false;
	const item = value as Partial<PendingManagementCreation>;
	return (
		item.version === 1 &&
		typeof item.ownerSubject === 'string' &&
		(item.kind === 'deck' || item.kind === 'card') &&
		typeof item.idempotencyKey === 'string' &&
		/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
			item.idempotencyKey,
		) &&
		((item.kind === 'deck' && isDeckPayload(item.payload)) ||
			(item.kind === 'card' && isCardPayload(item.payload))) &&
		typeof item.createdAt === 'number' &&
		typeof item.expiresAt === 'number' &&
		item.expiresAt === item.createdAt + PENDING_MANAGEMENT_TTL_MS
	);
}

export function createPendingManagement(
	ownerSubject: string,
	kind: 'deck' | 'card',
	payload: DeckCreate | CardCreate,
	now = Date.now(),
	idempotencyKey = crypto.randomUUID(),
): PendingManagementCreation {
	return {
		version: 1,
		ownerSubject,
		kind,
		payload,
		idempotencyKey,
		createdAt: now,
		expiresAt: now + PENDING_MANAGEMENT_TTL_MS,
	};
}

export function savePendingManagement(
	pending: PendingManagementCreation,
	storage: Storage = localStorage,
): void {
	storage.setItem(PENDING_MANAGEMENT_STORAGE_KEY, JSON.stringify(pending));
}

export function loadPendingManagement(
	ownerSubject: string,
	now = Date.now(),
	storage: Storage = localStorage,
): PendingManagementCreation | null {
	const raw = storage.getItem(PENDING_MANAGEMENT_STORAGE_KEY);
	if (!raw) return null;
	try {
		const pending: unknown = JSON.parse(raw);
		if (!isPending(pending) || pending.ownerSubject !== ownerSubject || pending.expiresAt <= now) {
			storage.removeItem(PENDING_MANAGEMENT_STORAGE_KEY);
			return null;
		}
		return pending;
	} catch {
		storage.removeItem(PENDING_MANAGEMENT_STORAGE_KEY);
		return null;
	}
}

export function clearPendingManagement(storage: Storage = localStorage): void {
	storage.removeItem(PENDING_MANAGEMENT_STORAGE_KEY);
}
