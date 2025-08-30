<svelte:options runes={true} />

<script lang="ts">
  import type { WordItem } from "$lib/types";

  // 透過 runes 取得 props
  let { wordList }: { wordList: WordItem[] } = $props();

  let root: HTMLDivElement; // .swipe
  let cardsWrap: HTMLDivElement; // .swipe--cards

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
  };
  const scratch = new WeakMap<HTMLElement, Scratch>();

  // UI state（runes）
  let swipeX = $state(0);
  let isTopCardBack = $state(false);
  let isClickAndSwiping = $state(false);

  const THRESHOLD = 250; // fly-out decision
  const MOVE_OUT_MULT = 1.5;

  const yesOpacity = $derived(
    swipeX > 0 ? Math.min(Math.abs(swipeX) / THRESHOLD, 1) : 0
  );
  const noOpacity = $derived(
    swipeX < 0 ? Math.min(Math.abs(swipeX) / THRESHOLD, 1) : 0
  );

  function topCardEl(): HTMLElement | null {
    // first non-removed card (highest z) is the last child
    const els = Array.from(
      cardsWrap.querySelectorAll<HTMLElement>(".swipe--card")
    );
    return els.find((el) => !el.dataset.removed) || null;
  }

  function layoutStack() {
    const els = Array.from(
      cardsWrap.querySelectorAll<HTMLElement>(".swipe--card")
    ).filter((el) => !el.dataset.removed);
    els.forEach((el, i) => {
      const scale = (20 - i) / 20;
      const translateY = -30 * i;
      const opacity = (10 - i) / 10;
      el.style.zIndex = String(els.length - i);
      if (i === 0) {
        return; // top card will be handled by drag transform
      }

      el.style.transform = `scale(${scale}) translateY(${translateY}px)`;
      el.style.opacity = String(opacity);
    });
  }

  function setBadge(x: number) {
    root.classList.toggle("swipe_yes", x > 10);
    root.classList.toggle("swipe_no", x < -10);
  }

  function clearBadge() {
    root.classList.remove("swipe_yes", "swipe_no");
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
    });

    function onDown(e: PointerEvent) {
      const s = scratch.get(el)!;
      // Only the top card AND only on back side can start dragging
      if (el !== topCardEl() || !s.isBack || isClickAndSwiping) {
        return;
      }

      el.setPointerCapture(e.pointerId);
      s.down = true;
      s.pointerId = e.pointerId;
      s.startX = e.clientX - s.x;
      s.startY = e.clientY - s.y;
      s.moved = false;
      el.classList.add("moving");
    }

    function onMove(e: PointerEvent) {
      const s = scratch.get(el)!;
      if (!s.down || s.pointerId !== e.pointerId) return;
      s.x = e.clientX - s.startX;
      s.y = e.clientY - s.startY;
      s.rot = s.x * 0.03 * (s.y / 80);
      if (Math.abs(s.x) > 3 || Math.abs(s.y) > 3) s.moved = true;

      // Only reflect swipe UI on the back side
      el.style.transform = `translate(${s.x}px, ${s.y}px) rotate(${s.rot}deg)`;
      swipeX = s.x;
      setBadge(s.x);
    }

    function flyOutAndRemove(directionX: number, y: number) {
      const s = scratch.get(el)!;
      const moveOutWidth = document.body.clientWidth * 1.2;
      const toX =
        directionX > 0
          ? Math.max(Math.abs(s.x), moveOutWidth)
          : -Math.max(Math.abs(s.x), moveOutWidth);
      const toY =
        y >= 0 ? Math.abs(y) * MOVE_OUT_MULT : -Math.abs(y) * MOVE_OUT_MULT;

      el.classList.remove("moving");
      el.style.transform = `translate(${toX}px, ${toY}px) rotate(${s.rot}deg)`;
      el.dataset.removed = "1";
      swipeX = 0;
      isTopCardBack = false; // reset state

      setTimeout(() => {
        clearBadge();
        layoutStack();
      }, 320);
    }

    function snapBack() {
      el.classList.remove("moving");
      el.style.transition = "transform 0.25s ease";
      el.style.transform = "";
      setTimeout(() => {
        el.style.transition = "";
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
      // decide
      Math.abs(s.x) < THRESHOLD ? snapBack() : flyOutAndRemove(s.x, s.y);
    }

    // Click-to-flip (front<->back), but ignore if it was actually a drag
    function onClick() {
      const s = scratch.get(el)!;
      if (s.down || s.moved) {
        return; // was a drag, not a click
      }

      s.isBack = !s.isBack;
      el.classList.toggle("is-back", s.isBack);
      isTopCardBack = s.isBack;
      // Reset swipe UI when flipping to front
      if (!s.isBack) {
        swipeX = 0;
        clearBadge();
      }
    }

    el.addEventListener("pointerdown", onDown);
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerup", onUp);
    el.addEventListener("pointercancel", onUp);
    el.addEventListener("click", onClick);
  }

  function programmaticSwipe(isYes: boolean) {
    const el = topCardEl();
    if (!el || isClickAndSwiping) {
      return;
    }

    const s = scratch.get(el);
    // Only allow button swipe on back side
    if (!s?.isBack) {
      return;
    }

    isClickAndSwiping = true;
    el.classList.add("click-and-swiping");

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
    };
    scratch.set(el, st);
    st.x = isYes ? 200 : -200;
    st.y = -80;
    isTopCardBack = false; // reset state

    requestAnimationFrame(() => {
      const moveOutWidth = document.body.clientWidth * 1.2 * (isYes ? 1 : -1);
      el.style.transform = `translate(${moveOutWidth}px, -120px) rotate(${st.rot}deg)`;
      el.dataset.removed = "1";

      setTimeout(() => {
        el.classList.remove("click-and-swiping"); // clean up
        el.style.transition = "";
        clearBadge();
        layoutStack();
      }, 300);
    });

    setTimeout(() => {
      isClickAndSwiping = false;
    }, 1000);
  }

  $effect(() => {
    if (!cardsWrap) {
      return;
    }

    const els = Array.from(
      cardsWrap.querySelectorAll<HTMLElement>(".swipe--card")
    );
    els.forEach(attachDrag);
    layoutStack();
  });
