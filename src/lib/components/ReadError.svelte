<script lang="ts">
	let {
		title,
		message,
		requestId,
		retryable = false,
		onretry,
	}: {
		title: string;
		message: string;
		requestId?: string;
		retryable?: boolean;
		onretry?: () => void;
	} = $props();
</script>

<section class="read-state error-state" aria-live="polite">
	<p class="state-label">Couldn’t load</p>
	<h2>{title}</h2>
	<p>{message}</p>
	{#if requestId}
		<p class="request-id">Request ID: {requestId}</p>
	{/if}
	{#if retryable && onretry}
		<button type="button" onclick={onretry}>Try again</button>
	{/if}
</section>

<style>
	.error-state {
		border-color: rgba(170, 68, 47, 0.28);
	}

	.state-label {
		margin: 0;
		color: #9a4636;
		font-family: var(--font-mono);
		font-size: 0.72rem;
		font-weight: 700;
		letter-spacing: 0.12em;
		text-transform: uppercase;
	}

	h2 {
		margin: 0.45rem 0 0;
		font-family: 'Bodoni Moda', Georgia, serif;
		font-size: 1.65rem;
	}

	p:not(.state-label) {
		margin: 0.6rem 0 0;
	}

	.request-id {
		font-family: var(--font-mono);
		font-size: 0.75rem;
		opacity: 0.72;
	}

	button {
		margin-top: 1rem;
		padding: 0.65rem 0.9rem;
		border: 0;
		border-radius: 0.55rem;
		color: white;
		background: #4075a6;
		font-weight: 700;
		cursor: pointer;
	}
</style>
