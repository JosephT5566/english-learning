<script lang="ts">
  import { onMount } from "svelte";
  import { initGsiOnce, onSignInError, renderGoogleButton } from "$lib/auth";
  let container: HTMLDivElement;
  let error = $state("");
  onMount(() => {
    const unsubscribe = onSignInError(() => {
      error = "Sign-in did not finish. Please try again.";
    });
    try {
      initGsiOnce();
      renderGoogleButton(container);
    } catch {
      error =
        "Google sign-in is unavailable right now. Refresh the page to try again.";
    }
    return unsubscribe;
  });
</script>

<div class="google-signin-container" bind:this={container}></div>
{#if error}<p role="alert">{error}</p>{/if}

<style>
  .google-signin-container {
    min-height: 44px;
    max-width: 100%;
    overflow: hidden;
  }
  p {
    color: #8b3030;
    font-size: 0.88rem;
  }
</style>
