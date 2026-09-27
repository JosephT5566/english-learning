import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

import CardForm from '$lib/components/CardForm.svelte';

describe('CardForm', () => {
	it('keeps the core task visible and submits optional words as arrays', async () => {
		const onsave = vi.fn();
		render(CardForm, {
			props: {
				language: 'en',
				onsave,
				oncancel: vi.fn(),
			},
		});

		expect(screen.getByLabelText('Term')).toBeVisible();
		expect(screen.getByLabelText('Meaning')).toBeVisible();
		expect(screen.getByLabelText('Pronunciation')).not.toBeVisible();

		await fireEvent.input(screen.getByLabelText('Term'), { target: { value: 'resilient' } });
		await fireEvent.input(screen.getByLabelText('Meaning'), { target: { value: '有復原力的' } });
		await fireEvent.click(screen.getByText('Related words').closest('summary')!);

		const synonymInput = screen.getByLabelText('Synonyms');
		await fireEvent.input(synonymInput, { target: { value: 'robust' } });
		await fireEvent.keyDown(synonymInput, { key: 'Enter' });
		expect(screen.getByRole('button', { name: 'Remove synonym robust' })).toBeInTheDocument();

		await fireEvent.click(screen.getByRole('button', { name: 'Save card' }));

		await waitFor(() =>
			expect(onsave).toHaveBeenCalledWith(
				expect.objectContaining({
					term: 'resilient',
					meaning: '有復原力的',
					synonyms: ['robust'],
					antonyms: [],
				}),
			),
		);
	});

	it('keeps Japanese reading in the essential flow', () => {
		render(CardForm, {
			props: {
				language: 'ja',
				onsave: vi.fn(),
				oncancel: vi.fn(),
			},
		});

		expect(screen.getByLabelText('Reading')).toBeVisible();
	});
});
