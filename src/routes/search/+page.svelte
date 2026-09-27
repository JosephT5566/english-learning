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

	function cardHref(cardId: string, language: 'en' | 'ja'): string {
		return `${resolve(`/cards/${cardId}`)}?language=${language}`;
	}

	function matchLabel(score: number): string {
		if (score >= 0.85) return 'Strong match';
		if (score >= 0.7) return 'Good match';
		return 'Possible match';
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
	<h1>Find a card</h1>
	<p class="intro">
		Look up English and Japanese cards directly, or describe an idea to find related English words.
	</p>

	<div class="mode-switch" aria-label="Search mode">
		<button
			type="button"
			class:active={mode === 'keyword'}
			aria-pressed={mode === 'keyword'}
			disabled={busy}
			onclick={() => selectMode('keyword')}>Words & phrases</button
		>
		<button
			type="button"
			class:active={mode === 'semantic'}
			aria-pressed={mode === 'semantic'}
			disabled={busy}
			onclick={() => selectMode('semantic')}>Meaning & concepts</button
		>
	</div>
	{#if mode === 'semantic'}
		<p class="scope-label">Meaning search currently uses English cards only.</p>
	{/if}

	<form onsubmit={search} aria-busy={busy}>
		<label for="search-query">
			{mode === 'keyword' ? 'Word, phrase, or translation' : 'Describe the meaning or idea'}
		</label>
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
				{busy ? 'Searching…' : 'Search cards'}
			</button>
		</div>
		<p class="search-hint">
			{mode === 'keyword'
				? 'Matches card words, meanings, readings, and deck content.'
				: 'Describe what you remember; exact wording is not required.'}
		</p>
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
				<h2>No cards found</h2>
				<p>Check the spelling, try a shorter phrase, or search by meaning.</p>
			</section>
		{:else}
			<div class="results-heading" aria-live="polite">
				<h2>Results for “{submittedQuery}”</h2>
				<span>{keywordResult.items.length} {keywordResult.items.length === 1 ? 'card' : 'cards'}</span>
			</div>
			<ol class="results">
				{#each keywordResult.items as item (item.id)}
					<li>
						<a href={cardHref(item.id, item.deck.target_language)}>
							<span class="result-copy">
								<strong>{item.term}</strong>
								<small>{item.meaning}</small>
								<small class="result-context">{item.deck.title}</small>
							</span>
							<span class="language-badge">{item.deck.target_language === 'en' ? 'EN' : 'JP'}</span>
						</a>
					</li>
				{/each}
			</ol>
		{/if}
	{:else if mode === 'semantic' && semanticResult}
		{#if semanticResult.index_status === 'partial'}
			<p class="notice" role="status">
				Meaning search is ready for {semanticResult.indexed_count} of your
				{semanticResult.eligible_count} English cards. These results may be incomplete.
			</p>
		{:else if semanticResult.index_status === 'empty' && semanticResult.eligible_count > 0}
			<p class="notice" role="status">
				Meaning search is still preparing your English cards. Word and phrase search works now.
			</p>
		{/if}
		{#if semanticResult.items.length === 0}
			<section class="state">
				<h2>No related cards found</h2>
				<p>Try a shorter description or search for an exact word or phrase.</p>
				<button type="button" class="secondary-action" onclick={() => selectMode('keyword')}>
					Use words & phrases
				</button>
			</section>
		{:else}
			<div class="results-heading" aria-live="polite">
				<h2>Related to “{submittedQuery}”</h2>
				<span>{semanticResult.items.length} {semanticResult.items.length === 1 ? 'card' : 'cards'}</span>
			</div>
			<ol class="results">
				{#each semanticResult.items as item (item.id)}
					<li>
						<a href={cardHref(item.id, 'en')}>
							<span class="result-copy">
								<strong>{item.term}</strong>
								<small>{item.meaning}</small>
								{#if item.pronunciation}<small class="result-context">{item.pronunciation}</small>{/if}
							</span>
							<span class="score">{matchLabel(item.score)}</span>
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
		margin: clamp(2.5rem, 8vh, 5rem) auto 5rem;
	}
	h1 {
		margin: 0;
		font-family: 'Bodoni Moda', Georgia, serif;
		font-size: clamp(2.75rem, 9vw, 4.5rem);
		font-weight: 600;
		line-height: 0.98;
		letter-spacing: -0.025em;
		text-align: left;
	}
	.intro {
		max-width: 42rem;
		margin: 1rem 0 0;
		color: #526b7f;
		font-size: 1.05rem;
	}
	.mode-switch {
		display: inline-flex;
		gap: 0.25rem;
		margin-top: 1.75rem;
		padding: 0.25rem;
		border: 1px solid rgba(64, 117, 166, 0.2);
		border-radius: 0.7rem;
		background: rgba(255, 255, 255, 0.58);
	}
	.mode-switch button {
		min-height: 2.75rem;
		padding: 0.65rem 0.9rem;
		border: 0;
		border-radius: 0.5rem;
		background: transparent;
		color: #526b7f;
		font: inherit;
		font-weight: 750;
		cursor: pointer;
	}
	.mode-switch button.active {
		background: #315f89;
		color: white;
	}
	.mode-switch button:disabled {
		cursor: wait;
		opacity: 0.6;
	}
	.scope-label {
		margin: 0.7rem 0 0;
		color: #526b7f;
		font-size: 0.82rem;
	}
	form {
		margin-top: 1.75rem;
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
		border-radius: 0.55rem;
		color: #20394e;
		background: rgba(255, 255, 255, 0.88);
		font: inherit;
	}
	input::placeholder {
		color: #64788a;
	}
	input:focus-visible {
		outline: 3px solid rgba(64, 117, 166, 0.28);
		outline-offset: 2px;
		border-color: #4075a6;
	}
	.search-controls button,
	.state button {
		padding: 0.8rem 1.1rem;
		border: 1px solid #315f89;
		border-radius: 0.65rem;
		background: #315f89;
		color: white;
		font: inherit;
		font-weight: 800;
		cursor: pointer;
	}
	.search-controls button:hover,
	.state button:hover {
		background: #294f73;
	}
	.search-controls button:disabled {
		cursor: not-allowed;
		opacity: 0.55;
	}
	.search-hint {
		margin: 0.55rem 0 0;
		color: #60788c;
		font-size: 0.82rem;
	}
	.state,
	.notice {
		margin-top: 2rem;
		padding: 1rem 1.1rem;
		border-radius: 0.75rem;
		background: rgba(255, 255, 255, 0.72);
		border: 1px solid rgba(64, 117, 166, 0.18);
	}
	.state h2,
	.state p {
		margin: 0;
	}
	.state p {
		margin-top: 0.35rem;
		color: #526b7f;
	}
	.error {
		border-color: #c68080;
	}
	.state button.secondary-action {
		margin-top: 0.85rem;
		border-color: rgba(49, 95, 137, 0.4);
		color: #315f89;
		background: rgba(255, 255, 255, 0.72);
	}
	.state button.secondary-action:hover {
		background: white;
	}
	.results-heading {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 1rem;
		margin-top: 2.25rem;
	}
	.results-heading h2 {
		min-width: 0;
		margin: 0;
		font-size: 1.1rem;
		overflow-wrap: anywhere;
	}
	.results-heading span {
		flex: none;
		color: #60788c;
		font-size: 0.78rem;
		font-variant-numeric: tabular-nums;
	}
	.results {
		display: grid;
		gap: 0;
		margin: 0.75rem 0 0;
		padding: 0;
		border-top: 1px solid rgba(64, 117, 166, 0.22);
		list-style: none;
	}
	.results a {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		min-height: 4.75rem;
		padding: 1rem 0.2rem;
		border-bottom: 1px solid rgba(64, 117, 166, 0.22);
		color: inherit;
		text-decoration: none;
		transition: color 150ms ease, padding 150ms ease, background-color 150ms ease;
	}
	.results a:hover {
		padding-inline: 0.65rem;
		color: #20394e;
		background: rgba(255, 255, 255, 0.38);
		text-decoration: none;
	}
	.result-copy {
		display: grid;
		gap: 0.2rem;
		min-width: 0;
	}
	.result-copy strong,
	.result-copy small {
		overflow-wrap: anywhere;
	}
	.results small {
		color: #526b7f;
	}
	.result-context {
		font-size: 0.75rem;
	}
	.score {
		flex: none;
		padding: 0.3rem 0.55rem;
		border-radius: 999px;
		color: #315f89;
		background: rgba(64, 117, 166, 0.1);
		font-size: 0.72rem;
		font-weight: 750;
	}
	.language-badge {
		flex: none;
		padding: 0.25rem 0.5rem;
		border-radius: 999px;
		background: rgba(64, 117, 166, 0.1);
		color: #315f89;
		font-size: 0.72rem;
		font-weight: 800;
		letter-spacing: 0.08em;
	}
	@media (max-width: 36rem) {
		.search-page {
			width: min(100% - 1.5rem, 46rem);
			margin-top: 2.5rem;
		}
		.mode-switch {
			display: grid;
			grid-template-columns: 1fr 1fr;
			width: 100%;
			box-sizing: border-box;
		}
		.search-controls {
			flex-direction: column;
		}
		.search-controls button {
			min-height: 3rem;
		}
		.results a {
			align-items: flex-start;
		}
		.results-heading {
			align-items: flex-start;
			flex-direction: column;
			gap: 0.3rem;
		}
	}
</style>
