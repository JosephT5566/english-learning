<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { getCards, getDeck } from '$lib/api/client';
	import type { ArchiveStatus, CardSummary, Deck, TargetLanguage } from '$lib/api/contracts';
	import LanguageTabs from '$lib/components/LanguageTabs.svelte';
	import ReadError from '$lib/components/ReadError.svelte';
	import { readErrorCopy, type ReadErrorCopy } from '$lib/management/errors';
	import { languageName, readArchiveStatus, readLanguageQuery } from '$lib/management/navigation';

	type ViewState = 'redirecting' | 'invalid-language' | 'loading' | 'ready' | 'error';
	let viewState: ViewState = $state('loading');
	let language: TargetLanguage = $state('en');
	let archiveStatus: ArchiveStatus = $state('active');
	let deck: Deck | null = $state(null);
	let cards: CardSummary[] = $state([]);
	let nextCursor: string | null = $state(null);
	let error: ReadErrorCopy | null = $state(null);
	let loadingMore = $state(false);
	let requestSequence = 0;
	let deckId = $derived(page.params.deckId ?? '');

	function deckHref(targetLanguage: TargetLanguage, status = archiveStatus): string {
		return `${resolve('/decks/[deckId]', { deckId })}?language=${targetLanguage}&status=${status}`;
	}

	function listHref(targetLanguage = language): string {
		return `${resolve('/decks')}?language=${targetLanguage}&status=${archiveStatus}`;
	}

	async function loadCurrent(targetLanguage: TargetLanguage, status: ArchiveStatus): Promise<void> {
		const sequence = ++requestSequence;
		viewState = 'loading';
		error = null;
		try {
			const [deckResult, cardResult] = await Promise.all([
				getDeck(deckId),
				getCards(deckId, status),
			]);
			if (sequence !== requestSequence) return;
			if (deckResult.target_language !== targetLanguage) {
				viewState = 'redirecting';
				void goto(deckHref(deckResult.target_language, status), {
					replaceState: true,
				});
				return;
			}
			deck = deckResult;
			cards = cardResult.items;
			nextCursor = cardResult.next_cursor;
			viewState = 'ready';
		} catch (cause) {
			if (sequence !== requestSequence) return;
			error = readErrorCopy(cause, 'deck');
			viewState = 'error';
		}
	}

	async function loadMore(): Promise<void> {
		if (!nextCursor || loadingMore) return;
		loadingMore = true;
		try {
			const result = await getCards(deckId, archiveStatus, 20, nextCursor);
			cards = [...cards, ...result.items];
			nextCursor = result.next_cursor;
		} catch (cause) {
			error = readErrorCopy(cause, 'cards');
			viewState = 'error';
		} finally {
			loadingMore = false;
		}
	}

	$effect(() => {
		const parsedLanguage = readLanguageQuery(page.url.searchParams);
		const parsedStatus = readArchiveStatus(page.url.searchParams);
		if (parsedLanguage.kind === 'missing') {
			viewState = 'redirecting';
			void goto(deckHref('en', parsedStatus), { replaceState: true });
			return;
		}
		if (parsedLanguage.kind === 'invalid') {
			requestSequence += 1;
			viewState = 'invalid-language';
			return;
		}
		language = parsedLanguage.language;
		archiveStatus = parsedStatus;
		void loadCurrent(language, archiveStatus);
	});
</script>

<svelte:head><title>{deck?.title ?? 'Deck'} · English Learning</title></svelte:head>

<section class="management-page">
	<a class="back-link" href={listHref()}>← All {languageName(language).toLowerCase()} decks</a>
	<div class="management-heading">
		<div>
			<p class="management-eyebrow">
				{deck?.archived_at ? 'Archived deck' : 'Deck'}
			</p>
			<h1>{deck?.title ?? 'Cards'}</h1>
			{#if deck}<p class="management-subtitle">
					{deck.explanation_language} explanations · Version {deck.version}
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
	{:else}
		<nav class="status-tabs" aria-label="Card status">
			<a
				aria-current={archiveStatus === 'active' ? 'page' : undefined}
				href={deckHref(language, 'active')}>Active cards</a
			>
			<a
				aria-current={archiveStatus === 'archived' ? 'page' : undefined}
				href={deckHref(language, 'archived')}>Archived cards</a
			>
		</nav>

		{#if viewState === 'redirecting' || viewState === 'loading'}
			<section class="read-state" aria-live="polite">Loading cards…</section>
		{:else if viewState === 'error' && error}
			<ReadError {...error} onretry={() => loadCurrent(language, archiveStatus)} />
		{:else if cards.length === 0}
			<section class="read-state">
				<h2>No {archiveStatus} cards</h2>
				<p>Cards in this deck will appear here.</p>
			</section>
		{:else}
			<ul class="management-list">
				{#each cards as card (card.id)}
					<li class="management-row">
						<div>
							<h2>{card.term}</h2>
							{#if language === 'ja' && (card.reading || card.romanization)}
								<p>
									{[card.reading, card.romanization].filter(Boolean).join(' · ')}
								</p>
							{:else if language === 'en' && card.pronunciation}
								<p>{card.pronunciation}</p>
							{/if}
							<p>{card.meaning}</p>
						</div>
						<a
							href={`${resolve('/cards/[cardId]', { cardId: card.id })}?language=${card.deck.target_language}`}
							>View card</a
						>
					</li>
				{/each}
			</ul>
			{#if nextCursor}<button
					class="load-more"
					type="button"
					disabled={loadingMore}
					onclick={loadMore}>{loadingMore ? 'Loading…' : 'Load more cards'}</button
				>{/if}
		{/if}
	{/if}
</section>
