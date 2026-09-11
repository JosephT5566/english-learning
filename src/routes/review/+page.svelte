<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import Icon from '@iconify/svelte';
	import SwipeCards from '$lib/components/SwipeCards.svelte';
	import { ApiClientError, getDueReviews, submitReviews } from '$lib/api/client';
	import type { DueCard, ReviewResult, ReviewSubmissionItem } from '$lib/api/contracts';
	import { getProfile } from '$lib/auth';
	import {
		clearPendingSubmission,
		createPendingSubmission,
		loadPendingSubmission,
		savePendingSubmission,
		type PendingReviewSubmission,
	} from '$lib/review/pending';

	type ReviewViewState =
		| 'loading'
		| 'reviewing'
		| 'empty'
		| 'submitting'
		| 'retryable_error'
		| 'authentication_required'
		| 'conflict'
		| 'rejected'
		| 'success';

	let cards = $state<DueCard[]>([]);
	let answers = $state<ReviewSubmissionItem[]>([]);
	let pending = $state<PendingReviewSubmission | null>(null);
	let result = $state<ReviewResult | null>(null);
	let viewState = $state<ReviewViewState>('loading');
	let message = $state('');
	let requestId = $state<string | undefined>();
	let allAnswered = $derived(cards.length > 0 && answers.length === cards.length);

	onMount(() => {
		void initialize();
	});

	async function initialize() {
		const subject = getProfile()?.sub;
		if (!subject) {
			showAuthenticationRequired();
			return;
		}

		const recovered = loadPendingSubmission(subject);
		if (recovered) {
			pending = recovered;
			answers = [...recovered.payload.items];
			viewState = 'retryable_error';
			message = 'Your previous review is not confirmed yet. Retry it with the original request.';
			return;
		}

		await loadCards();
	}

	async function loadCards() {
		viewState = 'loading';
		message = '';
		requestId = undefined;
		cards = [];
		answers = [];
		pending = null;
		result = null;
		try {
			const page = await getDueReviews('en', 10);
			cards = page.items.sort(() => Math.random() - 0.5);
			viewState = cards.length ? 'reviewing' : 'empty';
		} catch (error) {
			handleLoadFailure(error);
		}
	}

	function recordAnswer(answer: ReviewSubmissionItem) {
		if (answers.some((item) => item.card_id === answer.card_id)) return;
		answers = [...answers, answer];
	}

	async function submit() {
		if (viewState === 'submitting') return;
		const subject = getProfile()?.sub;
		if (!subject) {
			showAuthenticationRequired();
			return;
		}
		let command = pending;
		if (command && (command.ownerSubject !== subject || command.expiresAt <= Date.now())) {
			clearPendingSubmission();
			pending = null;
			viewState = 'rejected';
			message =
				command.ownerSubject !== subject
					? 'The previous review session was removed after the account changed.'
					: 'The unconfirmed review expired. Reload current reviews before answering again.';
			return;
		}
		if (!command) {
			command = createPendingSubmission(subject, { items: answers });
			savePendingSubmission(command);
			pending = command;
		}

		viewState = 'submitting';
		message = '';
		requestId = undefined;
		try {
			result = await submitReviews(command.payload, command.idempotencyKey);
			clearPendingSubmission();
			pending = null;
			viewState = 'success';
			const today = new Date();
			localStorage.setItem(
				'isTestedToday',
				`${String(today.getMonth() + 1).padStart(2, '0')}/${String(today.getDate()).padStart(2, '0')}`
			);
		} catch (error) {
			handleSubmissionFailure(error);
		}
	}

	function handleLoadFailure(error: unknown) {
		if (error instanceof ApiClientError) {
			requestId = error.requestId;
			if (error.kind === 'authentication') {
				showAuthenticationRequired();
				return;
			}
			message = error.retryable
				? 'Reviews could not be loaded. Please try again.'
				: 'Reviews are unavailable because the request was rejected.';
		} else {
			message = 'Reviews could not be loaded because of an unexpected error.';
		}
		viewState = 'rejected';
	}

	function handleSubmissionFailure(error: unknown) {
		if (!(error instanceof ApiClientError)) {
			viewState = 'retryable_error';
			message = 'Your review is not confirmed yet. Retry the same submission.';
			return;
		}

		requestId = error.requestId;
		if (error.kind === 'authentication') {
			showAuthenticationRequired();
			return;
		}
		if (error.status === 409) {
			clearPendingSubmission();
			pending = null;
			viewState = 'conflict';
			message =
				error.code === 'stale_review_state'
					? 'A card changed after this review started. None of your answers were saved.'
					: 'This review conflicts with the current server state. None of your answers were saved.';
			return;
		}
		if (error.retryable || error.status === undefined || error.status >= 500) {
			viewState = 'retryable_error';
			message = 'Your review is not confirmed yet. Retry the same submission.';
			return;
		}

		clearPendingSubmission();
		pending = null;
		viewState = 'rejected';
		message =
			error.status === 404
				? 'One or more review cards are no longer available. No answers were saved.'
				: 'The review was rejected. No answers were saved.';
	}

	function showAuthenticationRequired() {
		viewState = 'authentication_required';
		message = 'Your answers are not confirmed. Sign in again, then return here to retry them.';
	}
