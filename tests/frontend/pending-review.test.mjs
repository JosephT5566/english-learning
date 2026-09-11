import assert from 'node:assert/strict';
import test from 'node:test';

import {
	PENDING_REVIEW_STORAGE_KEY,
	PENDING_REVIEW_TTL_MS,
	clearPendingSubmission,
	createPendingSubmission,
	loadPendingSubmission,
	savePendingSubmission,
} from '../../src/lib/review/pending.ts';

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

const payload = {
	items: [
		{
			card_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
			decision: 'yes',
			expected_version: 3,
		},
	],
};

test('an ambiguous retry reloads the exact logical command', () => {
	const storage = new MemoryStorage();
	const pending = createPendingSubmission(
		'google-user-a',
		payload,
		1_000,
		'11111111-1111-4111-8111-111111111111'
	);
	savePendingSubmission(pending, storage);

	assert.deepEqual(loadPendingSubmission('google-user-a', 2_000, storage), pending);
	assert.equal(pending.expiresAt, 1_000 + PENDING_REVIEW_TTL_MS);
});

test('an expired pending command is removed', () => {
	const storage = new MemoryStorage();
	const pending = createPendingSubmission('google-user-a', payload, 1_000, crypto.randomUUID());
	savePendingSubmission(pending, storage);

	assert.equal(loadPendingSubmission('google-user-a', pending.expiresAt, storage), null);
	assert.equal(storage.getItem(PENDING_REVIEW_STORAGE_KEY), null);
});

test('switching accounts removes the previous owners command without returning it', () => {
	const storage = new MemoryStorage();
	savePendingSubmission(
		createPendingSubmission('google-user-a', payload, 1_000, crypto.randomUUID()),
		storage
	);

	assert.equal(loadPendingSubmission('google-user-b', 2_000, storage), null);
	assert.equal(storage.getItem(PENDING_REVIEW_STORAGE_KEY), null);
});

test('success cleanup removes the pending command', () => {
	const storage = new MemoryStorage();
	savePendingSubmission(
		createPendingSubmission('google-user-a', payload, 1_000, crypto.randomUUID()),
		storage
	);
	clearPendingSubmission(storage);

	assert.equal(storage.getItem(PENDING_REVIEW_STORAGE_KEY), null);
});

test('malformed or duplicate persisted items are rejected and removed', () => {
	const storage = new MemoryStorage();
	const pending = createPendingSubmission('google-user-a', payload, 1_000, crypto.randomUUID());
	pending.payload.items.push({ ...pending.payload.items[0] });
	storage.setItem(PENDING_REVIEW_STORAGE_KEY, JSON.stringify(pending));

	assert.equal(loadPendingSubmission('google-user-a', 2_000, storage), null);
	assert.equal(storage.getItem(PENDING_REVIEW_STORAGE_KEY), null);
});
