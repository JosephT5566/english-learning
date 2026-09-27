<script lang="ts">
	import { resolve } from '$app/paths';
	import { ApiClientError, keywordSearch, semanticSearch } from '$lib/api/client';
	import type { CardSummary, Page, SemanticSearchResponse } from '$lib/api/contracts';

	type SearchMode = 'keyword' | 'semantic';

	let query = $state('');
	let submittedQuery = $state('');
	let mode: SearchMode = $state('keyword');
	let keywordResult: Page<CardSummary> | null = $state(null);
	let semanticResult: SemanticSearchResponse | null = $state(null);
	let busy = $state(false);
	let error: { message: string; retryable: boolean; auth: boolean } | null = $state(null);
	let maximumLength = $derived(mode === 'keyword' ? 200 : 500);

	function selectMode(nextMode: SearchMode): void {
		if (busy || mode === nextMode) return;
		mode = nextMode;
		keywordResult = null;
		semanticResult = null;
		error = null;
		submittedQuery = '';
	}

	async function search(event?: SubmitEvent): Promise<void> {
		event?.preventDefault();
		const normalized = query.normalize('NFC').trim();
		if (normalized.length < 2 || normalized.length > maximumLength || busy) return;
		query = normalized;
		submittedQuery = normalized;
		busy = true;
		error = null;
		keywordResult = null;
		semanticResult = null;
		try {
			if (mode === 'keyword') {
				keywordResult = await keywordSearch(normalized);
			} else {
				semanticResult = await semanticSearch({
					query: normalized,
					target_language: 'en',
					limit: 10,
				});
			}
		} catch (cause) {
			if (cause instanceof ApiClientError) {
				error = {
					message: cause.message,
					retryable: cause.retryable,
					auth: cause.kind === 'authentication',
				};
			} else {
				error = {
					message: 'Search failed unexpectedly.',
					retryable: true,
					auth: false,
				};
			}
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head>
	<title>Search · English Learning</title>
	<meta name="description" content="Search your English and Japanese vocabulary." />
</svelte:head>

<section class="search-page">
	<p class="eyebrow">Your vocabulary</p>
	<h1>Find a card</h1>
	<p class="intro">Search across your active English and Japanese vocabulary.</p>

	<div class="mode-switch" aria-label="Search mode">
		<button
			type="button"
			class:active={mode === 'keyword'}
			aria-pressed={mode === 'keyword'}
			disabled={busy}
			onclick={() => selectMode('keyword')}>Keyword</button
		>
		<button
			type="button"
			class:active={mode === 'semantic'}
			aria-pressed={mode === 'semantic'}
			disabled={busy}
			onclick={() => selectMode('semantic')}>Search by meaning</button
		>
	</div>
	{#if mode === 'semantic'}
		<p class="scope-label">English cards only</p>
	{/if}

	<form onsubmit={search}>
		<label for="search-query">{mode === 'keyword' ? 'Word or meaning' : 'Meaning or concept'}</label
		>
		<div class="search-controls">
			<input
				id="search-query"
				bind:value={query}
				minlength="2"
				maxlength={maximumLength}
				required
				disabled={busy}
				placeholder={mode === 'keyword'
					? 'e.g. serendipity or べんきょう'
					: 'e.g. a lucky discovery'}
			/>
			<button type="submit" disabled={busy || query.trim().length < 2}>
				{busy ? 'Searching…' : 'Search'}
			</button>
		</div>
	</form>

	{#if busy}
		<p class="state" aria-live="polite">Searching your cards…</p>
	{:else if error}
		<section class="state error" role="alert">
			<h2>{error.auth ? 'Sign in again' : 'Search is unavailable'}</h2>
			<p>{error.message}</p>
			{#if error.auth}
				<a href={resolve('/')}>Go to sign in</a>
			{:else if error.retryable}
				<button type="button" onclick={() => search()}>Retry “{submittedQuery}”</button>
			{/if}
		</section>
	{:else if mode === 'keyword' && keywordResult}
		{#if keywordResult.items.length === 0}
			<section class="state">
				<h2>No keyword matches</h2>
				<p>Try another spelling or switch to search by meaning.</p>
			</section>
		{:else}
			<ol class="results">
				{#each keywordResult.items as item (item.id)}
					<li>
						<a href={resolve(`/cards/${item.id}`)}>
							<span><strong>{item.term}</strong><small>{item.meaning}</small></span>
							<span class="language-badge">{item.deck.target_language === 'en' ? 'EN' : 'JP'}</span>
						</a>
					</li>
				{/each}
			</ol>
		{/if}
	{:else if mode === 'semantic' && semanticResult}
		{#if semanticResult.index_status === 'partial'}
			<p class="notice" role="status">
				Some cards are still being indexed. Showing matches from {semanticResult.indexed_count}
				of
				{semanticResult.eligible_count} eligible cards.
			</p>
		{:else if semanticResult.index_status === 'empty' && semanticResult.eligible_count > 0}
			<p class="notice" role="status">Your eligible cards are not indexed yet. Try again later.</p>
		{/if}
		{#if semanticResult.items.length === 0}
			<section class="state">
				<h2>No searchable matches yet</h2>
				<p>Your query is preserved above.</p>
			</section>
		{:else}
			<ol class="results">
				{#each semanticResult.items as item (item.id)}
					<li>
						<a href={resolve(`/cards/${item.id}`)}>
							<span><strong>{item.term}</strong><small>{item.meaning}</small></span>
							<span class="score">{Math.round(item.score * 100)}%</span>
						</a>
					</li>
				{/each}
			</ol>
		{/if}
	{/if}
</section>

<style>
	.search-page {
		width: min(46rem, calc(100% - 2rem));
		margin: 2.5rem auto 5rem;
	}
	.eyebrow {
		margin: 0;
		color: var(--color-theme-1);
		font-size: 0.75rem;
		font-weight: 800;
		letter-spacing: 0.12em;
		text-transform: uppercase;
	}
	h1 {
		margin: 0.3rem 0 0.5rem;
		font-size: clamp(2rem, 7vw, 3.5rem);
	}
	.intro {
		max-width: 38rem;
		color: #52677a;
	}
	.mode-switch {
		display: inline-flex;
		gap: 0.25rem;
		margin-top: 1.25rem;
		padding: 0.25rem;
		border: 1px solid rgba(64, 117, 166, 0.2);
		border-radius: 0.85rem;
		background: rgba(255, 255, 255, 0.58);
	}
	.mode-switch button {
		background: transparent;
		color: #52677a;
	}
	.mode-switch button.active {
		background: var(--color-theme-1);
		color: white;
	}
	.scope-label {
		display: inline-block;
		margin: 0.75rem 0 0;
		padding: 0.25rem 0.55rem;
		border-radius: 999px;
		background: rgba(64, 117, 166, 0.1);
		color: #52677a;
		font-size: 0.78rem;
		font-weight: 700;
	}
	form {
		margin-top: 2rem;
	}
	label {
		display: block;
		margin-bottom: 0.5rem;
		font-weight: 700;
	}
	.search-controls {
		display: flex;
		gap: 0.65rem;
	}
	input {
		min-width: 0;
		flex: 1;
		padding: 0.9rem 1rem;
		border: 1px solid #a9bac9;
		border-radius: 0.75rem;
		font: inherit;
	}
	button {
		padding: 0.8rem 1.1rem;
		border: 0;
		border-radius: 0.75rem;
		background: var(--color-theme-1);
		color: white;
		font-weight: 800;
		cursor: pointer;
	}
	button:disabled {
		cursor: wait;
		opacity: 0.55;
	}
	.state,
	.notice {
		margin-top: 1.5rem;
		padding: 1rem 1.1rem;
		border-radius: 0.85rem;
		background: rgba(255, 255, 255, 0.72);
		border: 1px solid rgba(64, 117, 166, 0.18);
	}
	.error {
		border-color: #c68080;
	}
	.results {
		display: grid;
		gap: 0.75rem;
		margin: 1.5rem 0 0;
		padding: 0;
		list-style: none;
	}
	.results a {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 1rem 1.1rem;
		border-radius: 0.85rem;
		background: rgba(255, 255, 255, 0.78);
		box-shadow: 0 8px 24px rgba(47, 78, 105, 0.08);
		color: inherit;
		text-decoration: none;
	}
	.results span:first-child {
		display: grid;
		gap: 0.2rem;
	}
	.results small {
		color: #52677a;
	}
	.score {
		color: var(--color-theme-1);
		font-weight: 800;
	}
	.language-badge {
		flex: none;
		padding: 0.25rem 0.5rem;
		border-radius: 999px;
		background: rgba(64, 117, 166, 0.1);
		color: var(--color-theme-1);
		font-size: 0.72rem;
		font-weight: 800;
		letter-spacing: 0.08em;
	}
	@media (max-width: 36rem) {
		.search-controls {
			flex-direction: column;
		}
	}
</style>
