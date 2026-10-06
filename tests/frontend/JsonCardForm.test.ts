import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import JsonCardForm from '$lib/components/JsonCardForm.svelte';
import { ApiClientError, createCard, validateCardDrafts } from '$lib/api/client';
import { JSON_QUEUE_KEY } from '$lib/management/json-cards';

vi.mock('$env/dynamic/public', () => ({
	env: { PUBLIC_API_BASE_URL: 'https://api.example.test' },
}));
vi.mock('$lib/auth', () => ({
	getProfile: () => ({ sub: 'owner' }),
	getTokenIfValid: vi.fn(),
	signOut: vi.fn(),
}));
vi.mock('$lib/api/client', async (original) => ({
	...(await original<typeof import('$lib/api/client')>()),
	createCard: vi.fn(),
	validateCardDrafts: vi.fn(),
}));
const deck = {
	id: 'deck',
	title: 'Words',
	target_language: 'en',
	explanation_language: 'zh-TW',
	version: 1,
	created_at: '',
	updated_at: '',
	archived_at: null,
} as const;
const drafts = [
	{ term: 'learn', meaning: 'study', synonyms: [], antonyms: [] },
	{ term: 'practice', meaning: 'repeat', synonyms: [], antonyms: [] },
];
function setup() {
	return render(JsonCardForm, {
		props: { deck, onbusy: vi.fn(), onqueue: vi.fn(), oncreated: vi.fn() },
	});
}
async function preview() {
	await fireEvent.input(screen.getByLabelText('Card JSON'), {
		target: { value: JSON.stringify({ cards: drafts }) },
	});
	await fireEvent.click(screen.getByRole('button', { name: 'Validate and preview' }));
	await screen.findByText('learn', { exact: true });
}

beforeEach(() => {
	localStorage.clear();
	vi.resetAllMocks();
	vi.mocked(validateCardDrafts).mockResolvedValue(structuredClone(drafts));
});