</script>

<svelte:head>
	<title>Daily English review</title>
</svelte:head>

<div
	class="review-page-container flex h-dvh min-h-0 items-center justify-center bg-[var(--bg)] p-4"
>
	{#if viewState === 'loading'}
		<div class="flex flex-col items-center gap-3" aria-live="polite">
			<Icon
				icon="svg-spinners:pulse-multiple"
				width="120px"
				height="120px"
				class="text-slate-400"
			/>
			<span class="font-[Contrail_One] text-3xl text-slate-500">Loading...</span>
		</div>
	{:else if viewState === 'reviewing'}
		<div class="flex h-full min-h-0 w-full flex-col items-center gap-4">
			<p class="font-[Contrail_One] text-slate-500" aria-live="polite">
				{Math.min(answers.length + 1, cards.length)} / {cards.length}
			</p>
			<SwipeCards wordList={cards} onAnswer={recordAnswer} />
			{#if allAnswered}
				<button class="review-action" onclick={() => void submit()}>Submit Results</button>
			{/if}
		</div>
	{:else if viewState === 'empty'}
		<section class="review-status" aria-live="polite">
			<Icon icon="solar:cat-bold-duotone" width="120px" height="120px" />
			<h1>We don't have any cards for you today.</h1>
		</section>
	{:else if viewState === 'submitting'}
		<section class="review-status" aria-live="polite">
			<Icon icon="svg-spinners:pulse-multiple" width="100px" height="100px" />
			<h1>Saving your review...</h1>
			<p>Keep this page open until the result is confirmed.</p>
		</section>
	{:else if viewState === 'success'}
		<section class="review-status" aria-live="polite">
			<Icon icon="solar:confetti-bold-duotone" width="120px" height="120px" />
			<h1>You've completed today's review!</h1>
			<p>{result?.items.length ?? 0} answers were saved.</p>
			<a class="review-action" href={resolve('/')}>Back home</a>
		</section>
	{:else if viewState === 'authentication_required'}
		<section class="review-status" role="alert">
			<h1>Sign in required</h1>
			<p>{message}</p>
			<a class="review-action" href={resolve('/')}>Go to sign in</a>
		</section>
	{:else if viewState === 'conflict'}
		<section class="review-status" role="alert">
			<h1>Review not saved</h1>
			<p>{message}</p>
			<button class="review-action" onclick={() => void loadCards()}>Reload current reviews</button>
			{#if requestId}<small>Request ID: {requestId}</small>{/if}
		</section>
	{:else if viewState === 'retryable_error'}
		<section class="review-status" role="alert">
			<h1>Review not confirmed</h1>
			<p>{message}</p>
			<button class="review-action" onclick={() => void submit()}>Retry submission</button>
			{#if requestId}<small>Request ID: {requestId}</small>{/if}
		</section>
	{:else}
		<section class="review-status" role="alert">
			<h1>Review unavailable</h1>
			<p>{message}</p>
			<button class="review-action" onclick={() => void loadCards()}>Reload reviews</button>
			{#if requestId}<small>Request ID: {requestId}</small>{/if}
		</section>
	{/if}
</div>

<style>
	.review-status {
		display: flex;
		max-width: 36rem;
		flex-direction: column;
		align-items: center;
		gap: 1rem;
		text-align: center;
		color: rgb(100 116 139);
	}

	.review-status h1 {
		font-family: 'Contrail One', sans-serif;
		font-size: 1.875rem;
	}

	.review-action {
		margin-top: 1rem;
		cursor: pointer;
		border-radius: 0.5rem;
		background: rgb(16 185 129);
		padding: 0.75rem 1.5rem;
		font-family: 'Contrail One', sans-serif;
		color: white;
		text-decoration: none;
	}

	.review-action:hover {
		background: rgb(5 150 105);
	}
</style>
