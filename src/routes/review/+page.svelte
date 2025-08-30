<script lang="ts">
  import { onMount } from "svelte";
  import QuestionCard from "$lib/components/QuestionCard.svelte";
  import QWordToMeaning from "$lib/components/QWordToMeaning.svelte";
  import SwipeCards from "$lib/components/SwipeCards.svelte";
  import { getWordList, updateReview } from "$lib/api/sheet";
  import { wordList, current, nextQuestion } from "$lib/stores/review";

  let progress = { total: 0, current: 0 };

  onMount(async () => {
    const items = await getWordList();
    wordList.set(items.sort(() => Math.random() - 0.5)); // 打散
    progress.total = items.length;
  });

  async function handleResult(e: CustomEvent<{ ok: boolean }>) {
    const item = $current;
    if (!item) return;

    await updateReview(item.id, e.detail.ok);
    progress.current += 1;
    nextQuestion();
  }
</script>

<div class="min-h-[100dvh] bg-[var(--bg)] flex items-center justify-center p-4">
  {#if $current}
    <SwipeCards wordList={$wordList} />
  {:else}
    <QuestionCard title="完成！" subtitle="今天的到期單字都複習完了 🎉">
      <a class="underline" href="/">回首頁</a>
    </QuestionCard>
  {/if}
</div>
