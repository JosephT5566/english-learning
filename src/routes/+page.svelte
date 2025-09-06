<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import classnames from 'classnames';
	import { renderGoogleButton, initGsiOnce } from '$lib/auth';
	import { isSignedIn } from '$lib/stores/auth';

	let todayStr = $state('');
	let testedToday = $state(false);
	let pageTitle = $derived(`${todayStr}\n Welcome back Joseph! Ready for today's learning?`);
	let gsiBtnEl: HTMLDivElement | undefined = $state(undefined); // 用來放官方 Google 按鈕的容器

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

		// 初始化只做一次（不放在點擊事件裡）
		if (!$isSignedIn && gsiBtnEl) {
			initGsiOnce((e) => console.error(e));

			// 直接渲染官方按鈕；使用者可重複點擊重試
			renderGoogleButton(gsiBtnEl);
		}
	});
</script>

<svelte:head>
	<title>{pageTitle}</title>
	<meta name="description" content="Joseph's Daily English learning" />
</svelte:head>

<section class="homepage-container gap-8">
	<h1 class="font-[Bodoni_Moda] font-medium text-3xl">{pageTitle}</h1>
	<h2 class="font-[Contrail_One] text-xl text-slate-500">
		{testedToday
			? 'You’ve completed today’s test. Would you like to continue?'
			: "You haven't done your review yet today.\n Let's start it!"}
	</h2>

	{#if $isSignedIn}
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
	{:else}
		<!-- google login button -->
		<div class="google-signin-container mt-5">
			<div bind:this={gsiBtnEl}></div>
		</div>
	{/if}
</section>

<style>
	section {
		min-height: 80vh;
		display: flex;
		flex-direction: column;
		justify-content: center;
		align-items: center;
		padding: 25px;
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
