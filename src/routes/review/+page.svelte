<script lang="ts">
	import { onMount } from 'svelte';
	import SwipeCards from '$lib/components/SwipeCards.svelte';
	import { getWordList } from '$lib/api/sheet';
	import { wordList, current } from '$lib/stores/review';
	import Icon from '@iconify/svelte';

	let progress = { total: 0, current: 0 };

	onMount(async () => {
		const items = await getWordList();
		wordList.set(items.sort(() => Math.random() - 0.5)); // 打散
		progress.total = items.length;
	});
</script>

<div class="min-h-[100dvh] bg-[var(--bg)] flex items-center justify-center p-4">
	{#if $current}
		<SwipeCards wordList={$wordList} />
	{:else}
		<div class="flex flex-col items-center gap-3">
			<Icon icon="svg-spinners:pulse-multiple" width="120px" height="120px" class="text-slate-400" />
			<span class="ml-2 font-[Contrail_One] text-3xl text-slate-500">Loading...</span>
		</div>
	{/if}
</div>
