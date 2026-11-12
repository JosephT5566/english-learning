<script lang="ts">
  import { tick } from "svelte";

  let {
    consent,
    busy,
    updateConsent,
    onConfirmWithdraw,
    onKeepConsent,
    presentation = "panel",
    error = "",
    failedAction,
    focusHeading = false,
    inputIdPrefix = "genai-consent",
    heading = "Allow AI meaning search?",
    description = "Your card text and search queries are sent to Google Vertex AI for semantic search. You can withdraw consent here at any time.",
    allowedMessage = "AI meaning search is allowed.",
    withdrawalMessage = "Withdrawing consent deletes your existing embeddings and stops AI meaning search. It cannot recall card text or search queries already sent to Google Vertex AI.",
  }: {
    consent: "unknown" | "required" | "granted" | "confirm-withdraw";
    busy: boolean;
    updateConsent: (action: "read" | "grant" | "withdraw") => Promise<void>;
    onConfirmWithdraw: () => void;
    onKeepConsent: () => void;
    presentation?: "chip" | "panel";
    error?: string;
    failedAction?: "read" | "grant" | "withdraw";
    focusHeading?: boolean;
    inputIdPrefix?: string;
    heading?: string;
    description?: string;
    allowedMessage?: string;
    withdrawalMessage?: string;
  } = $props();

  let panelHeading = $state<HTMLHeadingElement>();
  let alert = $state<HTMLParagraphElement>();
  let previousConsent = "unknown";
  $effect(() => {
    const shouldFocus =
      presentation === "panel" &&
      ((consent === "required" &&
        (focusHeading || previousConsent === "confirm-withdraw")) ||
        (consent === "confirm-withdraw" &&
          previousConsent !== "confirm-withdraw"));
    previousConsent = consent;
    if (shouldFocus) void tick().then(() => panelHeading?.focus());
  });
  $effect(() => {
    if (presentation === "panel" && error)
      void tick().then(() => alert?.focus());
  });

  async function keepConsent() {
    onKeepConsent();
    await tick();
    document.getElementById(`${inputIdPrefix}-manage`)?.focus();
  }
</script>

{#if presentation === "chip"}
  {#if consent === "granted" || consent === "confirm-withdraw"}
    <button
      id={`${inputIdPrefix}-manage`}
      type="button"
      class="chip secondary"
      aria-label={`${allowedMessage} Manage AI consent`}
      aria-expanded={consent === "confirm-withdraw"}
      disabled={busy || consent === "confirm-withdraw"}
      onclick={onConfirmWithdraw}>AI on · Manage</button
    >
  {/if}
{:else if consent !== "granted"}
  <section class="consent" aria-label="AI consent" aria-busy={busy}>
    {#if consent === "required"}
      <h2 bind:this={panelHeading} tabindex="-1">{heading}</h2>
      <p>{description}</p>
      <details>
        <summary>Details</summary>
        <p>{withdrawalMessage}</p>
      </details>
      {#if error}
        <p class="error" role="alert" tabindex="-1" bind:this={alert}>
          {error}
        </p>
      {/if}
      <button
        type="button"
        disabled={busy}
        onclick={() => updateConsent("grant")}
        >{busy
          ? "Granting…"
          : failedAction === "grant" && error
            ? "Retry grant"
            : "Grant consent"}</button
      >
    {:else if consent === "confirm-withdraw"}
      <h2 bind:this={panelHeading} tabindex="-1">Withdraw AI consent?</h2>
      <p>{withdrawalMessage}</p>
      {#if error}
        <p class="error" role="alert" tabindex="-1" bind:this={alert}>
          {error}
        </p>
      {/if}
      {#if busy}<p role="status">Withdrawing consent…</p>{/if}
      <div class="consent-actions">
        <button
          type="button"
          class="secondary"
          disabled={busy}
          onclick={keepConsent}>Keep consent</button
        >
        <button
          type="button"
          class="danger"
          disabled={busy}
          onclick={() => updateConsent("withdraw")}
          >{busy
            ? "Withdrawing…"
            : failedAction === "withdraw" && error
              ? "Retry withdrawal"
              : "Confirm withdrawal"}</button
        >
      </div>
    {:else if busy}
      <h2>Checking AI consent…</h2>
      <p>{description}</p>
      <p role="status">
        Please wait. AI features are unavailable until consent is checked.
      </p>
    {:else}
      <h2>AI consent unavailable</h2>
      <p>{description}</p>
      {#if error}
        <p class="error" role="alert" tabindex="-1" bind:this={alert}>
          {error}
        </p>
      {/if}
      <button type="button" onclick={() => updateConsent("read")}
        >Retry consent check</button
      >
    {/if}
  </section>
{/if}

<style>
  .consent {
    margin-top: 1rem;
    padding: 1rem;
    border: 1px solid rgba(64, 117, 166, 0.22);
    border-radius: 0.9rem;
    background: rgba(255, 255, 255, 0.65);
    color: #20394e;
    font-size: 0.9rem;
  }
  h2 {
    margin: 0;
    font-family: Arial, sans-serif;
    font-size: 1rem;
    font-weight: 700;
  }
  p {
    margin: 0.5rem 0 0.8rem;
  }
  details {
    margin: 0.65rem 0;
  }
  summary {
    color: #315f89;
    cursor: pointer;
  }
  .consent-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.65rem;
  }
  button.secondary {
    background: rgba(255, 255, 255, 0.72);
    color: #315f89;
  }
  button.danger {
    background: #fff3f1;
    border-color: #a34646;
    color: #a34646;
  }
  .chip {
    border-radius: 999px;
    padding: 0.5rem 0.8rem;
    font-size: 0.8rem;
    white-space: nowrap;
  }
  .error {
    color: #a34646;
    border-left: 3px solid #a34646;
    padding-left: 0.65rem;
  }
  button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 2.75rem;
    min-height: 2.75rem;
    padding: 0.65rem 0.9rem;
    border: 1px solid #315f89;
    border-radius: 0.65rem;
    background: #315f89;
    color: white;
    font: inherit;
    font-weight: 700;
    cursor: pointer;
  }
  button:disabled {
    cursor: not-allowed;
    opacity: 0.55;
  }
  :is(button, summary):focus-visible {
    outline: 3px solid rgba(64, 117, 166, 0.5);
    outline-offset: 3px;
  }
</style>
