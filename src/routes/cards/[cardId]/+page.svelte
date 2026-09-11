<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { getCard } from '$lib/api/client';
	import type { CardDetail, TargetLanguage } from '$lib/api/contracts';
	import LanguageTabs from '$lib/components/LanguageTabs.svelte';
	import ReadError from '$lib/components/ReadError.svelte';
	import { readErrorCopy, type ReadErrorCopy } from '$lib/management/errors';
	import { readLanguageQuery } from '$lib/management/navigation';

	type ViewState = 'redirecting' | 'invalid-language' | 'loading' | 'ready' | 'error';
	let viewState: ViewState = $state('loading');
	let language: TargetLanguage = $state('en');
	let card: CardDetail | null = $state(null);
	let error: ReadErrorCopy | null = $state(null);
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
	<a class="back-link" href={deckHref()}>← Back to deck</a>
	<div class="management-heading">
		<div>
			<p class="management-eyebrow">
				{card?.archived_at ? 'Archived card' : (card?.deck.title ?? 'Learning card')}
			</p>
			<h1>{card?.term ?? 'Card details'}</h1>
			{#if card}<p class="management-subtitle">
					Version {card.version} · Learned {card.learned_on ?? 'date not set'}
				</p>{/if}
		</div>
		{#if viewState !== 'invalid-language'}
			<LanguageTabs current={language} englishHref={listHref('en')} japaneseHref={listHref('ja')} />
		{/if}
	</div>

	{#if viewState === 'invalid-language'}
		<section class="read-state">
			<h2>Choose English or Japanese</h2>
			<p>This link uses an unsupported language.</p>
		</section>
	{:else if viewState === 'redirecting' || viewState === 'loading'}
		<section class="read-state" aria-live="polite">Loading card…</section>
	{:else if viewState === 'error' && error}
		<ReadError {...error} onretry={() => loadCurrent(language)} />
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
					<dt>Definition</dt>
					<dd>{card.target_language_definition}</dd>
				</div>{/if}
			{#if card.example_sentence}<div class="detail-field wide">
					<dt>Example</dt>
					<dd>
						{card.example_sentence}{card.example_translation ? `\n${card.example_translation}` : ''}
					</dd>
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
					<dt>Tags</dt>
					<dd>{card.tags.map((tag) => tag.display_name).join(' · ')}</dd>
				</div>{/if}
			{#if card.note}<div class="detail-field wide">
					<dt>Note</dt>
					<dd>{card.note}</dd>
				</div>{/if}
			{#if card.supplementary_note}<div class="detail-field wide">
					<dt>Supplementary note</dt>
					<dd>{card.supplementary_note}</dd>
				</div>{/if}
			{#if card.review_state}<div class="detail-field wide">
					<dt>Review</dt>
					<dd>
						Stage {card.review_state.review_stage} · Next {new Date(
							card.review_state.next_review_at,
						).toLocaleDateString()}
					</dd>
				</div>{/if}
		</dl>
	{/if}
</section>
