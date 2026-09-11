import assert from 'node:assert/strict';
import test from 'node:test';

import {
	PENDING_MANAGEMENT_STORAGE_KEY,
	PENDING_MANAGEMENT_TTL_MS,
	clearPendingManagement,
	createPendingManagement,
	loadPendingManagement,
	savePendingManagement,
} from '../../src/lib/management/pending.ts';

class MemoryStorage {
	values = new Map();
	getItem(key) {
		return this.values.get(key) ?? null;
	}
	setItem(key, value) {
		this.values.set(key, value);
	}
	removeItem(key) {
		this.values.delete(key);
	}
}

const deckPayload = {
	title: 'Japanese foundations',
	target_language: 'ja',
	explanation_language: 'zh-TW',
};

test('an ambiguous deck creation restores the exact account-scoped command', () => {
	const storage = new MemoryStorage();
	const pending = createPendingManagement(
		'owner-a',
		'deck',
		deckPayload,
		1_000,
		'11111111-1111-4111-8111-111111111111',
	);
	savePendingManagement(pending, storage);

	assert.deepEqual(loadPendingManagement('owner-a', 2_000, storage), pending);
	assert.equal(pending.expiresAt, 1_000 + PENDING_MANAGEMENT_TTL_MS);
});

test('expired, cross-account, and malformed creations are removed', () => {
	const storage = new MemoryStorage();
	const pending = createPendingManagement(
		'owner-a',
		'deck',
		deckPayload,
		1_000,
		'11111111-1111-4111-8111-111111111111',
	);
	savePendingManagement(pending, storage);
	assert.equal(loadPendingManagement('owner-a', pending.expiresAt, storage), null);

	savePendingManagement(pending, storage);
	assert.equal(loadPendingManagement('owner-b', 2_000, storage), null);

	storage.setItem(PENDING_MANAGEMENT_STORAGE_KEY, JSON.stringify({ ...pending, payload: {} }));
	assert.equal(loadPendingManagement('owner-a', 2_000, storage), null);
});

test('confirmed creation cleanup removes the pending command', () => {
	const storage = new MemoryStorage();
	savePendingManagement(createPendingManagement('owner-a', 'deck', deckPayload), storage);
	clearPendingManagement(storage);
	assert.equal(storage.getItem(PENDING_MANAGEMENT_STORAGE_KEY), null);
});
