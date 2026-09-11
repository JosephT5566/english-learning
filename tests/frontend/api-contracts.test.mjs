import assert from 'node:assert/strict';
import test from 'node:test';

import { isApiErrorEnvelope, isDueCardPage, isReviewResult } from '../../src/lib/api/contracts.ts';

const state = {
	review_stage: 2,
	ease_factor: '2.40',
	interval_days: 3,
	last_reviewed_at: null,
	next_review_at: '2026-09-11T00:00:00Z',
	version: 4,
};

test('accepts the FastAPI due-review envelope and rejects legacy fields', () => {
	const due = {
		items: [
			{
				id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
				deck: {
					id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
					title: 'English',
					target_language: 'en',
					explanation_language: 'zh-TW',
					archived_at: null,
				},
				term: 'safe',
				meaning: '安全的',
				reading: null,
				pronunciation: null,
				romanization: null,
				part_of_speech: 'adjective',
				archived_at: null,
				version: 1,
				updated_at: '2026-09-11T00:00:00Z',
				target_language_definition: null,
				example_sentence: null,
				example_translation: null,
				example_source: null,
				synonyms: [],
				antonyms: [],
				part_of_speech_detail: null,
				note: null,
				supplementary_note: null,
				learned_on: null,
				created_at: '2026-09-01T00:00:00Z',
				tags: [],
				review_state: state,
			},
		],
		next_cursor: null,
	};
	assert.equal(isDueCardPage(due), true);
	assert.equal(isDueCardPage({ ok: true, result: [{ reviewStage: 2 }] }), false);
});

test('accepts the stable API error envelope', () => {
	assert.equal(
		isApiErrorEnvelope({
			error: {
				code: 'stale_review_state',
				message: 'Changed.',
				retryable: false,
				request_id: '22222222-2222-4222-8222-222222222222',
				details: { item_index: 0 },
			},
		}),
		true
	);
});

test('requires a complete review result before success can be shown', () => {
	const result = {
		batch_id: '33333333-3333-4333-8333-333333333333',
		reviewed_at: '2026-09-11T00:00:00Z',
		algorithm_version: 'srs-v1',
		items: [
			{
				event_id: 1,
				card_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
				decision: 'yes',
				quality: 5,
				previous_state: state,
				resulting_state: { ...state, version: 5 },
			},
		],
	};
	assert.equal(isReviewResult(result), true);
	assert.equal(isReviewResult({ batch_id: result.batch_id }), false);
});
