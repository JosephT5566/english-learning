import assert from 'node:assert/strict';
import test from 'node:test';
import {
	cardPrompt,
	loadJsonQueue,
	parseCardJson,
	saveJsonQueue,
	JSON_QUEUE_KEY,
} from '../../src/lib/management/json-cards.ts';

function storage() {
	const values = new Map();
	return {
		getItem: (key) => values.get(key) ?? null,
		setItem: (key, value) => values.set(key, value),
		removeItem: (key) => values.delete(key),
	};
}

test('prompt uses deck languages and excludes inappropriate pronunciation fields', () => {
	const english = cardPrompt({ target_language: 'en', explanation_language: 'zh-TW' });
	const japanese = cardPrompt({ target_language: 'ja', explanation_language: 'en' });
	assert.match(english, /Target language: English/);
	assert.match(english, /Traditional Chinese/);
	assert.match(english, /Optional fields: pronunciation/);
	assert.match(japanese, /Target language: Japanese/);
	assert.match(japanese, /Optional fields: reading and romanization/);
	assert.match(japanese, /Meanings and example translations: English/);
});

test('raw JSON byte bound includes multibyte characters and requires an object', () => {
	assert.throws(() => parseCardJson('[]'), /JSON object/);
	assert.throws(() => parseCardJson('```json\n{}'), /valid JSON/);
	assert.throws(
		() => parseCardJson(JSON.stringify({ cards: [{ term: '字'.repeat(34_000), meaning: 'x' }] })),
		/100,000 bytes/,
	);
	assert.deepEqual(parseCardJson('{"cards":[{"term":"x","meaning":"y"}]}'), {
		cards: [{ term: 'x', meaning: 'y' }],
	});
});

test('uncertain commands retain exact keys without expiry and are isolated by account', () => {
	const store = storage();
	const queue = {
		version: 1,
		owner: 'owner',
		deckId: 'deck',
		entries: [
			{
				fields: { term: 'x', meaning: 'y', synonyms: [], antonyms: [] },
				selected: true,
				key: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
				status: 'unconfirmed',
			},
		],
	};
	saveJsonQueue(queue, store);
	assert.deepEqual(loadJsonQueue('owner', store), queue);
	assert.equal(loadJsonQueue('another-owner', store), null);
	assert.equal(store.getItem(JSON_QUEUE_KEY), null);
});

test('malformed persisted commands cannot be sent', () => {
	const store = storage();
	store.setItem(
		JSON_QUEUE_KEY,
		JSON.stringify({
			version: 1,
			owner: 'owner',
			deckId: 'deck',
			entries: [
				{
					fields: { term: 'x', meaning: 'y', owner_id: 7 },
					selected: true,
					key: 'bad',
					status: 'unconfirmed',
				},
			],
		}),
	);
	assert.equal(loadJsonQueue('owner', store), null);
});
