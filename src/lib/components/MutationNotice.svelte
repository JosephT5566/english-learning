<script lang="ts">
	import type { MutationErrorCopy } from '$lib/management/mutations';

	let { notice, onreload }: { notice: MutationErrorCopy; onreload?: () => void } = $props();
</script>

<div class="mutation-notice" role="alert">
	<strong>{notice.title}</strong>
	<p>{notice.message}</p>
	{#if notice.requestId}<small>Request ID: {notice.requestId}</small>{/if}
	{#if notice.conflict && onreload}
		<button type="button" class="secondary-button" onclick={onreload}>
			Reload latest and discard my changes
		</button>
	{/if}
</div>
