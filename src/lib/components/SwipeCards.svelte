<script lang="ts">
  import { onMount } from "svelte";

  type Card = { id: number; img: string; question?: string; answer?: string };
  export let cards: Card[] = [
    {
      id: 1,
      img: "https://placeimg.com/600/300/people",
      question: "Question 1",
      answer: "Answer 1",
    },
    {
      id: 2,
      img: "https://placeimg.com/600/300/animals",
      question: "Question 2",
      answer: "Answer 2",
    },
    {
      id: 3,
      img: "https://placeimg.com/600/300/nature",
      question: "Demo 3",
      answer: "This is a demo",
    },
    {
      id: 4,
      img: "https://placeimg.com/600/300/tech",
      question: "Demo 4",
      answer: "This is a demo",
    },
    {
      id: 5,
      img: "https://placeimg.com/600/300/arch",
      question: "Demo 5",
      answer: "This is a demo",
    },
  ];

  let root: HTMLDivElement; // .swipe
  let cardsWrap: HTMLDivElement; // .swipe--cards
  const scratch = new WeakMap<
    HTMLElement,
    {
      x: number;
      y: number;
      rot: number;
      down: boolean;
      startX: number;
      startY: number;
      pointerId: number;
      showAnswer: boolean;
    }
  >();

  let swipeX = 0;
  $: yesOpacity = swipeX > 0 ? Math.min(Math.abs(swipeX) / THRESHOLD, 1) : 0;
  $: noOpacity = swipeX < 0 ? Math.min(Math.abs(swipeX) / THRESHOLD, 1) : 0;

  let isClickAndSwiping = false;

  const THRESHOLD = 250;
  const MOVE_OUT_MULT = 1.5;

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
      if (i === 0) return; // top card will be handled by drag transform
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
    });

    function onDown(e: PointerEvent) {
      const s = scratch.get(el)!;
      if (el !== topCardEl()) return;
      el.setPointerCapture(e.pointerId);
      s.down = true;
      s.pointerId = e.pointerId;
      s.startX = e.clientX - s.x;
      s.startY = e.clientY - s.y;
      el.classList.add("moving");
    }

    function onMove(e: PointerEvent) {
      const s = scratch.get(el)!;
      if (!s.down || s.pointerId !== e.pointerId) return;
      s.x = e.clientX - s.startX;
      s.y = e.clientY - s.startY;
      s.rot = s.x * 0.03 * (s.y / 80);
      // apply transform imperatively
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

      // allow CSS transition
      el.classList.remove("moving");
      el.style.transition = "transform 0.3s ease-in-out";
      el.style.transform = `translate(${toX}px, ${toY}px) rotate(${s.rot}deg)`;
      el.dataset.removed = "1";
      swipeX = 0;

      setTimeout(() => {
        el.style.transition = "";
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

    el.addEventListener("pointerdown", onDown);
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerup", onUp);
    el.addEventListener("pointercancel", onUp);
  }

  function programmaticSwipe(isYes: boolean) {
    const el = topCardEl();
    if (!el) {
      return;
    }

    isClickAndSwiping = true;

    // mark as removed and fly out
    const s = scratch.get(el) || {
      x: 0,
      y: 0,
      rot: isYes ? -0.3 : 0.3,
      down: false,
      startX: 0,
      startY: 0,
      pointerId: -1,
      showAnswer: false,
    };
    scratch.set(el, s);
    s.x = isYes ? 200 : -200;
    s.y = -80;
    el.classList.add("moving");

    // small delay to ensure transition applies consistently
    requestAnimationFrame(() => {
      el.classList.remove("moving");
      const moveOutWidth = document.body.clientWidth * 1.2 * (isYes ? 1 : -1);
      el.style.transform = `translate(${moveOutWidth}px, -120px) rotate(${s.rot}deg)`;
      el.dataset.removed = "1";

      setTimeout(() => {
        el.style.transition = "";
        clearBadge();
        layoutStack();
      }, 280);
    });

    setTimeout(() => {
      isClickAndSwiping = false;
    }, 1000);
  }

  onMount(() => {
    // attach handlers to current cards
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
    {#each cards as c (c.id)}
      <div class="swipe--card {isClickAndSwiping ? 'click-and-swiping' : ''}">
        <img src={c.img} alt="" />
        {#if c.question}<h3 class="q">{c.question}</h3>{/if}
        {#if c.answer}<p class="a">{c.answer}</p>{/if}
      </div>
    {/each}
  </div>

  <div class="swipe--buttons">
    <button
      id="no"
      on:click={() => programmaticSwipe(false)}
      disabled={isClickAndSwiping}
      aria-label="No">✖</button
    >
    <button
      id="yes"
      on:click={() => programmaticSwipe(true)}
      disabled={isClickAndSwiping}
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
    left: 50%;
  }
  .swipe.swipe_yes .icon.yes {
    transform: scale(1);
  }
  .swipe.swipe_no .icon.no {
    transform: scale(1);
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
    background: #fff;
    padding-bottom: 40px;
    border-radius: 8px;
    overflow: hidden;
    position: absolute;
    will-change: transform;
    &.click-and-swiping {
      transition: all 0.3s ease-in-out;
    }
  }
  .swipe--card.moving {
    transition: none;
    cursor: grabbing;
  }
  .swipe--card img {
    max-width: 100%;
    display: block;
    pointer-events: none;
  }
  .swipe--card .q {
    margin-top: 32px;
    font-size: 32px;
    padding: 0 16px;
    pointer-events: none;
    transition:
      font-size 0.2s,
      opacity 0.2s;
  }
  .swipe--card .a {
    margin-top: 24px;
    font-size: 20px;
    padding: 0 16px;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.2s;
  }
  .swipe--card.show-answer .q {
    font-size: 22px;
    opacity: 0.8;
  }
  .swipe--card.show-answer .a {
    opacity: 1;
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
</style>
