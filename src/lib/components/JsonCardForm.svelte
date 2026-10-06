<script lang="ts">
	import { getProfile } from '$lib/auth';
	import { ApiClientError, createCards, validateCardDrafts } from '$lib/api/client';
	import type { Deck } from '$lib/api/contracts';
	import CardForm from './CardForm.svelte';
	import { validateCardJson, type LocalJsonValidation } from '$lib/management/json-card-validation';
	import {
		cardPrompt,
		saveJsonQueue,
		validationMessages,
		type CardDraft,
		type JsonCardQueue,
	} from '$lib/management/json-cards';

	let {
		deck,
		restored = null,
		onbusy,
		onqueue,
		oncreated,
	}: {
		deck: Deck;
		restored?: JsonCardQueue | null;
		onbusy: (busy: boolean) => void;
		onqueue: (queue: JsonCardQueue) => void;
		oncreated: () => void;
	} = $props();
	let source = $state('');
	let queue: JsonCardQueue = $state(
		restored ?? {
			version: 1,
			owner: getProfile()?.sub ?? '',
			deckId: deck.id,
			entries: [],
		},
	);
	let busy = $state(false);
	let messages = $state<string[]>([]);
	let copied = $state(false);
	let localResult = $state<LocalJsonValidation | null>(null);
	let validationPending = $state(false);

	$effect(() => {
		const input = source;
		localResult = null;
		validationPending = Boolean(input.trim());
		if (!input.trim()) return;
		const timer = window.setTimeout(() => {
			localResult = validateCardJson(input);
			validationPending = false;
		}, 350);
		return () => window.clearTimeout(timer);
	});
	let editing = $state<number | null>(null);
	let uncertain = $derived(queue.entries.some((entry) => entry.status === 'unconfirmed'));
	let confirmed = $derived(queue.entries.filter((entry) => entry.status === 'confirmed').length);
	let selected = $derived(
		queue.entries.filter((entry) => entry.selected && entry.status !== 'confirmed').length,
	);

	function persist(): void {
		saveJsonQueue(queue);
		onqueue(queue);
	}
	function setBusy(value: boolean): void {
		busy = value;
		onbusy(value);
	}
	function checkOwner(): void {
		if (!queue.owner || getProfile()?.sub !== queue.owner)
			throw new Error('Sign in with the same account before continuing these drafts.');
	}
	function report(cause: unknown): void {
		messages = cause instanceof ApiClientError ? validationMessages(cause.details) : [];
		if (!messages.length)
			messages = [
				cause instanceof Error
					? cause.message
					: 'The result was not confirmed. Retry the same cards.',
			];
	}
	async function copyPrompt(): Promise<void> {
		try {
			await navigator.clipboard.writeText(cardPrompt(deck));
			copied = true;
		} catch {
			messages = ['Copy the prompt from the text below.'];
		}
	}
	async function preview(): Promise<void> {
		if (busy || uncertain) return;
		messages = [];
		const result = validateCardJson(source);
		localResult = result;
		validationPending = false;
		if (!result.valid) {
			messages = result.messages;
			return;
		}
		setBusy(true);
		try {
			checkOwner();
			const cards = await validateCardDrafts(deck.id, result.value);
			queue = {
				...queue,
				entries: cards.map((fields) => ({
					fields,
					key: crypto.randomUUID(),
					status: 'ready',
					selected: true,
				})),
			};
			editing = null;
			persist();
		} catch (cause) {
			report(cause);
		} finally {
			setBusy(false);
		}
	}
	function editDraft(index: number, fields: CardDraft): void {
		queue.entries[index] = {
			fields,
			key: crypto.randomUUID(),
			status: 'ready',
			selected: queue.entries[index].selected,
		};
		editing = null;
		try {
			persist();
		} catch (cause) {
			report(cause);
		}
	}
	function discardDrafts(): void {
		if (busy || uncertain) return;
		queue.entries = queue.entries.filter((entry) => entry.status === 'confirmed');
		editing = null;
		messages = [];
		try {
			persist();
		} catch (cause) {
			report(cause);
		}
	}
	async function addSelected(): Promise<void> {
		if (busy || !selected || editing !== null) return;
		setBusy(true);
		messages = [];
		let wrote = false;
		try {
			checkOwner();
			// Validate the complete selection again after edits, before any new write.
			// An uncertain command must be replayed exactly, without replacing normalized content.
			if (!uncertain) {
				const entries = queue.entries.filter(
					(entry) => entry.selected && entry.status !== 'confirmed',
				);
				const result = validateCardJson(
					JSON.stringify({ cards: entries.map((entry) => entry.fields) }),
				);
				if (!result.valid) {
					messages = result.messages;
					return;
				}
				const validated = await validateCardDrafts(deck.id, result.value);
				entries.forEach((entry, index) => {
					entry.fields = validated[index];
				});
				persist();
			}
			const entries = queue.entries.filter(
				(entry) => entry.selected && entry.status !== 'confirmed',
			);
			checkOwner();
			entries.forEach((entry) => {
				entry.status = 'unconfirmed';
			});
			persist(); // Preserve the entire exact selection before sending any write.
			try {
				const created = await createCards(queue.deckId, {
					cards: entries.map((entry) => ({ idempotency_key: entry.key, fields: entry.fields })),
				});
				entries.forEach((entry, index) => {
					entry.cardId = created[index].id;
					entry.status = 'confirmed';
				});
				wrote = true;
				persist();
			} catch (cause) {
				// Ambiguous failures retain every field/key and lock the whole selection.
				if (
					cause instanceof ApiClientError &&
					!cause.retryable &&
					cause.kind !== 'authentication' &&
					cause.kind !== 'invalid_response'
				) {
					entries.forEach((entry) => {
						entry.status = 'rejected';
					});
					// Keep keys: a restored legacy queue may already contain committed cards.
					persist();
				}
				throw cause;
			}
		} catch (cause) {
			report(cause);
		} finally {
			setBusy(false);
			if (wrote) oncreated();
		}
	}
