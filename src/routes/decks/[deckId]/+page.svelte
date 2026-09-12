<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { getProfile } from '$lib/auth';
	import {
		ApiClientError,
		archiveDeck,
		createCard,
		getCards,
		getDeck,
		updateDeck,
	} from '$lib/api/client';
	import type {
		ArchiveStatus,
		CardCreate,
		CardSummary,
		Deck,
		DeckCreate,
		TargetLanguage,
	} from '$lib/api/contracts';
	import CardForm from '$lib/components/CardForm.svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
	import DeckForm from '$lib/components/DeckForm.svelte';
	import Drawer from '$lib/components/Drawer.svelte';
	import LanguageTabs from '$lib/components/LanguageTabs.svelte';
	import MutationNotice from '$lib/components/MutationNotice.svelte';
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
	let deck: Deck | null = $state(null);
	let cards: CardSummary[] = $state([]);
	let nextCursor: string | null = $state(null);
	let error: ReadErrorCopy | null = $state(null);
	let loadingMore = $state(false);
	let editOpen = $state(false);
	let cardCreateOpen = $state(false);
	let archiveConfirm = $state(false);
	let mutationBusy = $state(false);
	let mutationNotice: MutationErrorCopy | null = $state(null);
	let pendingCreate: PendingManagementCreation | null = $state(null);
	let pendingLoaded = false;
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

	async function saveDeck(payload: DeckCreate): Promise<void> {
		if (!deck) return;
		mutationBusy = true;
		mutationNotice = null;
		try {
			deck = await updateDeck(deck.id, {
				version: deck.version,
				title: payload.title,
				explanation_language: payload.explanation_language,
			});
			editOpen = false;
		} catch (cause) {
			mutationNotice = mutationErrorCopy(cause);
		} finally {
			mutationBusy = false;
		}
	}

	async function discardDeckEdits(): Promise<void> {
		editOpen = false;
		mutationNotice = null;
		await loadCurrent(language, archiveStatus);
		editOpen = true;
	}

	async function archiveCurrentDeck(): Promise<void> {
		if (!deck) return;
		mutationBusy = true;
		mutationNotice = null;
		try {
			await archiveDeck(deck.id);
			await goto(`${resolve('/decks')}?language=${language}&status=archived`);
		} catch (cause) {
			try {
				const latest = await getDeck(deck.id);
				if (latest.archived_at) {
					await goto(`${resolve('/decks')}?language=${language}&status=archived`);
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

	async function saveNewCard(fields: Omit<CardCreate, 'deck_id'>): Promise<void> {
		const owner = getProfile()?.sub;
		if (!owner) {
			mutationNotice = mutationErrorCopy(
				new ApiClientError('Please sign in again.', 'authentication', false, 401),
			);
			return;
		}
		const payload: CardCreate = { ...fields, deck_id: deckId };
		if (
			!pendingCreate ||
			pendingCreate.kind !== 'card' ||
			JSON.stringify(pendingCreate.payload) !== JSON.stringify(payload)
		) {
			pendingCreate = createPendingManagement(owner, 'card', payload);
			savePendingManagement(pendingCreate);
		}
		mutationBusy = true;
		mutationNotice = null;
		try {
			const created = await createCard(payload, pendingCreate.idempotencyKey);
			clearPendingManagement();
			pendingCreate = null;
			cardCreateOpen = false;
			await goto(`${resolve('/cards/[cardId]', { cardId: created.id })}?language=${language}`);
		} catch (cause) {
			mutationNotice = mutationErrorCopy(cause);
			if (
				!(cause instanceof ApiClientError) ||
				(!cause.retryable && cause.kind !== 'authentication')
			) {
				clearPendingManagement();
				pendingCreate = null;
			}
		} finally {
			mutationBusy = false;
		}
	}

	function openCardCreate(): void {
		if (
			pendingCreate &&
			(pendingCreate.kind !== 'card' ||
				!('deck_id' in pendingCreate.payload) ||
				pendingCreate.payload.deck_id !== deckId)
		)
			return;
		mutationNotice = pendingCreate
			? {
					title: 'Card creation was not confirmed',
					message: 'Retry the unchanged request before editing these values.',
					retryable: true,
					conflict: false,
				}
			: null;
		cardCreateOpen = true;
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
		if (!pendingLoaded) {
			pendingLoaded = true;
			const owner = getProfile()?.sub;
			const pending = owner ? loadPendingManagement(owner) : null;
			pendingCreate = pending;
			if (
				pending?.kind === 'card' &&
				'deck_id' in pending.payload &&
				pending.payload.deck_id === deckId
			) {
				cardCreateOpen = true;
				mutationNotice = {
					title: 'Card creation was not confirmed',
					message: 'Your values are restored. Save again to retry the same request safely.',
					retryable: true,
					conflict: false,
				};
			}
		}
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
			<div class="heading-actions">
				<LanguageTabs
					current={language}
					englishHref={listHref('en')}
					japaneseHref={listHref('ja')}
				/>
			</div>
		{/if}
	</div>
	{#if deck && viewState === 'ready'}
		<div class="resource-actions">
			{#if !deck.archived_at && archiveStatus === 'active'}
				<button
					class="primary-button"
					type="button"
					disabled={Boolean(
						pendingCreate &&
							(pendingCreate.kind !== 'card' ||
								!('deck_id' in pendingCreate.payload) ||
								pendingCreate.payload.deck_id !== deckId),
					)}
					title={pendingCreate ? 'Finish the pending creation before starting another.' : undefined}
					onclick={openCardCreate}>New card</button
				>
				<button
					class="secondary-button"
					type="button"
					onclick={() => {
						mutationNotice = null;
						editOpen = true;
					}}>Edit deck</button
				>
				<button
					class="danger-button"
					type="button"
					onclick={() => {
						mutationNotice = null;
						archiveConfirm = true;
					}}>Archive deck</button
				>
			{/if}
		</div>
		{#if mutationNotice && !editOpen && !cardCreateOpen}<MutationNotice
				notice={mutationNotice}
			/>{/if}
	{/if}

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

{#if editOpen && deck}
	<Drawer
		title="Edit deck"
		dismissible={!mutationBusy}
		onclose={() => !mutationBusy && (editOpen = false)}
	>
		<DeckForm
			language={deck.target_language}
			initial={deck}
			busy={mutationBusy}
			locked={Boolean(pendingCreate && mutationNotice)}
			notice={mutationNotice}
			onsave={saveDeck}
			oncancel={() => (editOpen = false)}
			onreload={discardDeckEdits}
		/>
	</Drawer>
{/if}

{#if cardCreateOpen}
	<Drawer
		title={`New ${languageName(language)} card`}
		wide
		dismissible={!mutationBusy}
		onclose={() => !mutationBusy && (cardCreateOpen = false)}
	>
		<CardForm
			{language}
			draft={pendingCreate?.kind === 'card' ? (pendingCreate.payload as CardCreate) : null}
			busy={mutationBusy}
			notice={mutationNotice}
			onsave={saveNewCard}
			oncancel={() => (cardCreateOpen = false)}
		/>
	</Drawer>
{/if}

{#if archiveConfirm && deck}
	<ConfirmDialog
		eyebrow="Archive deck"
		title={`Archive “${deck.title}”?`}
		description="Its cards leave active study but remain available from Archived decks."
		cancelLabel="Keep deck"
		confirmLabel="Archive deck"
		busyLabel="Checking result…"
		busy={mutationBusy}
		oncancel={() => (archiveConfirm = false)}
		onconfirm={archiveCurrentDeck}
	/>
{/if}
