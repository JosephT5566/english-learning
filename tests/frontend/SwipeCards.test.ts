import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

import SwipeCards from '$lib/components/SwipeCards.svelte';
import type { DueCard } from '$lib/api/contracts';

const card: DueCard = {
	id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
	deck: {
		id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
		title: 'English',
		target_language: 'en',
		explanation_language: 'zh-TW',
		archived_at: null,
	},
	term: 'resilient',
	meaning: '有復原力的',
	reading: null,
	pronunciation: '/rɪˈzɪliənt/',
	romanization: null,
	part_of_speech: 'adjective',
	archived_at: null,
	version: 1,
	updated_at: '2026-09-10T00:00:00Z',
	target_language_definition: 'able to recover quickly',
	example_sentence: 'The service is resilient to retries.',
	example_translation: null,
	example_source: null,
	synonyms: ['robust'],
	antonyms: ['fragile'],
	part_of_speech_detail: null,
	note: null,
	supplementary_note: null,
	learned_on: '2026-09-01',
	created_at: '2026-09-01T00:00:00Z',
	tags: [{ id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc', display_name: 'backend' }],
	review_state: {
		review_stage: 1,
		ease_factor: '2.50',
		interval_days: 0,
		last_reviewed_at: null,
		next_review_at: '2026-09-10T00:00:00Z',
		version: 7,
	},
};

describe('SwipeCards', () => {
	it('displays a preserved legacy part-of-speech label instead of canonical other', () => {
		const importedCard: DueCard = {
			...card,
			part_of_speech: 'other',
			part_of_speech_detail: 'vocabulary',
			note: 'informal',
		};

		render(SwipeCards, { props: { wordList: [importedCard] } });

		expect(screen.getByText('vocabulary', { exact: true })).toBeInTheDocument();
		expect(screen.queryByText('other', { exact: true })).not.toBeInTheDocument();
		expect(screen.getByText('informal', { exact: true })).toBeInTheDocument();
	});

	it('requires a flip before answering and emits only the backend command fields', async () => {
		const onAnswer = vi.fn();
		const { container } = render(SwipeCards, { props: { wordList: [card], onAnswer } });
		const yes = screen.getByRole('button', { name: 'Yes' });

		expect(yes).toBeDisabled();
		await fireEvent.click(container.querySelector('.swipe--card')!);
		expect(yes).toBeEnabled();
		await fireEvent.click(yes);

		await waitFor(() =>
			expect(onAnswer).toHaveBeenCalledWith({
				card_id: card.id,
				decision: 'yes',
				expected_version: 7,
			})
		);
		expect(screen.getByText('Your answers are ready to submit.')).toBeInTheDocument();
	});
});
