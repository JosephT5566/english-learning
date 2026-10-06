<script lang="ts">
	import { getProfile } from '$lib/auth';
	import { ApiClientError, createCard, validateCardDrafts } from '$lib/api/client';
	import type { Deck } from '$lib/api/contracts';
	import CardForm from './CardForm.svelte';
	import {
		cardPrompt,
		parseCardJson,
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
		setBusy(true);
		messages = [];
		try {
			checkOwner();
			const cards = await validateCardDrafts(deck.id, parseCardJson(source));
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
				const validated = await validateCardDrafts(deck.id, {
					cards: entries.map((entry) => entry.fields),
				});
				entries.forEach((entry, index) => {
					entry.fields = validated[index];
				});
				persist();
			}
			for (const entry of queue.entries) {
				if (!entry.selected || entry.status === 'confirmed') continue;
				checkOwner();
				entry.status = 'unconfirmed';
				persist(); // Persist the exact command before sending it. Storage failure blocks the write.
				try {
					const created = await createCard({ ...entry.fields, deck_id: queue.deckId }, entry.key);
					entry.cardId = created.id;
					entry.status = 'confirmed';
					wrote = true;
					persist();
				} catch (cause) {
					// Network, malformed success, server, and authentication failures retain the key/body.
					if (
						cause instanceof ApiClientError &&
						!cause.retryable &&
						cause.kind !== 'authentication' &&
						cause.kind !== 'invalid_response'
					) {
						entry.status = 'rejected';
						entry.key = crypto.randomUUID();
						persist();
					}
					throw cause;
				}
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
			disabled={busy || uncertain}
			rows="8"
			placeholder={'{"cards":[{"term":"…","meaning":"…"}]}'}
			spellcheck="false"
		></textarea></label
	>
	<p class="input-hint">One JSON object · 1–20 cards · up to 100,000 bytes</p>
	<button
		type="button"
		class="secondary-button"
		disabled={busy || uncertain || !source.trim()}
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
				A card's result was not confirmed. Retry the unchanged cards before editing or starting
				another set.
			</p>{/if}
		<p class="input-hint">
			Cards are saved individually. If saving stops, cards already added remain in your deck.
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
