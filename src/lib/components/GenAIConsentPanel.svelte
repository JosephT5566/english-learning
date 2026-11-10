<script lang="ts">
	let {
		consent,
		busy,
		updateConsent,
		onConfirmWithdraw,
		onKeepConsent,
		heading = 'Allow AI meaning search?',
		description = 'Your card text and search queries are sent to Google Vertex AI for semantic search. You can withdraw consent here at any time.',
		allowedMessage = 'AI meaning search is allowed.',
		withdrawalMessage = 'Withdrawing consent deletes your existing embeddings and stops AI meaning search. It cannot recall card text or search queries already sent to Google Vertex AI.'
	}: {
		consent: 'unknown' | 'required' | 'granted' | 'confirm-withdraw';
		busy: boolean;
		updateConsent: (action: 'read' | 'grant' | 'withdraw') => Promise<void>;
		onConfirmWithdraw: () => void;
		onKeepConsent: () => void;
		heading?: string;
		description?: string;
		allowedMessage?: string;
		withdrawalMessage?: string;
	} = $props();
</script>

<section class="consent" aria-label="AI consent" aria-busy={busy}>
	{#if consent === 'required'}
		<h2>{heading}</h2>
		<p>
			{description}
		</p>
		<button type="button" disabled={busy} onclick={() => updateConsent('grant')}
			>Grant consent</button
		>
	{:else if consent === 'granted'}
		<p>{allowedMessage}</p>
		<button
			type="button"
			class="secondary"
			disabled={busy}
			onclick={onConfirmWithdraw}>Withdraw consent</button
		>
	{:else if consent === 'confirm-withdraw'}
		<h2>Withdraw AI consent?</h2>
		<p>
			{withdrawalMessage}
		</p>
		<div class="consent-actions">
			<button
				type="button"
				class="danger"
				disabled={busy}
				onclick={() => updateConsent('withdraw')}>Confirm withdrawal</button
			>
			<button
				type="button"
				class="secondary"
				disabled={busy}
				onclick={onKeepConsent}>Keep consent</button
			>
		</div>
	{:else if !busy}
		<button type="button" onclick={() => updateConsent('read')}
			>Retry consent check</button
		>
	{/if}
</section>

<style>
	.consent {
		margin-top: 1rem;
		padding: 1rem 1.1rem;
		border: 1px solid rgba(64, 117, 166, 0.22);
		border-radius: 0.9rem;
		background: rgba(255, 255, 255, 0.65);
	}
	.consent h2 {
		margin: 0;
		font-size: 1.08rem;
	}
	.consent p {
		margin: 0 0 0.8rem;
	}
	.consent h2 + p {
		margin-top: 0.5rem;
	}
	.consent-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.65rem;
	}
	.consent button.secondary {
		background: rgba(255, 255, 255, 0.72);
		color: #315f89;
	}
	.consent button.danger {
		background: #fff3f1;
		border-color: #a34646;
		color: #a34646;
	}
	button {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 2.75rem;
		min-height: 2.75rem;
		padding: 0.8rem 1.1rem;
		border: 1px solid #315f89;
		border-radius: 0.65rem;
		background: #315f89;
		color: white;
		font: inherit;
		font-weight: 800;
		cursor: pointer;
	}
	button:disabled {
		cursor: not-allowed;
		opacity: 0.55;
	}
	button:focus-visible {
		outline: 3px solid rgba(64, 117, 166, 0.5);
		outline-offset: 3px;
	}
	@media (max-width: 36rem) {
		.consent-actions {
			flex-direction: column;
		}
	}
</style>
