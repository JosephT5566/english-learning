<script lang="ts">
	import { onMount } from 'svelte';
	import SwipeCards from '$lib/components/SwipeCards.svelte';
	import { getWordListFromSheet } from '$lib/api/sheet';
	import { wordList } from '$lib/stores/review';
	import Icon from '@iconify/svelte';

	let progress = { total: 0, current: 0 };

	onMount(async () => {
		const items = await getWordListFromSheet();
    console.log('items:', items);
		wordList.set(items.sort(() => Math.random() - 0.5)); // 打散
		progress.total = items.length;
	});
</script>

<div class="review-page-container h-[90vh] bg-[var(--bg)] flex items-center justify-center">
	{#if $wordList}
		<SwipeCards wordList={$wordList} />
	{:else}
		<div class="flex flex-col items-center gap-3">
			<Icon icon="svg-spinners:pulse-multiple" width="120px" height="120px" class="text-slate-400" />
			<span class="ml-2 font-[Contrail_One] text-3xl text-slate-500">Loading...</span>
		</div>
	{/if}
</div>
