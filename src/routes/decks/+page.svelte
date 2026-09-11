<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { getDecks } from '$lib/api/client';
	import type { ArchiveStatus, Deck, TargetLanguage } from '$lib/api/contracts';
	import LanguageTabs from '$lib/components/LanguageTabs.svelte';
	import ReadError from '$lib/components/ReadError.svelte';
	import { readErrorCopy, type ReadErrorCopy } from '$lib/management/errors';
	import { languageName, readArchiveStatus, readLanguageQuery } from '$lib/management/navigation';

	type ViewState = 'redirecting' | 'invalid-language' | 'loading' | 'ready' | 'error';

	let viewState: ViewState = $state('loading');
	let language: TargetLanguage = $state('en');
	let archiveStatus: ArchiveStatus = $state('active');
	let decks: Deck[] = $state([]);
	let nextCursor: string | null = $state(null);
	let loadingMore = $state(false);
	let error: ReadErrorCopy | null = $state(null);
	let requestSequence = 0;

	function href(targetLanguage: TargetLanguage, status = archiveStatus): string {
		return `${resolve('/decks')}?language=${targetLanguage}&status=${status}`;
	}

	async function loadCurrent(targetLanguage: TargetLanguage, status: ArchiveStatus): Promise<void> {
		const sequence = ++requestSequence;
		viewState = 'loading';
		error = null;
		try {
			const result = await getDecks(targetLanguage, status);
			if (sequence !== requestSequence) return;
			decks = result.items;
			nextCursor = result.next_cursor;
			viewState = 'ready';
		} catch (cause) {
			if (sequence !== requestSequence) return;
			error = readErrorCopy(cause, 'decks');
			viewState = 'error';
		}
	}

	async function loadMore(): Promise<void> {
		if (!nextCursor || loadingMore) return;
		loadingMore = true;
		try {
			const result = await getDecks(language, archiveStatus, 20, nextCursor);
			decks = [...decks, ...result.items];
			nextCursor = result.next_cursor;
		} catch (cause) {
			error = readErrorCopy(cause, 'decks');
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
			void goto(href('en', parsedStatus), { replaceState: true });
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

<svelte:head>
	<title>{languageName(language)} decks · English Learning</title>
	<meta name="description" content="Manage English and Japanese learning decks." />
</svelte:head>

<section class="management-page">
	<div class="management-heading">
		<div>
			<p class="management-eyebrow">Learning library</p>
			<h1>Your decks</h1>
			<p class="management-subtitle">One library for English and Japanese cards.</p>
		</div>
		{#if viewState !== 'invalid-language'}
			<LanguageTabs current={language} englishHref={href('en')} japaneseHref={href('ja')} />
		{/if}
	</div>

	{#if viewState === 'invalid-language'}
		<section class="read-state" aria-live="polite">
			<p class="management-eyebrow">Unsupported language</p>
			<h2>Choose English or Japanese</h2>
			<p>This link uses a language that this learning library does not support.</p>
			<p><a href={href('en', 'active')}>Open English decks</a></p>
		</section>
	{:else}
		<nav class="status-tabs" aria-label="Deck status">
			<a
				aria-current={archiveStatus === 'active' ? 'page' : undefined}
				href={href(language, 'active')}>Active</a
			>
			<a
				aria-current={archiveStatus === 'archived' ? 'page' : undefined}
				href={href(language, 'archived')}>Archived</a
			>
		</nav>

		{#if viewState === 'redirecting' || viewState === 'loading'}
			<section class="read-state" aria-live="polite">
				Loading {languageName(language).toLowerCase()} decks…
			</section>
		{:else if viewState === 'error' && error}
			<ReadError {...error} onretry={() => loadCurrent(language, archiveStatus)} />
		{:else if decks.length === 0}
			<section class="read-state">
				<h2>No {archiveStatus} {languageName(language).toLowerCase()} decks</h2>
				<p>
					{archiveStatus === 'active'
						? 'Your active decks will appear here.'
						: 'Archived decks will appear here.'}
				</p>
			</section>
		{:else}
			<ul class="management-list">
				{#each decks as deck (deck.id)}
					<li class="management-row">
						<div>
							<h2>{deck.title}</h2>
							<p>
								Explained in {deck.explanation_language} · Updated {new Date(
									deck.updated_at,
								).toLocaleDateString()}
							</p>
						</div>
						<a
							href={`${resolve('/decks/[deckId]', { deckId: deck.id })}?language=${deck.target_language}&status=active`}
							>Manage cards</a
						>
					</li>
				{/each}
			</ul>
			{#if nextCursor}
				<button class="load-more" type="button" disabled={loadingMore} onclick={loadMore}>
					{loadingMore ? 'Loading…' : 'Load more decks'}
				</button>
			{/if}
		{/if}
	{/if}
</section>
