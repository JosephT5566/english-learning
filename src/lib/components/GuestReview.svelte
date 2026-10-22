<script lang="ts">
  import { onMount } from "svelte";
  import { resolve } from "$app/paths";
  import SwipeCards from "$lib/components/SwipeCards.svelte";
  import {
    getPublicReviewCards,
    PublicReviewError,
  } from "$lib/api/public-review";
  import { toPublicStudyCard, type StudyCard } from "$lib/review/presentation";

  type Session =
    | { kind: "loading" }
    | { kind: "error"; message: string }
    | { kind: "empty" }
    | { kind: "ready"; cards: StudyCard[]; batch: number; complete: boolean };
  let session: Session = $state({ kind: "loading" });
  let cooldown = $state(0);
  let batch = 0;
  let request: AbortController | undefined;
  let timer: ReturnType<typeof setInterval> | undefined;

  async function loadBatch() {
    if (request || cooldown > 0) return;
    const controller = new AbortController();
    request = controller;
    session = { kind: "loading" };
    try {
      const data = await getPublicReviewCards(controller.signal);
      if (controller.signal.aborted) return;
      session = data.items.length
        ? {
            kind: "ready",
            cards: data.items.map(toPublicStudyCard),
            batch: ++batch,
            complete: false,
          }
        : { kind: "empty" };
    } catch (error) {
      if (controller.signal.aborted) return;
      session = {
        kind: "error",
        message:
          error instanceof Error
            ? error.message
            : "Card review is unavailable.",
      };
      if (error instanceof PublicReviewError && error.retryAfterSeconds > 0) {
        const until = Date.now() + error.retryAfterSeconds * 1000;
        cooldown = error.retryAfterSeconds;
        timer = setInterval(() => {
          cooldown = Math.max(0, Math.ceil((until - Date.now()) / 1000));
          if (!cooldown) clearInterval(timer);
        }, 250);
      }
    } finally {
      if (request === controller) request = undefined;
    }
  }

  onMount(() => {
    void loadBatch();
    return () => {
      request?.abort();
      clearInterval(timer);
    };
  });
</script>

<svelte:head><title>Guest review - English Learning</title></svelte:head>
<section class="mx-auto flex w-full max-w-3xl flex-1 flex-col px-4 pb-6">
  <div class="mb-3 text-center">
    <h1 class="text-2xl font-bold text-slate-800">Guest review</h1>
    <p class="text-sm text-slate-600">
      Progress is not saved. Practice a random batch of public cards.
    </p>
    <a
      class="inline-flex min-h-11 items-center text-sm underline"
      href={resolve("/")}>Home / sign in</a
    >
  </div>
  {#if session.kind === "loading"}
    <p role="status" class="py-12 text-center">Loading cards...</p>
  {:else if session.kind === "error"}
    <div class="py-10 text-center">
      <h2 class="text-xl font-bold">Review unavailable</h2>
      <p role="alert" class="my-3">{session.message}</p>
      <button
        class="min-h-11 rounded-lg bg-slate-800 px-5 text-white disabled:opacity-50"
        disabled={cooldown > 0}
        onclick={() => void loadBatch()}
        >{cooldown > 0 ? `Try again in ${cooldown}s` : "Try again"}</button
      >
    </div>
  {:else if session.kind === "empty"}
    <div class="py-10 text-center">
      <h2 class="text-xl font-bold">No public cards available</h2>
      <p class="mt-3">Come back when a collection is available.</p>
    </div>
  {:else}
    {#key session.batch}
      <SwipeCards
        wordList={session.cards}
        onComplete={() => {
          if (session.kind === "ready") session.complete = true;
        }}
      />
    {/key}
    {#if session.complete}
      <button
        class="mx-auto min-h-11 rounded-lg bg-slate-800 px-5 text-white"
        onclick={() => void loadBatch()}>Practice again</button
      >
    {/if}
  {/if}
</section>
