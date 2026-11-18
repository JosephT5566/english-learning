<script lang="ts">
  import { onMount } from "svelte";
  import SwipeCards from "$lib/components/SwipeCards.svelte";
  import {
    getPublicReviewCards,
    sampleGuestCards,
  } from "$lib/api/public-review";
  import { toPublicStudyCard, type StudyCard } from "$lib/review/presentation";

  type Session =
    | { kind: "loading" }
    | { kind: "error"; message: string }
    | { kind: "empty" }
    | { kind: "ready"; cards: StudyCard[]; batch: number; complete: boolean };
  let session: Session = $state({ kind: "loading" });
  let pool: import("$lib/api/contracts").PublicReviewCard[] | undefined;
  let offline = $state(false);
  let snapshotDate = $state("");
  let batch = 0;
  let request: AbortController | undefined;

  async function loadBatch() {
    if (request) return;
    if (pool !== undefined) {
      startRound();
      return;
    }
    const controller = new AbortController();
    request = controller;
    session = { kind: "loading" };
    try {
      const data = await getPublicReviewCards(controller.signal);
      if (controller.signal.aborted) return;
      pool = data.items;
      snapshotDate = new Date(data.generated_at).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        timeZone: "UTC",
      });
      startRound();
    } catch (error) {
      if (controller.signal.aborted) return;
      session = {
        kind: "error",
        message:
          error instanceof Error
            ? error.message
            : "Card review is unavailable.",
      };
    } finally {
      if (request === controller) request = undefined;
    }
  }

  function startRound() {
    const cards = sampleGuestCards(pool ?? []);
    session = cards.length
      ? {
          kind: "ready",
          cards: cards.map(toPublicStudyCard),
          batch: ++batch,
          complete: false,
        }
      : { kind: "empty" };
  }

  onMount(() => {
    const updateConnectivity = () => {
      offline = navigator.onLine === false;
    };
    updateConnectivity();
    window.addEventListener("online", updateConnectivity);
    window.addEventListener("offline", updateConnectivity);
    void loadBatch();
    return () => {
      window.removeEventListener("online", updateConnectivity);
      window.removeEventListener("offline", updateConnectivity);
      request?.abort();
      pool = undefined;
    };
  });
</script>

<svelte:head><title>Guest review - English Learning</title></svelte:head>
<section class="mx-auto flex w-full max-w-3xl flex-1 flex-col px-4 pb-6">
  {#if session.kind === "loading"}
    <p role="status" class="py-12 text-center">Loading cards...</p>
  {:else if session.kind === "error"}
    <div class="py-10 text-center">
      <h2 class="text-xl font-bold">Review unavailable</h2>
      <p role="alert" class="my-3">{session.message}</p>
      <button
        class="min-h-11 rounded-lg bg-slate-800 px-5 text-white disabled:opacity-50"
        onclick={() => void loadBatch()}>Try again</button
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
    {#if offline}
      <p class="mt-3 text-center text-sm text-[#60788c]">
        Offline · saved copy from {snapshotDate}
      </p>
    {/if}
    {#if session.complete}
      <button
        class="mx-auto min-h-11 rounded-lg bg-slate-800 px-5 text-white"
        onclick={() => void loadBatch()}>Practice again</button
      >
    {/if}
  {/if}
</section>
