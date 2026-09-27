<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { archiveCard, getCard, updateCard } from '$lib/api/client';
	import type { CardCreate, CardDetail, TargetLanguage } from '$lib/api/contracts';
	import CardForm from '$lib/components/CardForm.svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
	import LanguageTabs from '$lib/components/LanguageTabs.svelte';
	import MutationNotice from '$lib/components/MutationNotice.svelte';
	import ReadError from '$lib/components/ReadError.svelte';
	import { readErrorCopy, type ReadErrorCopy } from '$lib/management/errors';
	import { mutationErrorCopy, type MutationErrorCopy } from '$lib/management/mutations';
	import { readLanguageQuery } from '$lib/management/navigation';

	type ViewState = 'redirecting' | 'invalid-language' | 'loading' | 'ready' | 'error';
	let viewState: ViewState = $state('loading');
	let language: TargetLanguage = $state('en');
	let card: CardDetail | null = $state(null);
	let error: ReadErrorCopy | null = $state(null);
	let editing = $state(false);
	let archiveConfirm = $state(false);
	let mutationBusy = $state(false);
	let mutationNotice: MutationErrorCopy | null = $state(null);
	let requestSequence = 0;
	let cardId = $derived(page.params.cardId ?? '');

	function cardHref(targetLanguage: TargetLanguage): string {
		return `${resolve('/cards/[cardId]', { cardId })}?language=${targetLanguage}`;
	}

	function deckHref(): string {
		if (!card) return `${resolve('/decks')}?language=${language}`;
		return `${resolve('/decks/[deckId]', { deckId: card.deck.id })}?language=${card.deck.target_language}`;
	}

	function listHref(targetLanguage: TargetLanguage): string {
		return `${resolve('/decks')}?language=${targetLanguage}`;
	}

	function formatDate(value: string): string {
		const date = /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00`) : new Date(value);
		if (Number.isNaN(date.getTime())) return 'Date unavailable';
		return new Intl.DateTimeFormat('en-US', {
			year: 'numeric',
			month: 'short',
			day: 'numeric',
		}).format(date);
	}

	function reviewSchedule(currentCard: CardDetail): string {
		if (currentCard.archived_at) return 'Review paused while archived';
		if (!currentCard.review_state) return 'Not scheduled for review';
		const { next_review_at: nextReviewAt } = currentCard.review_state;
		const nextReview = new Date(nextReviewAt);
		if (Number.isNaN(nextReview.getTime())) return 'Review date unavailable';
		if (nextReview.getTime() <= Date.now()) return 'Ready to review';
		return `Next review ${formatDate(nextReviewAt)}`;
	}

	async function loadCurrent(targetLanguage: TargetLanguage): Promise<void> {
		const sequence = ++requestSequence;
		viewState = 'loading';
		error = null;
		try {
			const result = await getCard(cardId);
			if (sequence !== requestSequence) return;
			if (result.deck.target_language !== targetLanguage) {
				viewState = 'redirecting';
				void goto(cardHref(result.deck.target_language), {
					replaceState: true,
				});
				return;
			}
			card = result;
			viewState = 'ready';
		} catch (cause) {
			if (sequence !== requestSequence) return;
			error = readErrorCopy(cause, 'card');
			viewState = 'error';
		}
	}

	async function saveCard(fields: Omit<CardCreate, 'deck_id'>): Promise<void> {
		if (!card) return;
		mutationBusy = true;
		mutationNotice = null;
		try {
			card = await updateCard(card.id, { version: card.version, ...fields });
			editing = false;
		} catch (cause) {
			mutationNotice = mutationErrorCopy(cause);
		} finally {
			mutationBusy = false;
		}
	}

	async function discardEdits(): Promise<void> {
		editing = false;
		mutationNotice = null;
		await loadCurrent(language);
		editing = true;
	}

	async function archiveCurrentCard(): Promise<void> {
		if (!card) return;
		mutationBusy = true;
		mutationNotice = null;
		try {
			await archiveCard(card.id);
			await goto(
				`${resolve('/decks/[deckId]', { deckId: card.deck.id })}?language=${language}&status=archived`,
			);
		} catch (cause) {
			try {
				const latest = await getCard(card.id);
				if (latest.archived_at) {
					await goto(
						`${resolve('/decks/[deckId]', { deckId: latest.deck.id })}?language=${language}&status=archived`,
					);
					return;
				}
			} catch {
				// The follow-up read is also unclear; keep the operation explicitly unconfirmed.
			}
			mutationNotice = mutationErrorCopy(cause);
			archiveConfirm = false;
		} finally {
			mutationBusy = false;
		}
	}

	$effect(() => {
		const parsedLanguage = readLanguageQuery(page.url.searchParams);
		if (parsedLanguage.kind === 'missing') {
			viewState = 'redirecting';
			void goto(cardHref('en'), { replaceState: true });
			return;
		}
		if (parsedLanguage.kind === 'invalid') {
			requestSequence += 1;
			viewState = 'invalid-language';
			return;
		}
		language = parsedLanguage.language;
		void loadCurrent(language);
	});
</script>

<svelte:head><title>{card?.term ?? 'Card'} · English Learning</title></svelte:head>

<section class="management-page">
	<a class="back-link" href={deckHref()}>← {card ? `Back to ${card.deck.title}` : 'Back to decks'}</a>
	<div class="management-heading">
		<div>
			<h1>{card?.term ?? 'Card details'}</h1>
			{#if card}
				<p class="card-context">
					<span>{card.deck.title}</span>
					{#if card.learned_on}<span>Learned on {formatDate(card.learned_on)}</span>{/if}
					{#if card.archived_at}<strong>Archived</strong>{/if}
				</p>
			{/if}
		</div>
		{#if viewState !== 'invalid-language'}
			<LanguageTabs current={language} englishHref={listHref('en')} japaneseHref={listHref('ja')} />
		{/if}
	</div>
	{#if card && viewState === 'ready' && !card.archived_at && !editing}
		<div class="resource-actions">
			<button
				class="primary-button"
				type="button"
				onclick={() => {
					mutationNotice = null;
					editing = true;
				}}>Edit card</button
			>
			<button
				class="danger-button"
				type="button"
				onclick={() => {
					mutationNotice = null;
					archiveConfirm = true;
				}}>Archive card</button
			>
		</div>
	{/if}
	{#if mutationNotice && !editing}<MutationNotice notice={mutationNotice} />{/if}

	{#if viewState === 'invalid-language'}
		<section class="read-state">
			<h2>Choose English or Japanese</h2>
			<p>This card link has an unsupported language. Open your English or Japanese decks instead.</p>
			<div class="read-actions">
				<a class="secondary-button" href={listHref('en')}>Open English decks</a>
				<a class="secondary-button" href={listHref('ja')}>Open Japanese decks</a>
			</div>
		</section>
	{:else if viewState === 'redirecting' || viewState === 'loading'}
		<section class="read-state" aria-live="polite">Loading card details…</section>
	{:else if viewState === 'error' && error}
		<ReadError {...error} onretry={() => loadCurrent(language)} />
	{:else if card && editing}
		<section class="inline-editor" aria-label="Edit card">
			<h2>Edit card</h2>
			<CardForm
				{language}
				initial={card}
				busy={mutationBusy}
				notice={mutationNotice}
				onsave={saveCard}
				oncancel={() => (editing = false)}
				onreload={discardEdits}
			/>
		</section>
	{:else if card}
		<dl class="detail-grid">
			<div class="detail-field wide">
				<dt>Meaning</dt>
				<dd>{card.meaning}</dd>
			</div>
			{#if language === 'ja'}
				{#if card.reading}<div class="detail-field">
						<dt>Reading</dt>
						<dd>{card.reading}</dd>
					</div>{/if}
				{#if card.romanization}<div class="detail-field">
						<dt>Romanization</dt>
						<dd>{card.romanization}</dd>
					</div>{/if}
			{:else if card.pronunciation}
				<div class="detail-field">
					<dt>Pronunciation</dt>
					<dd>{card.pronunciation}</dd>
				</div>
			{/if}
			{#if card.part_of_speech}<div class="detail-field">
					<dt>Part of speech</dt>
					<dd>
						{card.part_of_speech}{card.part_of_speech_detail
							? ` · ${card.part_of_speech_detail}`
							: ''}
					</dd>
				</div>{/if}
			{#if card.target_language_definition}<div class="detail-field wide">
					<dt>{language === 'ja' ? 'Japanese definition' : 'English definition'}</dt>
					<dd>{card.target_language_definition}</dd>
				</div>{/if}
			{#if card.example_sentence}<div class="detail-field wide">
					<dt>Example sentence</dt>
					<dd>
						<span>{card.example_sentence}</span>
						{#if card.example_translation}<span class="example-translation">{card.example_translation}</span>{/if}
					</dd>
				</div>{/if}
			{#if card.example_source}<div class="detail-field wide">
					<dt>Example source</dt>
					<dd>{card.example_source}</dd>
				</div>{/if}
			{#if card.synonyms.length}<div class="detail-field">
					<dt>Synonyms</dt>
					<dd>{card.synonyms.join(', ')}</dd>
				</div>{/if}
			{#if card.antonyms.length}<div class="detail-field">
					<dt>Antonyms</dt>
					<dd>{card.antonyms.join(', ')}</dd>
				</div>{/if}
			{#if card.tags.length}<div class="detail-field wide">
					<dt>Study tags</dt>
					<dd>{card.tags.map((tag) => tag.display_name).join(' · ')}</dd>
				</div>{/if}
			{#if card.note}<div class="detail-field wide">
					<dt>Study note</dt>
					<dd>{card.note}</dd>
				</div>{/if}
			{#if card.supplementary_note}<div class="detail-field wide">
					<dt>More context</dt>
					<dd>{card.supplementary_note}</dd>
				</div>{/if}
			{#if card.review_state}<div class="detail-field wide review-schedule">
					<dt>Review schedule</dt>
					<dd>{reviewSchedule(card)}</dd>
				</div>{/if}
		</dl>
	{/if}
</section>

{#if archiveConfirm && card}
	<ConfirmDialog
		eyebrow="Archive card"
		title={`Remove “${card.term}” from active study?`}
		description="It will no longer appear in active study. You can still find it in Archived cards."
		cancelLabel="Keep card"
		confirmLabel="Archive card"
		busyLabel="Checking result…"
		busy={mutationBusy}
		oncancel={() => (archiveConfirm = false)}
		onconfirm={archiveCurrentCard}
	/>
{/if}

<style>
	.card-context {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.45rem 0.8rem;
		margin: 0.75rem 0 0;
		color: #60788c;
		font-size: 0.88rem;
	}

	.card-context span + span::before {
		margin-right: 0.8rem;
		color: rgba(64, 117, 166, 0.55);
		content: '·';
	}

	.card-context strong {
		padding: 0.2rem 0.55rem;
		border-radius: 999px;
		color: #76431f;
		background: rgba(180, 107, 57, 0.14);
		font-size: 0.75rem;
	}

	.read-actions {
		display: flex;
		justify-content: center;
		flex-wrap: wrap;
		gap: 0.65rem;
		margin-top: 1rem;
	}

	.read-actions a {
		text-decoration: none;
	}

	.example-translation {
		display: block;
		margin-top: 0.45rem;
		color: #526b7f;
	}

	.review-schedule dd {
		color: #315f89;
		font-weight: 750;
	}

	@media (max-width: 40rem) {
		.card-context {
			align-items: flex-start;
			flex-direction: column;
			gap: 0.3rem;
		}

		.card-context span + span::before {
			content: none;
		}
	}
</style>