describe('JSON card authoring', () => {
	it('validates pasted card fields after a short delay without calling the backend', async () => {
		setup();
		const input = screen.getByLabelText('Card JSON');
		await fireEvent.input(input, { target: { value: '{"cards":[{"term":"learn"}]}' } });
		expect(await screen.findByText('Card 1 · meaning: This field is required.')).toBeVisible();
		expect(input).toHaveAttribute('aria-invalid', 'true');
		expect(screen.getByRole('button', { name: 'Validate and preview' })).toBeDisabled();
		expect(validateCardDrafts).not.toHaveBeenCalled();
		await fireEvent.input(input, { target: { value: JSON.stringify({ cards: [drafts[0]] }) } });
		expect(
			await screen.findByText('JSON format looks valid. Preview to check it with your deck.'),
		).toBeVisible();
		expect(input).not.toHaveAttribute('aria-invalid');
		expect(screen.getByRole('button', { name: 'Validate and preview' })).toBeEnabled();
		expect(validateCardDrafts).not.toHaveBeenCalled();
	});
	it('checks the latest input when typing replaces an invalid paste', async () => {
		setup();
		const input = screen.getByLabelText('Card JSON');
		await fireEvent.input(input, { target: { value: '{"cards":[{}]}' } });
		await fireEvent.input(input, { target: { value: JSON.stringify({ cards: [drafts[0]] }) } });
		expect(
			await screen.findByText('JSON format looks valid. Preview to check it with your deck.'),
		).toBeVisible();
		expect(screen.queryByText('Card 1 · meaning: This field is required.')).not.toBeInTheDocument();
		expect(validateCardDrafts).not.toHaveBeenCalled();
	});
	it('rejects invalid draft edits locally before confirmation calls', async () => {
		setup();
		await preview();
		await fireEvent.click(screen.getByRole('button', { name: 'Edit card 1' }));
		await fireEvent.input(screen.getByLabelText('Meaning'), { target: { value: '   ' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Apply draft edits' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Add selected cards (2)' }));
		expect(await screen.findByRole('alert')).toHaveTextContent(
			'Card 1 · meaning: Enter a nonblank value.',
		);
		expect(validateCardDrafts).toHaveBeenCalledOnce();
		expect(createCard).not.toHaveBeenCalled();
	});

	it('does not submit malformed JSON or create cards during preview', async () => {
		setup();
		await fireEvent.input(screen.getByLabelText('Card JSON'), {
			target: { value: '```json' },
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Validate and preview' }));
		expect(await screen.findByRole('alert')).toHaveTextContent('valid JSON');
		expect(validateCardDrafts).not.toHaveBeenCalled();
		await preview();
		expect(createCard).not.toHaveBeenCalled();
	});
	it('shows backend card and field errors', async () => {
		vi.mocked(validateCardDrafts).mockRejectedValue(
			new ApiClientError('Invalid', 'api', false, 422, 'validation_failed', undefined, {
				fields: [
					{
						path: ['body', 'cards', 1, 'meaning'],
						message: 'This field is required.',
					},
				],
			}),
		);
		setup();
		await fireEvent.input(screen.getByLabelText('Card JSON'), {
			target: { value: JSON.stringify({ cards: drafts }) },
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Validate and preview' }));
		expect(await screen.findByRole('alert')).toHaveTextContent('Card 2 · meaning');
	});
	it('submits only selected cards with deck context and revalidates edits', async () => {
		setup();
		await preview();
		await fireEvent.click(screen.getByRole('checkbox', { name: 'Card 2' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Edit card 1' }));
		await fireEvent.input(screen.getByLabelText('Meaning'), {
			target: { value: 'edited' },
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Apply draft edits' }));
		vi.mocked(validateCardDrafts).mockResolvedValue([{ ...drafts[0], meaning: 'edited' }]);
		vi.mocked(createCard).mockResolvedValue({ id: 'created' } as never);
		await fireEvent.click(screen.getByRole('button', { name: 'Add selected cards (1)' }));
		await waitFor(() => expect(createCard).toHaveBeenCalledOnce());
		expect(validateCardDrafts).toHaveBeenLastCalledWith('deck', {
			cards: [expect.objectContaining({ meaning: 'edited' })],
		});
		expect(createCard).toHaveBeenCalledWith(
			expect.objectContaining({
				deck_id: 'deck',
				term: 'learn',
				meaning: 'edited',
			}),
			expect.any(String),
		);
	});
	it('restores uncertain commands and retries the exact key/body without recreating confirmed cards', async () => {
		vi.mocked(createCard)
			.mockResolvedValueOnce({ id: 'first' } as never)
			.mockRejectedValueOnce(new ApiClientError('Offline', 'network', true));
		const view = setup();
		await preview();
		await fireEvent.click(screen.getByRole('button', { name: 'Add selected cards (2)' }));
		await screen.findByRole('button', { name: 'Retry unchanged cards' });
		const firstAttempt = vi.mocked(createCard).mock.calls[1];
		const restored = JSON.parse(localStorage.getItem(JSON_QUEUE_KEY)!);
		expect(restored.entries[0].status).toBe('confirmed');
		expect(restored.entries[1].status).toBe('unconfirmed');
		expect(screen.getByRole('button', { name: 'Edit card 2' })).toBeDisabled();
		view.unmount();
		render(JsonCardForm, {
			props: {
				deck,
				restored,
				onbusy: vi.fn(),
				onqueue: vi.fn(),
				oncreated: vi.fn(),
			},
		});
		vi.mocked(createCard).mockResolvedValueOnce({ id: 'second' } as never);
		await fireEvent.click(screen.getByRole('button', { name: 'Retry unchanged cards' }));
		await waitFor(() => expect(createCard).toHaveBeenCalledTimes(3));
		expect(vi.mocked(createCard).mock.calls[2]).toEqual(firstAttempt);
		expect(validateCardDrafts).toHaveBeenCalledTimes(2); // Preview and original confirmation only.
	});
});
