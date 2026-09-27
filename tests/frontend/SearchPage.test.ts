import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import SearchPage from '../../src/routes/search/+page.svelte';

const api = vi.hoisted(() => ({
	keywordSearch: vi.fn(),
	semanticSearch: vi.fn(),
}));

vi.mock('$lib/api/client', () => ({
	ApiClientError: class ApiClientError extends Error {},
	keywordSearch: api.keywordSearch,
	semanticSearch: api.semanticSearch,
}));

const japaneseCard = {
	id: '20000000-0000-0000-0000-000000000002',
	deck: {
		id: '10000000-0000-0000-0000-000000000002',
		title: 'Japanese',
		target_language: 'ja',
		explanation_language: 'zh-TW',
		archived_at: null,
	},
	term: '勉強',
	meaning: '學習',
	reading: 'べんきょう',
	pronunciation: null,
	romanization: 'benkyou',
	part_of_speech: 'noun',
	archived_at: null,
	version: 1,
	updated_at: '2026-09-01T00:00:00Z',
};

describe('Search page', () => {
	beforeEach(() => {
		api.keywordSearch.mockReset();
		api.semanticSearch.mockReset();
		api.keywordSearch.mockResolvedValue({ items: [japaneseCard], next_cursor: null });
		api.semanticSearch.mockResolvedValue({
			items: [],
			index_status: 'complete',
			eligible_count: 1,
			indexed_count: 1,
		});
	});

	it('defaults to multilingual keyword search and labels Japanese results', async () => {
		render(SearchPage);

		expect(screen.getByRole('button', { name: 'Keyword' })).toHaveAttribute('aria-pressed', 'true');
		expect(screen.queryByText('English cards only')).not.toBeInTheDocument();

		await fireEvent.input(screen.getByLabelText('Word or meaning'), {
			target: { value: 'benkyou' },
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Search' }));

		await waitFor(() => expect(api.keywordSearch).toHaveBeenCalledWith('benkyou'));
		expect(screen.getByText('勉強')).toBeInTheDocument();
		expect(screen.getByText('JP')).toBeInTheDocument();
		expect(api.semanticSearch).not.toHaveBeenCalled();
	});

	it('preserves the query when switching to English-only semantic search', async () => {
		render(SearchPage);
		const input = screen.getByLabelText('Word or meaning');
		await fireEvent.input(input, { target: { value: 'a lucky discovery' } });

		await fireEvent.click(screen.getByRole('button', { name: 'Search by meaning' }));

		expect(screen.getByText('English cards only')).toBeInTheDocument();
		expect(screen.getByLabelText('Meaning or concept')).toHaveValue('a lucky discovery');
		await fireEvent.click(screen.getByRole('button', { name: 'Search' }));

		await waitFor(() =>
			expect(api.semanticSearch).toHaveBeenCalledWith({
				query: 'a lucky discovery',
				target_language: 'en',
				limit: 10,
			}),
		);
		expect(api.keywordSearch).not.toHaveBeenCalled();
	});
});