</script>

<div class="json-authoring">
	<p class="management-subtitle">
		Use your own AI to prepare cards. Review them here before adding them to this deck.
	</p>
	<div class="prompt-heading">
		<strong>Start with the deck's prompt</strong>
		<button type="button" class="secondary-button" onclick={copyPrompt}
			>{copied ? 'Prompt copied' : 'Copy prompt'}</button
		>
	</div>
	<details class="prompt-details">
		<summary>View prompt</summary>
		<pre>{cardPrompt(deck)}</pre>
	</details>
	<label class="json-input"
		><span>Card JSON</span><textarea
			bind:value={source}
			oninput={() => (messages = [])}
			aria-invalid={localResult && !localResult.valid ? true : undefined}
			aria-describedby="json-local-validation"
			disabled={busy || uncertain}
			rows="8"
			placeholder={'{"cards":[{"term":"…","meaning":"…"}]}'}
			spellcheck="false"
		></textarea></label
	>
	<p class="input-hint">One JSON object · 1–20 cards · up to 100,000 bytes</p>
	<div id="json-local-validation" role="status" aria-live="polite">
		{#if validationPending}<p class="input-hint">Checking JSON…</p>
		{:else if localResult?.valid}<p class="input-hint">
				JSON format looks valid. Preview to check it with your deck.
			</p>
		{:else if localResult && !messages.length}
			<div class="json-errors">
				<strong>Check this JSON</strong>
				<ul>
					{#each localResult?.messages ?? [] as message, index (index)}<li>{message}</li>{/each}
				</ul>
			</div>
		{/if}
	</div>
	<button
		type="button"
		class="secondary-button"
		disabled={busy || uncertain || !source.trim() || localResult?.valid === false}
		onclick={preview}>{busy ? 'Working…' : 'Validate and preview'}</button
	>
	{#if messages.length}<div class="json-errors" role="alert">
			<strong>Check these cards</strong>
			<ul>
				{#each messages as message, messageIndex (messageIndex)}<li>{message}</li>{/each}
			</ul>
		</div>{/if}
	{#if queue.entries.length}
		<div class="preview-heading">
			<h2>Review drafts</h2>
			<span aria-live="polite">{confirmed} added · {selected} selected</span>
			<button
				type="button"
				class="secondary-button"
				disabled={busy || uncertain}
				onclick={discardDrafts}>Discard unsaved drafts</button
			>
		</div>
		{#if uncertain}<p role="status">
				The selected cards' result was not confirmed. Retry the unchanged cards before editing or
				starting another set.
			</p>{/if}
		<p class="input-hint">
			Selected cards are saved together. If any card is rejected, no new cards are added.
		</p>
		<ul class="draft-list">
			{#each queue.entries as entry, index (index)}
				<li class:added={entry.status === 'confirmed'}>
					<div class="draft-heading">
						<label
							><input
								type="checkbox"
								bind:checked={entry.selected}
								disabled={busy || uncertain || entry.status === 'confirmed'}
								onchange={() => {
									try {
										persist();
									} catch (cause) {
										report(cause);
									}
								}}
							/>Card {index + 1}</label
						>
						<span
							>{entry.status === 'confirmed'
								? 'Added'
								: entry.status === 'unconfirmed'
									? 'Not confirmed'
									: entry.status === 'rejected'
										? 'Not added'
										: 'Draft'}</span
						>
					</div>
					<strong class="draft-term">{entry.fields.term}</strong>
					<p>{entry.fields.meaning}</p>
					{#if deck.target_language === 'ja' && entry.fields.reading}<p class="input-hint">
							{entry.fields.reading}
						</p>{/if}
					{#if editing === index}
						<CardForm
							language={deck.target_language}
							draft={entry.fields}
							submitLabel="Apply draft edits"
							inputIdPrefix={`json-${index}`}
							onsave={(fields) => editDraft(index, fields)}
							oncancel={() => (editing = null)}
						/>
					{:else if entry.status !== 'confirmed'}
						<button
							type="button"
							class="secondary-button"
							disabled={busy || uncertain}
							onclick={() => (editing = index)}>Edit card {index + 1}</button
						>
					{/if}
					<details class="draft-details">
						<summary>All card fields</summary>
						<pre>{JSON.stringify(entry.fields, null, 2)}</pre>
					</details>
				</li>
			{/each}
		</ul>
		<button
			type="button"
			class="primary-button"
			disabled={busy || !selected || editing !== null}
			onclick={addSelected}
			>{busy
				? 'Adding cards…'
				: uncertain
					? 'Retry unchanged cards'
					: `Add selected cards (${selected})`}</button
		>
	{/if}
</div>

<style>
	.json-authoring {
		display: grid;
		gap: 1rem;
	}
	.prompt-heading,
	.preview-heading,
	.draft-heading {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 1rem;
		flex-wrap: wrap;
	}
	.preview-heading h2 {
		font-size: 1.25rem;
		font-weight: 700;
	}
	.json-input {
		display: grid;
		gap: 0.5rem;
		font-weight: 600;
	}
	.json-input textarea {
		width: 100%;
		min-width: 0;
		border: 1px solid #cbd5e1;
		border-radius: 0.75rem;
		padding: 0.875rem;
		font-family: 'Fira Mono', monospace;
		font-size: 0.85rem;
		font-weight: 400;
		background: #f8fafc;
	}
	.json-input textarea:focus-visible {
		outline: 2px solid #2563eb;
		outline-offset: 2px;
	}
	pre {
		white-space: pre-wrap;
		overflow-wrap: anywhere;
		font-size: 0.8rem;
		padding: 0.75rem;
		background: #f1f5f9;
		border-radius: 0.5rem;
		margin-top: 0.5rem;
	}
	summary {
		cursor: pointer;
		color: #334155;
		font-size: 0.875rem;
	}
	.input-hint,
	.preview-heading span,
	.draft-heading span {
		color: #64748b;
		font-size: 0.875rem;
	}
	.draft-list {
		display: grid;
		gap: 1rem;
		list-style: none;
		padding: 0;
	}
	.draft-list li {
		display: grid;
		gap: 0.75rem;
		padding: 1rem;
		border: 1px solid #bfdbfe;
		border-left: 4px solid #2563eb;
		border-radius: 0.75rem;
	}
	.draft-list li.added {
		border-color: #bbf7d0;
		border-left-color: #16a34a;
	}
	.draft-heading label {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.875rem;
	}
	.draft-term {
		font-size: 1.125rem;
	}
	.json-errors {
		color: #991b1b;
		background: #fef2f2;
		padding: 1rem;
		border-radius: 0.75rem;
	}
	.json-errors ul {
		list-style: disc;
		padding-left: 1.25rem;
	}
</style>
