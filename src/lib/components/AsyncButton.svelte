<svelte:options runes={true} />

<script lang="ts">
	import { type Snippet } from 'svelte';
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
	let showFail = $state(false);
	let didFinish = $state(false);

	async function handleClick() {
		if (isLoading || disabled || !onRun) {
			return;
		}
		isLoading = true;
		showFail = false;

		try {
			await onRun();
			didFinish = true;
			showDone = true;
		} catch (err) {
			const message = err instanceof Error ? err.message : String(err);
			alert(`[AsyncButton] onRun error: ${message}`);
			showFail = true;
		} finally {
			isLoading = false;
		}
	}
</script>

<button
	{type}
	{...restProps}
	class={`relative ${className} disabled:opacity-50 disabled:cursor-not-allowed`}
	aria-busy={isLoading}
	disabled={disabled || isLoading || (disableAfterFinish && didFinish)}
	onclick={handleClick}
>
	<span class:opacity-0={isLoading || showDone || showFail}>
		{@render children()}
	</span>

	{#if showDone}
		<span class="btn-overlay text-rose-300" aria-hidden="true"> Submitted </span>
	{:else if showFail}
		<span class="btn-overlay text-red-300" aria-hidden="true"> Fail </span>
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
