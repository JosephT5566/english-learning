<svelte:options runes={true} />

<script lang="ts">
	import { type Snippet, onDestroy } from 'svelte';
	import Icon from '@iconify/svelte';

	interface Props {
		onRun?: () => Promise<unknown>;
		disabled?: boolean;
		type?: 'button' | 'submit';
		class?: string;
		disableAfterFinish?: boolean;
		children: Snippet;
		[x: string]: any; // 允許其他任意屬性
	}

	let {
		class: className,
		type = 'button',
		disabled = false,
		onRun,
		children,
		disableAfterFinish = true,
		...restProps
	}: Props = $props();

	let isLoading = $state(false);
	let showDone = $state(false);
	let didFinish = $state(false);
	let doneTimer: ReturnType<typeof setTimeout> | undefined;

	onDestroy(() => {
		if (doneTimer) {
			clearTimeout(doneTimer);
		}
	});

	async function handleClick() {
		if (isLoading || disabled || !onRun) return;
		isLoading = true;
		try {
			await onRun();
			didFinish = true;
			showDone = true;
			doneTimer = setTimeout(() => {
				showDone = false;
			}, 1000);
		} finally {
			isLoading = false;
		}
	}
</script>

<button
	{type}
	{...restProps}
	class={`relative ${className}`}
	aria-busy={isLoading}
	disabled={disabled || isLoading || (disableAfterFinish && didFinish)}
	onclick={handleClick}
>
	<span class:opacity-0={isLoading || showDone}>
		{@render children()}
	</span>

    {#if showDone}
        <span class="btn-overlay text-rose-300" aria-hidden="true">
            Done
        </span>
    {/if}

	{#if isLoading}
		<span class="btn-overlay text-amber-100" aria-hidden="true">
			<Icon icon="mdi:loading" class="animate-spin" width="30px" height="30px" />
		</span>
	{/if}
</button>

<style>
	.btn-overlay {
		position: absolute;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		pointer-events: none;
	}
</style>
