<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import classnames from 'classnames';

	let todayStr = $state('');
	let testedToday = $state(false);
	let pageTitle = $derived(`${todayStr}\n Welcome back Joseph! Ready for today's learning?`);

	onMount(() => {
		const d = new Date();
		const mm = String(d.getMonth() + 1).padStart(2, '0');
		const dd = String(d.getDate()).padStart(2, '0');
		todayStr = `${mm}/${dd}`;

		try {
			const v = localStorage.getItem('isTestedToday');
			// 建議在完成測驗時寫入：localStorage.setItem('isTestedToday', todayStr)
			testedToday = v === todayStr;
		} catch {
			testedToday = false;
		}
	});
</script>

<svelte:head>
	<title>{pageTitle}</title>
	<meta name="description" content="Joseph's Daily English learning" />
</svelte:head>

<section class="gap-8">
	<h1 class="font-[Bodoni_Moda] font-medium text-3xl">{pageTitle}</h1>
	<h2 class="font-[Contrail_One] text-xl text-slate-500">
		{testedToday
			? 'You’ve completed today’s test. Would you like to continue?'
			: "You haven't done your review yet today.\n Let's start it!"}
	</h2>

	<button
		class={classnames(
			'font-[Contrail_One]',
			'start-btn',
			'px-5',
			'py-4',
			'mt-10',
			'text-xl',
			'text-neutral-100',
			'decoration-0',
			'rounded-lg',
			'bg-emerald-500',
			'hover:bg-emerald-600',
			'cursor-pointer',
			'transition'
		)}
		onclick={() => (window.location.href = resolve('/review'))}
	>
		Start
	</button>
</section>

<style>
	section {
		min-height: 80vh;
		display: flex;
		flex-direction: column;
		justify-content: center;
		align-items: center;
	}
	h1 {
		text-align: center;
		/* 讓 \n 變成實際換行 */
		white-space: pre-line;
	}
	h2 {
		margin: 0;
		text-align: center;
		white-space: pre-line;
	}
</style>
