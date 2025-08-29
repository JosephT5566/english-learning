<script lang="ts">
  export let title = '';
  export let subtitle = '';
</script>

<section class="bg-[var(--card)] rounded-2xl shadow p-6 max-w-[680px] w-full">
  <h2 class="text-2xl font-extrabold text-[var(--ink)] mb-2">{title}</h2>
  {#if subtitle}<p class="text-[var(--ink-2)] mb-4">{subtitle}</p>{/if}
  <slot />
</section>
