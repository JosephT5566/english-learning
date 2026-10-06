import { afterEach, describe, expect, it, vi } from 'vitest';
import { createCards } from '$lib/api/client';
import { CARD_OPTIONAL_TEXT_FIELDS } from '$lib/management/json-cards';

vi.mock('$env/dynamic/public', () => ({
	env: { PUBLIC_API_BASE_URL: 'https://api.example.test' },
}));
vi.mock('$lib/auth', () => ({ getTokenIfValid: () => 'test-token', signOut: vi.fn() }));
afterEach(() => vi.unstubAllGlobals());

const fields = { term: 'learn', meaning: 'study', synonyms: [], antonyms: [] };
const payload = {
	cards: [
		{ idempotency_key: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', fields },
		{ idempotency_key: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', fields },
	],
};
const results = payload.cards.map((item, index) => ({
	idempotency_key: item.idempotency_key,
	card: {
		...Object.fromEntries(CARD_OPTIONAL_TEXT_FIELDS.map((field) => [field, null])),
		...fields,
		id: `card-${index}`,
		deck: {
			id: 'deck',
			title: 'Words',
			target_language: 'en',
			explanation_language: 'zh-TW',
			archived_at: null,
		},
		part_of_speech: null,
		version: 1,
		archived_at: null,
		created_at: '2026-10-06T00:00:00Z',
		updated_at: '2026-10-06T00:00:00Z',
		tags: [],
		review_state: {
			review_stage: 1,
			ease_factor: '2.50',
			interval_days: 0,
			last_reviewed_at: null,
			next_review_at: '2026-10-06T00:00:00Z',
			version: 1,
		},
	},
}));

describe('bulk card API client', () => {
	it('sends all selected fields and stable keys in one deck-scoped request', async () => {
		const fetch = vi
			.fn()
			.mockResolvedValue(new Response(JSON.stringify({ cards: results }), { status: 201 }));
		vi.stubGlobal('fetch', fetch);
		expect(await createCards('deck', payload)).toEqual(results.map((item) => item.card));
		expect(fetch).toHaveBeenCalledTimes(1);
		expect(fetch).toHaveBeenCalledWith(
			'https://api.example.test/v1/decks/deck/cards/bulk',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify(payload),
				headers: { 'Content-Type': 'application/json', Authorization: 'Bearer test-token' },
			}),
		);
	});
	it.each([
		{},
		{ cards: [results[0]] },
		{ cards: [...results].reverse() },
		{ cards: [results[0], { ...results[1], card: results[0].card }] },
		{
			cards: [
				results[0],
				{
					...results[1],
					card: { ...results[1].card, deck: { ...results[1].card.deck, id: 'foreign' } },
				},
			],
		},
		{ cards: [results[0], { ...results[1], card: { id: 'invalid' } }] },
	])('retains uncertainty for incomplete or uncorrelated responses %j', async (response) => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue(new Response(JSON.stringify(response), { status: 201 })),
		);
		await expect(createCards('deck', payload)).rejects.toMatchObject({
			kind: 'invalid_response',
			retryable: true,
		});
	});
});
