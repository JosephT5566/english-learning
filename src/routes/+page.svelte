<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import { renderGoogleButton, initGsiOnce } from '$lib/auth';
	import { isSignedIn } from '$lib/stores/auth';

	let todayStr = $state('');
	let testedToday = $state(false);
	let signInError = $state('');
	let pageTitle = $derived(
		testedToday ? 'Daily review complete — English Learning' : 'Daily review — English Learning'
	);
	let gsiBtnEl: HTMLDivElement | undefined = $state(undefined);

	onMount(() => {
		const d = new Date();
		const mm = String(d.getMonth() + 1).padStart(2, '0');
		const dd = String(d.getDate()).padStart(2, '0');
		todayStr = `${mm}/${dd}`;

		try {
			const v = localStorage.getItem('isTestedToday');
			testedToday = v === todayStr;
		} catch {
			testedToday = false;
		}

		if (!$isSignedIn && gsiBtnEl) {
			try {
				initGsiOnce(() => {
					signInError = 'Sign-in did not finish. Please try again.';
				});
				renderGoogleButton(gsiBtnEl);
			} catch {
				signInError = 'Google sign-in is unavailable right now. Refresh the page to try again.';
			}
		}
	});
</script>

<svelte:head>
	<title>{pageTitle}</title>
	<meta
		name="description"
		content="Joseph's private workspace for daily English and Japanese learning."
	/>
</svelte:head>

<section class="homepage-container">
	<div class="welcome-copy">
		{#if todayStr}<time datetime={new Date().toISOString().slice(0, 10)}>{todayStr}</time>{/if}
		<h1>Welcome back, Joseph.</h1>
		<p>Your language cards are ready whenever you are.</p>
	</div>

	<div class="review-invitation">
		<div class="review-status" class:complete={testedToday} aria-hidden="true"><span></span></div>
		<div class="invitation-copy">
			<h2>{testedToday ? 'Today’s review is complete' : 'Make a little progress today'}</h2>
			<p>
				{testedToday
					? 'You can stop here, or take another pass through your due cards.'
					: 'Open your due cards, reveal each answer, and mark how well you remembered it.'}
			</p>
		</div>

		{#if $isSignedIn}
			<a class="primary-action" href={resolve('/review')}
				>{testedToday ? 'Review again' : 'Start today’s review'}<span aria-hidden="true">→</span></a
			>
			<nav class="supporting-links" aria-label="Other learning actions">
				<a href={`${resolve('/decks')}?language=en`}>Browse decks</a>
				<a href={resolve('/search')}>Search cards</a>
			</nav>
		{:else}
			<div class="sign-in-block">
				<p>Sign in to load your private decks and review history.</p>
				<div class="google-signin-container"><div bind:this={gsiBtnEl}></div></div>
				{#if signInError}<p class="sign-in-error" role="alert">{signInError}</p>{/if}
			</div>
		{/if}
	</div>
</section>

<style>
	.homepage-container {
		width: min(100%, 52rem);
		min-height: calc(100dvh - 4.25rem);
		box-sizing: border-box;
		margin: 0 auto;
		padding: clamp(3.5rem, 10vh, 7rem) 1.25rem 4rem;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
	}

	.welcome-copy {
		max-width: 42rem;
		text-align: center;
	}

	time {
		display: block;
		margin-bottom: 0.9rem;
		color: #4075a6;
		font-family: var(--font-mono);
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.1em;
		font-variant-numeric: tabular-nums;
	}

	h1 {
		max-width: 12ch;
		margin: 0 auto;
		font-family: 'Bodoni Moda', Georgia, serif;
		font-size: clamp(3rem, 9vw, 5.5rem);
		font-weight: 600;
		line-height: 0.94;
		letter-spacing: -0.025em;
		text-align: center;
	}

	.welcome-copy > p {
		margin: 1.25rem auto 0;
		color: #526b7f;
		font-size: clamp(1rem, 2.5vw, 1.15rem);
	}

	.review-invitation {
		position: relative;
		width: min(100%, 34rem);
		box-sizing: border-box;
		margin-top: clamp(2.5rem, 7vh, 4.5rem);
		padding: clamp(1.35rem, 4vw, 2rem);
		border: 1px solid rgba(64, 117, 166, 0.22);
		border-radius: 0.9rem;
		background: rgba(255, 255, 255, 0.7);
	}

	.review-status {
		position: absolute;
		top: 1.5rem;
		right: 1.5rem;
		display: grid;
		width: 1.75rem;
		height: 1.75rem;
		place-items: center;
		border-radius: 999px;
		background: rgba(64, 117, 166, 0.12);
	}

	.review-status span {
		width: 0.5rem;
		height: 0.5rem;
		border-radius: 999px;
		background: #4075a6;
	}

	.review-status.complete {
		background: rgba(5, 150, 105, 0.13);
	}

	.review-status.complete span {
		background: rgb(5 150 105);
	}

	.invitation-copy {
		padding-right: 2.5rem;
	}

	h2 {
		margin: 0;
		color: #20394e;
		font-size: clamp(1.3rem, 4vw, 1.65rem);
		line-height: 1.15;
	}

	.invitation-copy p,
	.sign-in-block > p {
		max-width: 42ch;
		margin: 0.75rem 0 0;
		color: #526b7f;
	}

	.primary-action {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 2rem;
		min-height: 3.25rem;
		margin-top: 1.5rem;
		padding: 0 1.15rem;
		border-radius: 0.65rem;
		color: white;
		background: #315f89;
		font-weight: 750;
		text-decoration: none;
		transition:
			background-color 160ms ease-out,
			transform 160ms ease-out;
	}

	.primary-action:hover {
		color: white;
		background: #264f73;
		text-decoration: none;
		transform: translateY(-1px);
	}

	.primary-action:active {
		transform: translateY(0);
	}

	.primary-action span {
		font-size: 1.2rem;
	}

	.supporting-links {
		display: flex;
		gap: 1.25rem;
		margin-top: 1rem;
	}

	.supporting-links a {
		color: #315f89;
		font-size: 0.88rem;
		font-weight: 700;
		text-underline-offset: 0.2em;
	}

	.sign-in-block {
		margin-top: 1.5rem;
		padding-top: 1.25rem;
		border-top: 1px solid rgba(64, 117, 166, 0.18);
	}

	.sign-in-block > p {
		margin-top: 0;
	}

	.google-signin-container {
		min-height: 44px;
		max-width: 100%;
		margin-top: 1rem;
		overflow: hidden;
	}

	.sign-in-error {
		margin: 0.75rem 0 0;
		color: #8b3030;
		font-size: 0.88rem;
	}

	@media (max-width: 36rem) {
		.homepage-container {
			justify-content: flex-start;
			padding-top: clamp(3rem, 10vh, 5rem);
		}

		h1 {
			font-size: clamp(2.75rem, 15vw, 4.25rem);
		}

		.review-invitation {
			margin-top: 2.5rem;
		}

		.supporting-links {
			justify-content: space-between;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.primary-action {
			transition: none;
		}
	}

	@supports not (height: 100dvh) {
		.homepage-container {
			min-height: calc(100vh - 4.25rem);
		}
	}
</style>
