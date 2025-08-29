<script lang="ts">
  import { createEventDispatcher } from "svelte";
  const dispatch = createEventDispatcher();
  export let word = "";
  export let answer = ""; // meaning
  let input = "";
  function submit() {
    const ok = input.trim().toLowerCase() === answer.trim().toLowerCase();
    dispatch("result", { ok, input });
  }
</script>

<div class="space-y-4">
  <div class="text-3xl font-black">{word}</div>
  <input
    class="w-full text-lg border-2 rounded-xl px-4 py-3 border-[var(--line)] focus:outline-none focus:ring-4 focus:ring-[var(--blue)]"
    bind:value={input}
    placeholder="輸入中文意思…"
    on:keydown={(e) => e.key === "Enter" && submit()}
  />
  <button
    class="bg-[var(--green)] text-white font-extrabold px-5 py-3 rounded-xl"
    on:click={submit}>送出</button
  >
</div>
