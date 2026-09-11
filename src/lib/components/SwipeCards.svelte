<svelte:options runes={true} />

<script lang="ts">
	import type { DueCard, ReviewDecision, ReviewSubmissionItem } from '$lib/api/contracts';
	import type { StudyDirection } from '$lib/types';
	import { canAnswerCard } from '$lib/review/interaction';
	import _clamp from 'lodash/clamp';
	import Icon from '@iconify/svelte';
	import classNames from 'classnames';
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
			// decide: 距離或速度達門檻就飛出
			const { vx } = velocityOf(s.moveHist);
			const fast = Math.abs(vx) > VELOCITY_THRESHOLD;
			if (Math.abs(s.x) >= THRESHOLD || fast) {
				flyOutAndRemove(fast ? vx : s.x, s.y, fast ? vx : undefined);
			} else {
				snapBack();
			}
		}

		// Click-to-flip (front<->back), but ignore if it was actually a drag
		function onClick() {
			const s = scratch.get(el)!;
			if (s.down || s.moved) {
				return; // was a drag, not a click
			}

			s.isBack = !s.isBack;
			el.classList.toggle('is-back', s.isBack);
			isTopCardBack = s.isBack;
			// Reset swipe UI when flipping to front
			if (!s.isBack) {
				swipeX = 0;
				clearBadge();
			}
		}

		el.addEventListener('pointerdown', onDown);
		el.addEventListener('pointermove', onMove);
		el.addEventListener('pointerup', onUp);
		el.addEventListener('pointercancel', onUp);
		el.addEventListener('click', onClick);
	}

	function programmaticSwipe(isYes: boolean, decision: ReviewDecision) {
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

			setTimeout(() => {
				el.classList.remove('click-and-swiping'); // clean up
				el.style.transition = '';
				clearBadge();
				updateLayoutStack();
			}, 300);
		});

		setTimeout(() => {
			isClickAndSwiping = false;
		}, 1000);
	}

	function updateFinishedCard(decision: ReviewDecision) {
		if (!currentWord) {
			return; // safety guard
		}
		onAnswer?.({
			card_id: currentWord.id,
			decision,
			expected_version: currentWord.review_state.version,
		});
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

	// Compute what to show on each face from a Card + direction + mode
	function faceFront(c: DueCard, dir: StudyDirection): FrontFace {
		if (dir === 'EN_ZH') {
			return {
				title: c.term,
				lessonDate: c.learned_on ? new Date(c.learned_on).toLocaleDateString('zh-TW') : null,
				chips: [c.part_of_speech, ...(c.note?.split(/,\s*/g) ?? [])].filter(Boolean) as string[],
				tags: c.tags.map((tag) => tag.display_name),
				phonics: c.pronunciation ?? c.reading ?? c.romanization ?? undefined,
			};
		} else {
			return {
				title: c.meaning || '—',
				lessonDate: c.learned_on ? new Date(c.learned_on).toLocaleDateString('zh-TW') : null,
				chips: [c.part_of_speech, ...(c.note?.split(/,\s*/g) ?? [])].filter(Boolean) as string[],
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
		els.forEach((el) => {
			if (!scratch.has(el)) {
				attachDrag(el); // 避免重複綁定事件
			}
		});
		updateLayoutStack();
	});
</script>

<div class="swipe" bind:this={root}>
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
				<div class="swipe--card rounded-2xl">
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
		<div class="swipe--buttons">
			<button
				id="no"
				onclick={() => programmaticSwipe(false, 'no')}
				disabled={isClickAndSwiping || !isTopCardBack}
				aria-label="No"
			>
				<Icon icon="solar:close-square-bold" class="text-rose-700" width="60px" height="60px" />
			</button>
			<button
				id="no-a-bit"
				class="ml-5 text-rose-700"
				onclick={() => programmaticSwipe(false, 'no_a_bit')}
				disabled={isClickAndSwiping || !isTopCardBack}
				aria-label="No A Bit"
			>
				<Icon icon="solar:close-square-outline" width="40px" height="40px" />
				<span>a bit</span>
			</button>
			<button
				id="yes-a-bit"
				class="mr-5 text-emerald-500"
				onclick={() => programmaticSwipe(true, 'yes_a_bit')}
				disabled={isClickAndSwiping || !isTopCardBack}
				aria-label="Yes A Bit"
			>
				<Icon icon="solar:check-square-outline" width="40px" height="40px" />
				<span>a bit</span>
			</button>
			<button
				id="yes"
				onclick={() => programmaticSwipe(true, 'yes')}
				disabled={isClickAndSwiping || !isTopCardBack}
				aria-label="Yes"
			>
				<Icon icon="solar:check-square-bold" class="text-emerald-500" width="60px" height="60px" />
			</button>
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
		width: 100vw;
		height: 100%;
		padding-block: 40px;
		display: flex;
		flex-direction: column;
		position: relative;
		overflow: hidden;
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
		flex-grow: 1;
		padding-top: 40px;
		display: flex;
		position: relative;
		justify-content: center;
		align-items: flex-end;
	}

	.swipe--card {
		display: inline-block;
		width: 90vw;
		max-width: 400px;
		height: 90%;
		max-height: 600px;
		position: absolute;
		overflow: hidden;
		will-change: transform;
		touch-action: none;
		backface-visibility: hidden;
		contain: layout paint;
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
		overflow: hidden;
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
		font-size: 28px;
		text-align: center;
	}
	.subtitle {
		margin-top: 6px;
		font-size: 15px;
		opacity: 0.7;
		text-align: center;
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
		display: flex;
		justify-content: center;
		gap: 8px;
		padding-top: 20px;
	}
	.swipe--buttons button {
		cursor: pointer;
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
		opacity: 0.5;
		cursor: not-allowed;
	}
</style>
