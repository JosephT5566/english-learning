<svelte:options runes={true} />

<script lang="ts">
	import type { DueCard, ReviewDecision, ReviewSubmissionItem } from '$lib/api/contracts';
	import type { StudyDirection } from '$lib/types';
	import { canAnswerCard } from '$lib/review/interaction';
	import _clamp from 'lodash/clamp';
	import Icon from '@iconify/svelte';
	import classNames from 'classnames';
	import { SvelteSet } from 'svelte/reactivity';
	import Modal from '$lib/components/Modal.svelte';

	// 透過 runes 取得 props
	let {
		wordList = [],
		studyDirection = 'EN_ZH',
		onAnswer,
	}: {
		wordList?: DueCard[];
		studyDirection?: StudyDirection;
		onAnswer?: (answer: ReviewSubmissionItem) => void;
	} = $props();

	let root: HTMLDivElement | undefined = $state(); // .swipe
	let cardsWrap: HTMLDivElement | undefined = $state(); // .swipe--cards

	type Scratch = {
		x: number;
		y: number;
		rot: number;
		down: boolean;
		startX: number;
		startY: number;
		pointerId: number;
		showAnswer: boolean;
		isBack: boolean; // ⇦ front/back state
		moved: boolean; // ⇦ small movement guard to avoid click-after-drag flipping
		moveHist: { x: number; y: number; t: number }[]; // 近期移動歷史，用於估算速度
	};
	const scratch = new WeakMap<HTMLElement, Scratch>();

	// UI state（runes）
	let swipeX = $state(0);
	let isTopCardBack = $state(false);
	let isClickAndSwiping = $state(false);
	let currentWordIndex = $state(0);
	let currentWord = $derived(wordList[currentWordIndex] ?? null);
	let isEnded = $derived(currentWordIndex >= wordList.length);
	const hasCards = $derived(wordList.length > 0);
	let modalOpen = $state(false);
	let modalContent = $state('');
	let announcement = $state('');
	const timers = new SvelteSet<ReturnType<typeof setTimeout>>();

	const answerOptions: {
		decision: ReviewDecision;
		label: string;
		shortcut: string;
		isYes: boolean;
		icon: string;
	}[] = [
		{ decision: 'no', label: 'Forgot', shortcut: '1', isYes: false, icon: 'solar:close-square-bold' },
		{
			decision: 'no_a_bit',
			label: 'Hard',
			shortcut: '2',
			isYes: false,
			icon: 'solar:close-square-outline',
		},
		{
			decision: 'yes_a_bit',
			label: 'Almost',
			shortcut: '3',
			isYes: true,
			icon: 'solar:check-square-outline',
		},
		{ decision: 'yes', label: 'Knew it', shortcut: '4', isYes: true, icon: 'solar:check-square-bold' },
	];

	const THRESHOLD = 200; // fly-out decision
	const MOVE_OUT_MULT = 1.5;
	const VELOCITY_THRESHOLD = 0.6; // px/ms ≈ 600px/s，超過視為快速滑動（fling）

	const yesOpacity = $derived(swipeX > 0 ? Math.min(Math.abs(swipeX) / THRESHOLD, 1) : 0);
	const noOpacity = $derived(swipeX < 0 ? Math.min(Math.abs(swipeX) / THRESHOLD, 1) : 0);

	// $effect(() => {
	// 	console.log('isEnded', isEnded);
	// });
	// $effect(() => {
	// 	console.log('Current word index', currentWordIndex);
	// });

	// $effect(() => {
	// 	console.log('new Fields', $newFields);
	// });

	// Warning: this function is called when the card flips or is swiped away, make sure related logic is correct.
	function topCardEl(): HTMLElement | null {
		if (!cardsWrap) return null;
		// first non-removed card (highest z) is the last child
		const els = Array.from(cardsWrap.querySelectorAll<HTMLElement>('.swipe--card'));
		const topCard = els.find((el) => !el.dataset.removed) || null;

		return topCard;
	}

	function updateLayoutStack() {
		if (!cardsWrap) return;
		const els = Array.from(cardsWrap.querySelectorAll<HTMLElement>('.swipe--card')).filter(
			(el) => !el.dataset.removed
		);

		els.forEach((el, i) => {
			const scale = (20 - i) / 20;
			const translateY = -30 * i;
			const opacity = (10 - i) / 10;
			el.style.opacity = String(opacity);
			el.style.zIndex = String(els.length - i);
			el.style.transform = `scale(${scale}) translateY(${translateY}px)`;
		});
	}

	function setBadge(x: number) {
		if (!root) return;
		root.classList.toggle('swipe_yes', x > 10);
		root.classList.toggle('swipe_no', x < -10);
	}

	function clearBadge() {
		if (!root) return;
		root.classList.remove('swipe_yes', 'swipe_no');
	}

	function schedule(callback: () => void, delay: number) {
		const timer = setTimeout(() => {
			timers.delete(timer);
			callback();
		}, delay);
		timers.add(timer);
	}

	function toggleCard(el: HTMLElement) {
		const s = scratch.get(el);
		if (!s || el !== topCardEl() || isClickAndSwiping) return;

		s.isBack = !s.isBack;
		el.classList.toggle('is-back', s.isBack);
		isTopCardBack = s.isBack;
		announcement = s.isBack
			? `Answer revealed for ${currentWord?.term ?? 'this card'}. Choose how well you remembered it.`
			: `Question shown for ${currentWord?.term ?? 'this card'}.`;

		if (!s.isBack) {
			swipeX = 0;
			clearBadge();
		}
	}

	function handleCardKeydown(event: KeyboardEvent, index: number) {
		if (index !== currentWordIndex || event.repeat || isClickAndSwiping) return;
		const el = event.currentTarget as HTMLElement;

		if (event.key === 'Enter' || event.key === ' ') {
			event.preventDefault();
			toggleCard(el);
			return;
		}

		const option = answerOptions.find(({ shortcut }) => shortcut === event.key);
		if (option && scratch.get(el)?.isBack) {
			event.preventDefault();
			programmaticSwipe(option.isYes, option.decision, true);
		}
	}

	function attachDrag(el: HTMLElement) {
		scratch.set(el, {
			x: 0,
			y: 0,
			rot: 0,
			down: false,
			startX: 0,
			startY: 0,
			pointerId: -1,
			showAnswer: false,
			isBack: false, // start face-up (front)
			moved: false,
			moveHist: [],
		});

		// 以最近 120ms 的軌跡估算速度（px/ms）
		function velocityOf(hist: { x: number; y: number; t: number }[]) {
			if (hist.length < 2) {
				return { vx: 0, vy: 0 };
			}

			const first = hist[0];
			const last = hist[hist.length - 1];
			const dt = Math.max(1, last.t - first.t);
			return { vx: (last.x - first.x) / dt, vy: (last.y - first.y) / dt };
		}

		function onDown(e: PointerEvent) {
			const s = scratch.get(el)!;
			if (s.down) return;
			// Only the top card AND only on back side can start dragging
			if (!canAnswerCard(el === topCardEl(), s.isBack, isClickAndSwiping)) {
				return;
			}

			el.setPointerCapture(e.pointerId);
			s.down = true;
			s.pointerId = e.pointerId;
			s.startX = e.clientX - s.x;
			s.startY = e.clientY - s.y;
			s.moved = false;
			el.classList.add('moving');
			s.moveHist = [{ x: s.x, y: s.y, t: performance.now() }];
		}

		function onMove(e: PointerEvent) {
			const s = scratch.get(el)!;
			if (!s.down || s.pointerId !== e.pointerId) return;
			s.x = e.clientX - s.startX;
			s.y = e.clientY - s.startY;
			s.rot = s.x * 0.03 * (s.y / 80);
			if (Math.abs(s.x) > 3 || Math.abs(s.y) > 3) s.moved = true;

			// 記錄移動歷史（僅保留最近 ~120ms）
			const now = performance.now();
			s.moveHist.push({ x: s.x, y: s.y, t: now });
			while (s.moveHist.length > 2 && s.moveHist[0].t < now - 120) {
				s.moveHist.shift();
			}

			// Only reflect swipe UI on the back side
			el.style.transform = `translate(${s.x}px, ${s.y}px) rotate(${s.rot}deg)`;
			swipeX = s.x;
			setBadge(s.x);
		}

		function flyOutAndRemove(directionX: number, y: number, speedX?: number) {
			const s = scratch.get(el)!;
			const moveOutWidth = document.body.clientWidth * 1.2;
			const toX =
				directionX > 0
					? Math.max(Math.abs(s.x), moveOutWidth)
					: -Math.max(Math.abs(s.x), moveOutWidth);
			const toY = y >= 0 ? Math.abs(y) * MOVE_OUT_MULT : -Math.abs(y) * MOVE_OUT_MULT;

			el.classList.remove('moving');
			// 速度越快，時間越短（180~380ms）
			const absV = Math.abs(speedX ?? 0);
			const duration = speedX ? _clamp(Math.round(280 / absV), 180, 380) : 250;
			el.style.transition = `transform ${duration}ms ease-out`;
			el.style.transform = `translate(${toX}px, ${toY}px) rotate(${s.rot}deg)`;
			el.dataset.removed = '1';
			swipeX = 0;
			isTopCardBack = false; // reset state

			updateFinishedCard(directionX > 0 ? 'yes' : 'no');

			setTimeout(() => {
				el.style.transition = '';
				clearBadge();
				updateLayoutStack();
			}, duration);
		}

		function snapBack() {
			el.classList.remove('moving');
			el.style.transition = 'transform 0.25s ease';
			el.style.transform = '';
			setTimeout(() => {
				el.style.transition = '';
				clearBadge();
			}, 260);
			const s = scratch.get(el)!;
			s.x = 0;
			s.y = 0;
			s.rot = 0;
			swipeX = 0;
		}

		function onUp(e: PointerEvent) {
			const s = scratch.get(el)!;
			if (!s.down || s.pointerId !== e.pointerId) return;
			s.down = false;
			s.pointerId = -1;
			if (el.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId);
			// decide: 距離或速度達門檻就飛出
			const { vx } = velocityOf(s.moveHist);
			const fast = Math.abs(vx) > VELOCITY_THRESHOLD;
			if (Math.abs(s.x) >= THRESHOLD || fast) {
				flyOutAndRemove(fast ? vx : s.x, s.y, fast ? vx : undefined);
			} else {
				snapBack();
			}
		}

		function cancelDrag() {
			const s = scratch.get(el);
			if (!s?.down) return;
			s.down = false;
			if (s.pointerId >= 0 && el.hasPointerCapture(s.pointerId)) {
				el.releasePointerCapture(s.pointerId);
			}
			s.pointerId = -1;
			s.moved = true;
			snapBack();
		}

		// Click-to-flip (front<->back), but ignore if it was actually a drag
		function onClick() {
			const s = scratch.get(el)!;
			if (s.down || s.moved) {
				s.moved = false;
				return; // was a drag, not a click
			}

			toggleCard(el);
		}

		el.addEventListener('pointerdown', onDown);
		el.addEventListener('pointermove', onMove);
		el.addEventListener('pointerup', onUp);
		el.addEventListener('pointercancel', cancelDrag);
		el.addEventListener('lostpointercapture', cancelDrag);
		el.addEventListener('click', onClick);
		window.addEventListener('blur', cancelDrag);

		return () => {
			el.removeEventListener('pointerdown', onDown);
			el.removeEventListener('pointermove', onMove);
			el.removeEventListener('pointerup', onUp);
			el.removeEventListener('pointercancel', cancelDrag);
			el.removeEventListener('lostpointercapture', cancelDrag);
			el.removeEventListener('click', onClick);
			window.removeEventListener('blur', cancelDrag);
			scratch.delete(el);
		};
	}

	function programmaticSwipe(
		isYes: boolean,
		decision: ReviewDecision,
		focusNextCard = false
	) {
		const el = topCardEl();
		const s = el ? scratch.get(el) : undefined;
		if (!el || !s || !canAnswerCard(true, s.isBack, isClickAndSwiping)) {
			return;
		}

		isClickAndSwiping = true;
		el.classList.add('click-and-swiping');

		const st = s || {
			x: 0,
			y: 0,
			rot: isYes ? -0.3 : 0.3,
			down: false,
			startX: 0,
			startY: 0,
			pointerId: -1,
			showAnswer: false,
			isBack: true,
			moved: false,
			moveHist: [],
		};
		scratch.set(el, st);
		st.x = isYes ? 200 : -200;
		st.y = -80;
		isTopCardBack = false; // reset state

		updateFinishedCard(decision);

		requestAnimationFrame(() => {
			const moveOutWidth = document.body.clientWidth * 1.2 * (isYes ? 1 : -1);
			el.style.transform = `translate(${moveOutWidth}px, -120px) rotate(${st.rot}deg)`;
			el.dataset.removed = '1';

			schedule(() => {
				el.classList.remove('click-and-swiping'); // clean up
				el.style.transition = '';
				clearBadge();
				updateLayoutStack();
			}, 300);

			if (focusNextCard) {
				requestAnimationFrame(() => topCardEl()?.focus());
			}
		});

		schedule(() => {
			isClickAndSwiping = false;
		}, 1000);
	}

	function updateFinishedCard(decision: ReviewDecision) {
		if (!currentWord) {
			return; // safety guard
		}
		const answeredCard = currentWord;
		onAnswer?.({
			card_id: currentWord.id,
			decision,
			expected_version: currentWord.review_state.version,
		});
		const label = answerOptions.find((option) => option.decision === decision)?.label ?? decision;
		announcement = `${label}. ${answeredCard.term} completed.`;
		currentWordIndex += 1; // move to next card
	}

	type FrontFace = {
		title: string;
		lessonDate: string | null;
		chips: string[];
		tags: string[];
		phonics?: string;
	};
	type BackFace = {
		title: string;
		subtitle?: string;
		head?: string;
		lessonDate: string | null;
		example: string | null;
		syns: string[];
		ants: string[];
		supplementary?: string;
	};

	function displayedPartOfSpeech(c: DueCard): string | null {
		return c.part_of_speech === 'other' && c.part_of_speech_detail
			? c.part_of_speech_detail
			: c.part_of_speech;
	}

	// Compute what to show on each face from a Card + direction + mode
	function faceFront(c: DueCard, dir: StudyDirection): FrontFace {
		const partOfSpeech = displayedPartOfSpeech(c);
		if (dir === 'EN_ZH') {
			return {
				title: c.term,
				lessonDate: c.learned_on ? new Date(c.learned_on).toLocaleDateString('zh-TW') : null,
				chips: [partOfSpeech, ...(c.note?.split(/,\s*/g) ?? [])].filter(Boolean) as string[],
				tags: c.tags.map((tag) => tag.display_name),
				phonics: c.pronunciation ?? c.reading ?? c.romanization ?? undefined,
			};
		} else {
			return {
				title: c.meaning || '—',
				lessonDate: c.learned_on ? new Date(c.learned_on).toLocaleDateString('zh-TW') : null,
				chips: [partOfSpeech, ...(c.note?.split(/,\s*/g) ?? [])].filter(Boolean) as string[],
				tags: c.tags.map((tag) => tag.display_name),
				phonics: undefined,
			};
		}
	}

	function faceBack(c: DueCard, dir: StudyDirection): BackFace {
		if (dir === 'EN_ZH') {
			return {
				title: c.meaning || '—',
				subtitle: c.target_language_definition ?? undefined,
				lessonDate: c.learned_on ? new Date(c.learned_on).toLocaleDateString('zh-TW') : null,
				example: c.example_sentence,
				syns: c.synonyms,
				ants: c.antonyms,
				supplementary: c.supplementary_note ?? undefined,
			};
		} else {
			return {
				title: c.term,
				subtitle: c.target_language_definition ?? undefined,
				head: c.pronunciation ?? c.reading ?? c.romanization ?? undefined,
				lessonDate: c.learned_on ? new Date(c.learned_on).toLocaleDateString('zh-TW') : null,
				example: c.example_sentence,
				syns: c.synonyms,
				ants: c.antonyms,
				supplementary: c.supplementary_note ?? undefined,
			};
		}
	}

	// https://github.com/sveltejs/svelte/issues/15975
	function listen(node: Node, { name, handler }: { name: string; handler: EventListener }) {
		node.addEventListener(name, handler);
		return { destroy: () => node.removeEventListener(name, handler) };
	}

	function openInfoModal(b: BackFace) {
		if (!b.supplementary) {
			return;
		}

		modalContent = b.supplementary;
		modalOpen = true;
	}

	$effect(() => {
		if (!cardsWrap) {
			return;
		}

		const els = Array.from(cardsWrap.querySelectorAll<HTMLElement>('.swipe--card'));
		const cleanups = els.map((el) => attachDrag(el));
		updateLayoutStack();

		return () => {
			cleanups.forEach((cleanup) => cleanup());
			for (const timer of timers) clearTimeout(timer);
			timers.clear();
		};
	});
