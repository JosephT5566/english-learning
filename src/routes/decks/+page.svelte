<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { getProfile } from '$lib/auth';
	import { ApiClientError, createDeck, getDecks } from '$lib/api/client';
	import type { ArchiveStatus, Deck, DeckCreate, TargetLanguage } from '$lib/api/contracts';
	import DeckForm from '$lib/components/DeckForm.svelte';
	import Drawer from '$lib/components/Drawer.svelte';
	import LanguageTabs from '$lib/components/LanguageTabs.svelte';
	import ReadError from '$lib/components/ReadError.svelte';
	import { readErrorCopy, type ReadErrorCopy } from '$lib/management/errors';
	import { mutationErrorCopy, type MutationErrorCopy } from '$lib/management/mutations';
	import { languageName, readArchiveStatus, readLanguageQuery } from '$lib/management/navigation';
	import {
		clearPendingManagement,
		createPendingManagement,
		loadPendingManagement,
		savePendingManagement,
		type PendingManagementCreation,
	} from '$lib/management/pending';

	type ViewState = 'redirecting' | 'invalid-language' | 'loading' | 'ready' | 'error';

	let viewState: ViewState = $state('loading');
	let language: TargetLanguage = $state('en');
	let archiveStatus: ArchiveStatus = $state('active');
	let decks: Deck[] = $state([]);
	let nextCursor: string | null = $state(null);
	let loadingMore = $state(false);
	let error: ReadErrorCopy | null = $state(null);
	let createOpen = $state(false);
	let createBusy = $state(false);
	let createNotice: MutationErrorCopy | null = $state(null);
	let pendingCreate: PendingManagementCreation | null = $state(null);
	let pendingLoaded = false;
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

	async function saveNewDeck(payload: DeckCreate): Promise<void> {
		const owner = getProfile()?.sub;
		if (!owner) {
			createNotice = mutationErrorCopy(
				new ApiClientError('Please sign in again.', 'authentication', false, 401),
			);
			return;
		}
		if (
			!pendingCreate ||
			pendingCreate.kind !== 'deck' ||
			JSON.stringify(pendingCreate.payload) !== JSON.stringify(payload)
		) {
			pendingCreate = createPendingManagement(owner, 'deck', payload);
			savePendingManagement(pendingCreate);
		}
		createBusy = true;
		createNotice = null;
		try {
			await createDeck(payload, pendingCreate.idempotencyKey);
			clearPendingManagement();
			pendingCreate = null;
			createOpen = false;
			await loadCurrent(language, archiveStatus);
		} catch (cause) {
			createNotice = mutationErrorCopy(cause);
			if (
				!(cause instanceof ApiClientError) ||
				(!cause.retryable && cause.kind !== 'authentication')
			) {
				clearPendingManagement();
				pendingCreate = null;
			}
		} finally {
			createBusy = false;
		}
	}

	function openDeckCreate(): void {
		if (
			pendingCreate &&
			(pendingCreate.kind !== 'deck' ||
				!('target_language' in pendingCreate.payload) ||
				pendingCreate.payload.target_language !== language)
		)
			return;
		createNotice = pendingCreate
			? {
					title: 'Deck creation was not confirmed',
					message: 'Retry the unchanged request before editing these values.',
					retryable: true,
					conflict: false,
				}
			: null;
		createOpen = true;
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
		if (!pendingLoaded) {
			pendingLoaded = true;
			const owner = getProfile()?.sub;
			const pending = owner ? loadPendingManagement(owner) : null;
			pendingCreate = pending;
			if (
				pending?.kind === 'deck' &&
				'target_language' in pending.payload &&
				pending.payload.target_language === language
			) {
				createOpen = true;
				createNotice = {
					title: 'Deck creation was not confirmed',
					message: 'Your values are restored. Save again to retry the same request safely.',
					retryable: true,
					conflict: false,
				};
			}
		}
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
			<div class="heading-actions">
				<LanguageTabs current={language} englishHref={href('en')} japaneseHref={href('ja')} />
				{#if archiveStatus === 'active'}<button
						class="primary-button"
						type="button"
						disabled={Boolean(
							pendingCreate &&
								(pendingCreate.kind !== 'deck' ||
									!('target_language' in pendingCreate.payload) ||
									pendingCreate.payload.target_language !== language),
						)}
						title={pendingCreate
							? 'Finish the pending creation before starting another.'
							: undefined}
						onclick={openDeckCreate}>New deck</button
					>{/if}
			</div>
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

{#if createOpen}
	<Drawer
		title={`New ${languageName(language)} deck`}
		dismissible={!createBusy}
		onclose={() => !createBusy && (createOpen = false)}
	>
		<DeckForm
			{language}
			draft={pendingCreate?.kind === 'deck' ? (pendingCreate.payload as DeckCreate) : null}
			busy={createBusy}
			locked={Boolean(pendingCreate && createNotice)}
			notice={createNotice}
			onsave={saveNewDeck}
			oncancel={() => (createOpen = false)}
		/>
	</Drawer>
{/if}
