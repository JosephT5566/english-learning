import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

import CardForm from '$lib/components/CardForm.svelte';

describe('CardForm', () => {
	it.each([
		['Word details', 'Pronunciation'],
		['Example', 'Example sentence'],
		['Related words', 'Synonyms'],
		['Notes', 'Note'],
	])('preserves the user-controlled %s disclosure while editing', async (section, label) => {
		render(CardForm, { props: { language: 'en', onsave: vi.fn(), oncancel: vi.fn() } });
		const details = screen.getByText(section, { exact: true }).closest('details')!;
		details.open = true;
		await fireEvent(details, new Event('toggle'));
		await fireEvent.input(screen.getByLabelText(label, { exact: true }), {
			target: { value: 'a' },
		});
		expect(details.open).toBe(true);
		details.open = false;
		await fireEvent(details, new Event('toggle'));
		await fireEvent.input(screen.getByLabelText('Term'), { target: { value: 'word' } });
		expect(details.open).toBe(false);
	});

	it('keeps pending words on blur, ignores IME confirmation, and adds with Enter or comma', async () => {
		const onsave = vi.fn();
		render(CardForm, {
			props: {
				language: 'ja',
				onsave,
				oncancel: vi.fn(),
				draft: { term: '学ぶ', meaning: 'study', synonyms: ['知る'], antonyms: [] },
			},
		});
		const synonym = screen.getByLabelText('Synonyms');
		await fireEvent.input(synonym, { target: { value: '習う' } });
		await fireEvent.blur(synonym);
		expect(synonym).toHaveValue('習う');
		expect(screen.queryByRole('button', { name: 'Remove synonym 習う' })).not.toBeInTheDocument();
		await fireEvent.keyDown(synonym, { key: 'Enter', isComposing: true });
		expect(synonym).toHaveValue('習う');
		expect(onsave).not.toHaveBeenCalled();
		await fireEvent.keyDown(synonym, { key: 'Enter' });
		expect(screen.getByRole('button', { name: 'Remove synonym 習う' })).toBeVisible();
		await fireEvent.input(screen.getByLabelText('Antonyms'), { target: { value: '忘れる' } });
		await fireEvent.keyDown(screen.getByLabelText('Antonyms'), { key: ',' });
		expect(screen.getByRole('button', { name: 'Remove antonym 忘れる' })).toBeVisible();
	});

	it('includes unconfirmed related-word text only when saving the form', async () => {
		const onsave = vi.fn();
		render(CardForm, {
			props: {
				language: 'en',
				onsave,
				oncancel: vi.fn(),
				draft: { term: 'steady', meaning: 'stable', synonyms: ['reliable'], antonyms: [] },
			},
		});
		await fireEvent.input(screen.getByLabelText('Synonyms'), {
			target: { value: 'reliable, consistent' },
		});
		await fireEvent.input(screen.getByLabelText('Antonyms'), { target: { value: 'unstable' } });
		expect(
			screen.queryByRole('button', { name: 'Remove synonym consistent' }),
		).not.toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: 'Save card' }));
		expect(onsave).toHaveBeenCalledWith(
			expect.objectContaining({ synonyms: ['reliable', 'consistent'], antonyms: ['unstable'] }),
		);
	});
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