</script>

<div class="swipe" bind:this={root}>
  <div class="swipe--status">
    <span class="icon no" style="opacity:{noOpacity}">✖</span>
    <span class="icon yes" style="opacity:{yesOpacity}">♥</span>
  </div>

  <div class="swipe--cards" bind:this={cardsWrap}>
    {#each wordList as c, i (`${c.id ?? 'no-id'}-${i}`)}
      <div class="swipe--card">
        <!-- 3D flip container -->
        <div class="card-inner">
          <!-- FRONT -->
          <div class="card-face card-front">
            {#if c.content}<h3 class="q">{c.content}</h3>{/if}
          </div>
          <!-- BACK -->
          <div class="card-face card-back">
            {#if c.chineseExplain}<p class="a">{c.chineseExplain}</p>{/if}
            <!-- You can add more back-side UI here -->
          </div>
        </div>
      </div>
    {/each}
  </div>

  <div class="swipe--buttons">
    <button
      id="no"
      on:click={() => programmaticSwipe(false)}
      disabled={isClickAndSwiping || !isTopCardBack}
      aria-label="No">✖</button
    >
    <button
      id="yes"
      on:click={() => programmaticSwipe(true)}
      disabled={isClickAndSwiping || !isTopCardBack}
      aria-label="Yes">♥</button
    >
  </div>
</div>

<style>
  *,
  *::before,
  *::after {
    box-sizing: border-box;
  }
  :global(body) {
    background: #ccfbfe;
    overflow: hidden;
    font-family: sans-serif;
  }

  .swipe {
    width: 100vw;
    height: 85vh;
    display: flex;
    flex-direction: column;
    position: relative;
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
    font-size: 100px;
    transform: scale(0.3);
    transition: all 0.2s;
    width: 100px;
  }
  .swipe--cards {
    flex-grow: 1;
    padding-top: 40px;
    display: flex;
    justify-content: center;
    align-items: flex-end;
  }

  .swipe--card {
    display: inline-block;
    width: 90vw;
    max-width: 400px;
    height: 70vh;
    position: absolute;
    border-radius: 8px;
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
  :global(.swipe--card.is-back) {
    border: solid 2px #888;
  }
  :global(.swipe--card.is-back) .card-inner {
    transform: rotateY(180deg);
  }

  .card-face {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    backface-visibility: hidden;
    background: #fff;
    border-radius: 8px;
    overflow: hidden;
  }
  .card-front img,
  .card-back img {
    max-width: 100%;
    display: block;
    pointer-events: none;
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

  :global(.swipe--card.moving) {
    transition: none;
    cursor: grabbing;
  }
  :global(.swipe--card.click-and-swiping) {
    transition: transform 0.3s ease-in-out;
  }

  .swipe--buttons {
    flex: 0 0 100px;
    text-align: center;
    padding-top: 20px;
  }
  .swipe--buttons button {
    border-radius: 50%;
    line-height: 60px;
    width: 60px;
    border: 0;
    background: #fff;
    display: inline-block;
    margin: 0 8px;
    font-size: 32px;
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
