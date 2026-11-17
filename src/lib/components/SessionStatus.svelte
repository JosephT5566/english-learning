<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { page } from "$app/state";
  import { authSession, authNotice, signInOpen } from "$lib/stores/auth";
  import { pendingReviewInfo } from "$lib/review/pending";
  import { enterGuestSession } from "$lib/auth";

  let guestError = $state("");
  let guestPending = $derived(
    $authSession.kind === "guest" && $pendingReviewInfo.count > 0,
  );
  let notice = $derived($authNotice);
  let expired = $derived(
    $authSession.kind === "expired" ||
      notice?.kind === "expired" ||
      notice?.kind === "other-tab",
  );
  let visible = $derived(
    guestPending || expired || notice !== null || !!guestError,
  );
  let tone = $derived(
    guestError || notice?.kind === "error" ? "red" : expired ? "amber" : "blue",
  );
  let canDismiss = $derived(
    !guestPending && !expired && notice?.kind !== "signing-in",
  );
  let profile = $derived(
    $authSession.kind === "authenticated" || $authSession.kind === "expired"
      ? $authSession.profile
      : null,
  );
  async function guest() {
    const result = enterGuestSession();
    if (result.ok) {
      guestError = "";
      await goto(resolve("/review"));
    } else guestError = result.error;
  }
</script>

{#if visible}
  <section
    class="session-strip {tone}"
    role={tone === "red" ? "alert" : "status"}
    aria-live="polite"
    aria-label="Session status"
    data-testid="session-status"
  >
    <span class="message">
      {#if guestError}
        {guestError}
      {:else if notice?.kind === "error"}
        {#if notice.email}<strong>{notice.email}</strong> can't open private decks.
          Try another Google account, or practise as a guest.
        {:else}Sign-in did not finish. Please try again.{/if}
      {:else if notice?.kind === "signing-in"}
        <span class="spinner" aria-hidden="true"></span> Signing you in&hellip;
      {:else if guestPending}
        <strong>Guest practice.</strong> Progress isn't saved. {$pendingReviewInfo.count}
        answers for {$pendingReviewInfo.email ?? "your account"} stay on this device
        until you sign in with that account.
      {:else if notice?.kind === "pending-expired"}
        Saved answers expired and were not sent
      {:else if notice?.kind === "other-tab"}
        <strong>You signed out in another tab.</strong>
      {:else if expired}
        <strong>Session ended.</strong>
        {#if $pendingReviewInfo.count > 0}
          {$pendingReviewInfo.count} answers are saved here and will be sent after
          you sign in.
        {:else if page.url.pathname.includes("/assistant")}
          Sign in again to send. Your message stays in the box.
        {:else}
          Sign in again to continue.
        {/if}
      {:else if notice?.kind === "signed-out"}
        <strong>You signed out on this device.</strong>
      {:else if notice?.kind === "account-changed"}
        <strong
          >Signed in as {profile?.name ||
            profile?.email ||
            "your account"}.</strong
        >
        {notice.count} unsent answers from {notice.previousEmail ||
          "the previous account"} were removed.
      {:else if notice?.kind === "saved"}
        <strong
          >Signed in as {profile?.name ||
            profile?.email ||
            "your account"}.</strong
        >
        Your {notice.count} saved answers were sent.
      {/if}
    </span>
    {#if guestPending}
      <button class="primary" onclick={() => signInOpen.set(true)}
        >Sign in to send</button
      >
      {#if notice?.kind === "error"}<button onclick={guest}
          >Continue as guest</button
        >{/if}
    {:else if expired}
      <button class="primary" onclick={() => signInOpen.set(true)}
        >Sign in again</button
      >
      <button onclick={guest}>Continue as guest</button>
    {:else if notice?.kind === "error" || notice?.kind === "signed-out"}
      <button onclick={guest}>Continue as guest</button>
    {/if}
    {#if canDismiss}
      <button
        class="dismiss"
        aria-label="Dismiss session notice"
        onclick={() => {
          authNotice.set(null);
          guestError = "";
        }}>&times;</button
      >
    {/if}
  </section>
{/if}

<style>
  .session-strip {
    display: flex;
    align-items: center;
    gap: 0.65rem;
    flex-wrap: wrap;
    box-sizing: border-box;
    width: calc(100% - 1.5rem);
    max-width: 62.5rem;
    margin: 0.4rem auto 0;
    padding: 0.5rem 0.65rem 0.5rem 0.75rem;
    border: 1px solid rgba(64, 117, 166, 0.22);
    border-left: 4px solid #4075a6;
    border-radius: 0.7rem;
    background: rgba(255, 255, 255, 0.86);
    color: #20394e;
    font-size: 0.84rem;
  }
  .amber {
    border-left-color: #b46b39;
  }
  .red {
    border-left-color: #a34646;
  }
  .message {
    flex: 1;
    min-width: min(12rem, 100%);
    overflow-wrap: anywhere;
  }
  button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 44px;
    padding: 0 0.75rem;
    border: 1px solid rgba(64, 117, 166, 0.45);
    border-radius: 0.65rem;
    background: rgba(255, 255, 255, 0.72);
    color: #315f89;
    font-size: 0.84rem;
    font-weight: 700;
    cursor: pointer;
  }
  button.primary {
    color: white;
    background: #315f89;
    border-color: #315f89;
  }
  button.dismiss {
    width: 44px;
    padding: 0;
    color: #60788c;
    font-size: 1.2rem;
  }
  button:focus-visible {
    outline: 3px solid rgba(64, 117, 166, 0.45);
    outline-offset: 2px;
  }
  .spinner {
    display: inline-block;
    width: 1rem;
    height: 1rem;
    margin-right: 0.4rem;
    vertical-align: middle;
    border: 2px solid rgba(64, 117, 166, 0.25);
    border-top-color: #315f89;
    border-radius: 999px;
    animation: spin 1s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .spinner {
      animation: none;
    }
  }
</style>
