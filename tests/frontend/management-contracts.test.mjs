import assert from 'node:assert/strict';
import test from 'node:test';

import {
	isCardDetail,
	isCardSummaryPage,
	isDeck,
	isDeckPage,
} from '../../src/lib/api/contracts.ts';
import { readArchiveStatus, readLanguageQuery } from '../../src/lib/management/navigation.ts';

const deck = {
	id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
	title: 'English foundations',
	target_language: 'en',
	explanation_language: 'zh-TW',
	archived_at: null,
	version: 3,
	created_at: '2026-09-01T00:00:00Z',
	updated_at: '2026-09-11T00:00:00Z',
};

const card = {
	id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
	deck: {
		id: deck.id,
		title: deck.title,
		target_language: deck.target_language,
		explanation_language: deck.explanation_language,
		archived_at: null,
	},
	term: 'resilient',
	meaning: '有復原力的',
	reading: null,
	pronunciation: '/rɪˈzɪliənt/',
	romanization: null,
	part_of_speech: 'adjective',
	archived_at: null,
	version: 2,
	updated_at: '2026-09-11T00:00:00Z',
	target_language_definition: 'able to recover quickly',
	example_sentence: 'The service is resilient.',
	example_translation: null,
	example_source: null,
	synonyms: ['robust'],
	antonyms: ['fragile'],
	part_of_speech_detail: null,
	note: null,
	supplementary_note: null,
	learned_on: '2026-09-11',
	created_at: '2026-09-01T00:00:00Z',
	tags: [],
	review_state: {
		review_stage: 1,
		ease_factor: '2.50',
		interval_days: 0,
		last_reviewed_at: null,
		next_review_at: '2026-09-12T00:00:00Z',
		version: 1,
	},
};

test('generated management shapes are still guarded at runtime', () => {
	assert.equal(isDeck(deck), true);
	assert.equal(isDeckPage({ items: [deck], next_cursor: null }), true);
	assert.equal(isCardSummaryPage({ items: [card], next_cursor: null }), true);
	assert.equal(isCardDetail(card), true);
	assert.equal(isDeck({ ...deck, version: 0 }), false);
	assert.equal(isCardDetail({ ...card, tags: [{ display_name: 'missing id' }] }), false);
});

test('language and archive query state is explicit', () => {
	assert.deepEqual(readLanguageQuery(new URLSearchParams()), {
		kind: 'missing',
		language: 'en',
	});
	assert.deepEqual(readLanguageQuery(new URLSearchParams('language=ja')), {
		kind: 'valid',
		language: 'ja',
	});
	assert.deepEqual(readLanguageQuery(new URLSearchParams('language=fr')), {
		kind: 'invalid',
		language: null,
	});
	assert.equal(readArchiveStatus(new URLSearchParams('status=archived')), 'archived');
	assert.equal(readArchiveStatus(new URLSearchParams('status=unknown')), 'active');
});
