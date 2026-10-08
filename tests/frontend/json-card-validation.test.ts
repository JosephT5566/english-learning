import { describe, expect, it } from 'vitest';
import { validateCardJson } from '$lib/management/json-card-validation';

const card = { term: 'learn', meaning: 'study' };
function check(fields: object) {
	return validateCardJson(JSON.stringify({ cards: [{ ...card, ...fields }] }));
}

describe('local Pydantic-schema validation', () => {
	it('accepts minimal English and Japanese cards and normalizes constrained strings', () => {
		expect(check({})).toMatchObject({ valid: true });
		expect(
			check({
				term: ' 学ぶ ',
				meaning: ' 學習 ',
				reading: ' まなぶ ',
				synonyms: [' 知る '],
			}),
		).toMatchObject({
			valid: true,
			value: {
				cards: [
					{
						term: '学ぶ',
						meaning: '學習',
						reading: 'まなぶ',
						synonyms: ['知る'],
					},
				],
			},
		});
		expect(check({ term: 'x'.repeat(255) + '  ' })).toMatchObject({
			valid: true,
		});
	});
	it.each([
		{ cards: [] },
		{ cards: Array.from({ length: 21 }, () => card) },
		{ cards: [{ meaning: 'study' }] },
		{ cards: [{ ...card, term: '   ' }] },
		{ cards: [{ ...card, meaning: 42 }] },
		{ cards: [{ ...card, term: 'x'.repeat(256) }] },
		{ cards: [{ ...card, owner_id: 1 }] },
		{ cards: [{ ...card, synonyms: 'x' }] },
		{ cards: [{ ...card, antonyms: null }] },
		{ cards: [{ ...card, synonyms: [' '] }] },
		{ cards: [{ ...card, synonyms: Array.from({ length: 21 }, () => 'x') }] },
		{ cards: [{ ...card, part_of_speech: 'unknown' }] },
		{ cards: [{ ...card, learned_on: '2026-02-29' }] },
		{ cards: [{ ...card, learned_on: '2026-10-06T00:00:00Z' }] },
		{ cards: [{ ...card, example_translation: 'translation' }] },
		{ cards: [{ ...card, example_source: 'source', example_sentence: null }] },
		{
			cards: [{ ...card, part_of_speech: 'other', part_of_speech_detail: null }],
		},
		{ cards: [card], target_language: 'ja' },
	])('rejects invalid content before a request: %j', (value) => {
		expect(validateCardJson(JSON.stringify(value))).toMatchObject({
			valid: false,
		});
	});
	it('allows null optional values, leap dates, and fulfilled dependencies', () => {
		expect(
			check({
				learned_on: '2024-02-29',
				example_source: null,
				example_translation: null,
			}),
		).toMatchObject({ valid: true });
		expect(
			check({
				example_sentence: 'We learn.',
				example_translation: '我們學習。',
				part_of_speech: 'other',
				part_of_speech_detail: 'expression',
			}),
		).toMatchObject({ valid: true });
	});
	it('reports the actual card and field with actionable errors', () => {
		const result = validateCardJson(
			JSON.stringify({
				cards: [card, { term: 'x', learned_on: '2026-99-99', owner_id: 4 }],
			}),
		);
		expect(result).toMatchObject({
			valid: false,
			messages: expect.arrayContaining([
				'Card 2 · meaning: This field is required.',
				'Card 2 · owner_id: Remove this unsupported field.',
				'Card 2 · learned_on: Use a valid date in YYYY-MM-DD format.',
			]),
		});
	});
	it.each(['{\r\n"cards": @}', '{"cards": [}', '{"cards": [],}', '{/* comment */"cards": []}'])(
		'locates strict JSON syntax failures: %s',
		(source) => {
			const result = validateCardJson(source);
			expect(result.valid).toBe(false);
			if (result.valid) return;
			expect(result.issues?.[0].location).toBeDefined();
		},
	);
	it('locates a CRLF error and EOF without relying on browser exception messages', () => {
		const result = validateCardJson('{\r\n"cards": @}');
		expect(result).toMatchObject({
			valid: false,
			issues: [{ location: { offset: 12, line: 2, column: 10 } }],
		});
		expect(validateCardJson('{')).toMatchObject({
			valid: false,
			issues: [{ location: { offset: 1, length: 0, line: 1, column: 2 } }],
		});
	});
	it('points missing fields at their containing card and escapes JSON pointer property names', () => {
		const source = '{"cards":[{"term":"learn","a/b~c":1}]}';
		const result = validateCardJson(source);
		if (result.valid) throw new Error('Expected invalid input');
		const missing = result.issues?.find((issue) => issue.message.includes('meaning'));
		expect(missing?.location).toMatchObject({ offset: 10, length: 1 });
		const extra = result.issues?.find((issue) => issue.message.includes('a/b~c'));
		expect(
			source.slice(extra!.location!.offset, extra!.location!.offset + extra!.location!.length),
		).toBe('1');
	});
	it('rejects deeply nested unsupported input without crashing error location parsing', () => {
		const source = '{"cards":[],"extra":' + '['.repeat(10_000) + '0' + ']'.repeat(10_000) + '}';
		expect(validateCardJson(source)).toMatchObject({ valid: false });
	});
	it('rejects malformed JSON and excessive byte size', () => {
		expect(validateCardJson('{')).toMatchObject({ valid: false });
		expect(check({ note: '字'.repeat(34_000) })).toMatchObject({
			valid: false,
			messages: ['JSON must be at most 100,000 bytes.'],
		});
	});
});