</script>

<div class="swipe" bind:this={root}>
	<p class="sr-only" aria-live="polite" aria-atomic="true">{announcement}</p>
	{#if !hasCards}
		<div class="flex flex-col items-center gap-3 mt-10">
			<Icon icon="solar:cat-bold-duotone" width="120px" height="120px" class="text-slate-400" />
			<span class="ml-2 font-[Contrail_One] text-3xl text-center text-slate-500">
				We don't have any cards for you today.
			</span>
		</div>
	{:else if isEnded}
		<div class="flex flex-col items-center gap-3 mt-10">
			<Icon
				icon="solar:confetti-bold-duotone"
				width="120px"
				height="120px"
				class="text-slate-400"
			/>
			<span class="ml-2 font-[Contrail_One] text-3xl text-center text-slate-500">
				Your answers are ready to submit.
			</span>
		</div>
	{:else}
		<div class="review-guidance" id="review-guidance">
			<p>{isTopCardBack ? 'Choose how well you remembered it.' : 'Flip the card to reveal the answer.'}</p>
			<span>{isTopCardBack ? 'Swipe or press 1–4' : 'Click, tap, or press Enter'}</span>
		</div>

		<div class="swipe--status">
			<span class="icon no" style="opacity:{noOpacity}">
				<Icon icon="solar:close-square-outline" class={noOpacity === 1 ? 'text-rose-500' : ''} />
			</span>
			<span class="icon yes" style="opacity:{yesOpacity}">
				<Icon
					icon="solar:check-square-outline"
					class={yesOpacity === 1 ? 'text-emerald-500' : ''}
				/>
			</span>
		</div>

		<div class="swipe--cards" bind:this={cardsWrap}>
			{#each wordList as c, i (`${c.id ?? 'no-id'}-${i}`)}
				{@const f = faceFront(c, studyDirection) as FrontFace}
				{@const b = faceBack(c, studyDirection) as BackFace}
				<div
					class="swipe--card rounded-2xl"
					role="button"
					tabindex={i === currentWordIndex ? 0 : -1}
					aria-label={`${isTopCardBack && i === currentWordIndex ? 'Answer' : 'Question'} card for ${f.title}`}
					aria-expanded={i === currentWordIndex ? isTopCardBack : false}
					aria-describedby={i === currentWordIndex ? 'review-guidance' : undefined}
					aria-keyshortcuts="Enter Space 1 2 3 4"
					aria-hidden={i !== currentWordIndex}
					onkeydown={(event) => handleCardKeydown(event, i)}
				>
					<!-- 3D flip container -->
					<div class="card-inner">
						<!-- FRONT -->
						<div class="card-face card-front p-2 pb-10 bg-white">
							{#if f.chips?.length}
								<div class="chips">
									{#each f.chips as chip, idx (idx)}
										<span class={classNames('chip', idx === 0 ? 'bg-orange-200' : 'bg-gray-100')}
											>{chip}</span
										>
									{/each}
								</div>
							{/if}
							{#if f.tags?.length}
								<div class="chips mt-2">
									{#each f.tags as tag, idx (idx)}
										<span class={classNames('chip', 'bg-gray-100')}>{tag}</span>
									{/each}
								</div>
							{/if}
							<h2 class="headline">{f.title}</h2>
							{#if f.phonics}<div class="hint">{f.phonics}</div>{/if}
							{#if f.lessonDate}
								<div class="lesson-date chip bg-gray-100">{f.lessonDate}</div>
							{/if}
						</div>

						<!-- BACK -->
						<div class="card-face card-back py-10 px-4 bg-slate-300">
							{#if b.supplementary}
								<button
									class={classNames(
										'info-btn',
										'absolute',
										'top-2',
										'right-2',
										'cursor-pointer',
										'p-2',
										'rounded-full',
										'text-amber-700',
										'hover:bg-slate-400/50',
										'active:bg-slate-400/70',
										'transition'
									)}
									title="More info"
									use:listen={{
										name: 'click',
										handler: (e) => {
											e.stopPropagation();
											openInfoModal(b);
										},
									}}
									use:listen={{
										name: 'pointerdown',
										handler: (e) => e.stopPropagation(),
									}}
									aria-label="Open supplementary info"
									tabindex={i === currentWordIndex && isTopCardBack ? 0 : -1}
								>
									<Icon icon="solar:info-circle-bold" width="25px" height="25px" />
								</button>
							{/if}

							<h2 class="headline">{b.title}</h2>
							{#if b.head}<div class="ipa">{b.head}</div>{/if}
							{#if b.subtitle}<div class="subtitle">{b.subtitle}</div>{/if}
							{#if f.lessonDate}
								<div class="lesson-date chip bg-gray-100">{f.lessonDate}</div>
							{/if}
							{#if b.example}<p class="example">{b.example}</p>{/if}
							<div class="rows">
								{#if b.syns.length}
									<div class="row">
										<span>Syn</span>
										{#each b.syns as s, idx (idx)}<span class="pill">{s}</span>{/each}
									</div>
								{/if}
								{#if b.ants.length}
									<div class="row">
										<span>Ant</span>
										{#each b.ants as a, idx (idx)}<span class="pill">{a}</span>{/each}
									</div>
								{/if}
							</div>
						</div>
					</div>
				</div>
			{/each}
		</div>
	{/if}

	{#if hasCards && !isEnded}
		<div class="swipe--buttons" aria-label="Review answer">
			{#each answerOptions as option (option.decision)}
				<button
					id={option.decision.replace('_', '-')}
					class:positive={option.isYes}
					onclick={() => programmaticSwipe(option.isYes, option.decision)}
					disabled={isClickAndSwiping || !isTopCardBack}
					aria-label={option.label}
				>
					<Icon icon={option.icon} width="26px" height="26px" aria-hidden="true" />
					<span>{option.label}</span>
					<kbd>{option.shortcut}</kbd>
				</button>
			{/each}
		</div>
	{/if}
</div>

<Modal open={modalOpen} title="More Info" handleClose={() => (modalOpen = false)}>
	{#snippet ModalBody()}
		<div class="whitespace-pre-wrap text-sm leading-relaxed">
			{modalContent}
		</div>
	{/snippet}
</Modal>

<style>
	*,
	*::before,
	*::after {
		box-sizing: border-box;
	}
	.swipe {
		width: 100%;
		min-height: 0;
		flex: 1;
		padding-block: 40px;
		display: flex;
		flex-direction: column;
		position: relative;
		overflow: hidden;
	}
	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		padding: 0;
		margin: -1px;
		overflow: hidden;
		clip: rect(0, 0, 0, 0);
		white-space: nowrap;
		border: 0;
	}
	.review-guidance {
		text-align: center;
		color: #334155;
		line-height: 1.35;
	}
	.review-guidance p {
		font-weight: 700;
	}
	.review-guidance span {
		display: block;
		margin-top: 2px;
		font-size: 0.8rem;
		color: #64748b;
	}
	.swipe--status {
		position: absolute;
		top: 50%;
		display: flex;
		justify-content: space-around;
		margin-top: -30px;
		z-index: 100;
		width: 100%;
		text-align: center;
		pointer-events: none;
	}
	.swipe--status .icon {
		font-size: 150px;
		transform: scale(0.3);
		transition: all 0.2s;
	}
	.swipe--cards {
		min-height: 0;
		flex: 1;
		padding-top: 24px;
		display: flex;
		position: relative;
		justify-content: center;
		align-items: flex-end;
	}

	.swipe--card {
		display: inline-block;
		width: 90vw;
		max-width: 400px;
		height: 100%;
		max-height: 600px;
		position: absolute;
		overflow: hidden;
		will-change: transform;
		touch-action: pan-y;
		backface-visibility: hidden;
		contain: layout paint;
		cursor: pointer;
		outline: none;
	}
	.swipe--card:focus-visible {
		box-shadow: 0 0 0 4px #dbeafe, 0 0 0 7px #2563eb;
	}
	/* 3D flip scaffolding */
	.swipe--card .card-inner {
		position: relative;
		width: 100%;
		height: 100%;
		transform-style: preserve-3d;
		transition: transform 0.35s ease;
		will-change: transform;
	}
	:global(.swipe--card.is-back) .card-inner {
		transform: rotateY(180deg);
	}

	.card-face {
		position: absolute;
		inset: 0;
		display: flex;
		gap: 8px;
		flex-direction: column;
		align-items: center;
		backface-visibility: hidden;
		border-radius: 8px;
		overflow-x: hidden;
		overflow-y: auto;
		overscroll-behavior: contain;
	}

	.card-front .q {
		margin-top: 24px;
		font-size: 28px;
		padding: 0 16px;
		pointer-events: none;
	}
	.card-back .a {
		margin-top: 24px;
		font-size: 20px;
		padding: 0 16px;
		pointer-events: none;
	}

	.card-back {
		transform: rotateY(180deg);
	}

	.headline {
		margin-top: 16px;
		font-size: clamp(1.5rem, 6vw, 1.9rem);
		text-align: center;
		overflow-wrap: anywhere;
	}
	.subtitle {
		margin-top: 6px;
		font-size: 15px;
		opacity: 0.7;
		text-align: center;
		overflow-wrap: anywhere;
	}
	.hint {
		margin-top: 10px;
		font-size: 16px;
		opacity: 0.8;
		text-align: center;
	}
	.lesson-date {
		position: absolute;
		bottom: 10px;
		left: 10px;
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
	}
	.chips {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
		align-self: flex-start;
	}
	.chip {
		font-size: 12px;
		padding: 2px 6px;
		border-radius: 999px;
	}
	.ipa {
		margin-top: 8px;
		font-size: 16px;
		opacity: 0.9;
		text-align: center;
	}
	.example {
		margin: 14px 16px;
		font-size: 16px;
		line-height: 1.4;
		white-space: pre-line;
		overflow-wrap: anywhere;
	}
	.rows {
		margin: 10px 12px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.row {
		display: flex;
		align-items: center;
		gap: 6px;
		flex-wrap: wrap;
	}
	.row > span:first-child {
		font-size: 12px;
		opacity: 0.6;
	}
	.pill {
		font-size: 12px;
		padding: 2px 6px;
		border-radius: 999px;
		background: #f3f4f6;
	}

	:global(.swipe--card.moving) {
		transition: none;
		cursor: grabbing;
	}
	:global(.swipe--card.click-and-swiping) {
		transition: transform 0.3s ease-in-out;
	}

	.swipe--buttons {
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		gap: 8px;
		padding-top: 20px;
		width: min(100%, 520px);
		margin-inline: auto;
	}
	.swipe--buttons button {
		cursor: pointer;
		min-width: 0;
		min-height: 64px;
		padding: 8px 6px;
		border: 1px solid #fecdd3;
		border-radius: 14px;
		background: #fff1f2;
		color: #9f1239;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 4px;
		flex-wrap: wrap;
		font-size: 0.8rem;
		font-weight: 700;
		transition: transform 150ms ease, background-color 150ms ease, border-color 150ms ease;
	}
	.swipe--buttons button.positive {
		border-color: #a7f3d0;
		background: #ecfdf5;
		color: #047857;
	}
	.swipe--buttons kbd {
		min-width: 1.25rem;
		padding: 1px 4px;
		border: 1px solid currentColor;
		border-radius: 5px;
		font: inherit;
		font-size: 0.65rem;
		opacity: 0.65;
	}
	.swipe--buttons button:hover {
		transform: translateY(-1px);
	}
	.swipe--buttons button:active {
		transform: translateY(0);
	}
	.swipe--buttons button:focus-visible {
		outline: 2px solid #0ea5e9; /* sky-500 */
		outline-offset: 2px;
	}

	.swipe--buttons button:disabled {
		opacity: 0.45;
		cursor: not-allowed;
	}

	@media (max-width: 420px) {
		.swipe {
			padding-block: 24px;
		}
		.swipe--buttons button {
			min-height: 58px;
			flex-direction: column;
			gap: 1px;
		}
		.swipe--buttons kbd {
			display: none;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.swipe--card .card-inner,
		:global(.swipe--card.click-and-swiping),
		.swipe--buttons button {
			transition-duration: 1ms;
		}
	}
</style>
