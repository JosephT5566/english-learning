import { afterEach, describe, expect, it, vi } from 'vitest';
import { validateCardDrafts } from '$lib/api/client';

vi.mock('$env/dynamic/public', () => ({
	env: { PUBLIC_API_BASE_URL: 'https://api.example.test' },
}));
vi.mock('$lib/auth', () => ({ getTokenIfValid: () => 'test-token', signOut: vi.fn() }));
const fields = { term: 'learn', meaning: 'study', synonyms: [], antonyms: [] };
afterEach(() => vi.unstubAllGlobals());

describe('JSON draft API client', () => {
	it('puts deck context in the route and sends only content to the validation boundary', async () => {
		const fetch = vi
			.fn()
			.mockResolvedValue(new Response(JSON.stringify({ cards: [fields] }), { status: 200 }));
		vi.stubGlobal('fetch', fetch);
		expect(await validateCardDrafts('selected-deck', { cards: [fields] })).toEqual([fields]);
		expect(fetch).toHaveBeenCalledWith(
			'https://api.example.test/v1/decks/selected-deck/card-drafts/validate',
			expect.objectContaining({
				method: 'POST',
				headers: { 'Content-Type': 'application/json', Authorization: 'Bearer test-token' },
				body: JSON.stringify({ cards: [fields] }),
			}),
		);
	});
	it.each([
		{ cards: [] },
		{ cards: [fields, fields] },
		{ cards: [{ ...fields, owner_id: 3 }] },
		{ cards: [{ ...fields, synonyms: null }] },
	])('rejects malformed or mismatched successful responses %j', async (response) => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue(new Response(JSON.stringify(response), { status: 200 })),
		);
		await expect(validateCardDrafts('deck', { cards: [fields] })).rejects.toMatchObject({
			kind: 'invalid_response',
		});
	});
});
