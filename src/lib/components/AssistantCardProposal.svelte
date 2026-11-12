<script lang="ts">
  import { onDestroy, tick } from "svelte";
  import { resolve } from "$app/paths";
  import { getProfile } from "$lib/auth";
  import { ApiClientError, createCard, createCards } from "$lib/api/client";
  import type { CardDetail } from "$lib/api/contracts";
  import type { CardDraft } from "$lib/management/json-cards";
  import {
    clearPendingAssistantProposal,
    createPendingAssistantProposal,
    savePendingAssistantProposal,
    type CardProposalPayload,
    type PendingAssistantProposal,
  } from "$lib/assistant/pending";
  import CardForm from "./CardForm.svelte";
  import Drawer from "./Drawer.svelte";

  type ProposalState = {
    proposal_id: string;
    status: "committed" | "dismissed";
    created_card_ids: string[];
  };
  let {
    proposal,
    restored = null,
    onstate,
  }: {
    proposal: CardProposalPayload;
    restored?: PendingAssistantProposal | null;
    onstate?: (state: ProposalState) => void;
  } = $props();
  type Row = {
    index: number;
    fields: CardDraft;
    selected: boolean;
    removed: boolean;
    key?: string;
  };
  // Original indices are stable identities; a removed row never shifts its warning to a neighbor.
  let rows = $state<Row[]>(
    proposal.drafts.map((fields, index) => ({
      index,
      fields: {
        ...fields,
        synonyms: [...fields.synonyms],
        antonyms: [...fields.antonyms],
      },
      selected: true,
      removed: false,
      ...(restored ? { key: restored.idempotencyKeys[index] } : {}),
    })),
  );
  const ownerSubject = getProfile()?.sub;
  let alive = true;
  onDestroy(() => {
    alive = false;
  });
  const current = () => alive && getProfile()?.sub === ownerSubject;
  let busy = $state(false);
  let uncertain = $state(Boolean(restored));
  let command = $state<PendingAssistantProposal | null>(restored);
  let error = $state("");
  let errorTitle = $state("");
  let archived = $state(false);
  let saveWarning = $state("");
  let outcome = $state<"committed" | "dismissed" | null>(null);
  let created = $state<CardDetail[]>([]);
  let editing = $state<Row | null>(null);
  let editTrigger: HTMLButtonElement | undefined;
  let resultHeading = $state<HTMLHeadingElement>();
  let alertElement = $state<HTMLDivElement>();
  let editorElement = $state<HTMLDivElement>();
  let fieldError = $state<{
    index: number;
    field: string;
    message: string;
  } | null>(null);
  const selected = $derived(rows.filter((row) => row.selected && !row.removed));
  const locked = $derived(busy || uncertain);

  async function closeEditor() {
    editing = null;
    fieldError = null;
    await tick();
    editTrigger?.focus();
  }
  function focusDraftForm(event?: Event) {
    event?.preventDefault();
    editorElement
      ?.querySelector<HTMLInputElement>('input[aria-label="Term"]')
      ?.focus();
  }
  async function edit(row: Row, trigger?: HTMLButtonElement) {
    editing = row;
    editTrigger = trigger;
    await tick();
    focusDraftForm();
  }
  async function remove(row: Row) {
    if (locked) return;
    row.removed = true;
    await tick();
    const next =
      rows.find((other) => !other.removed && other.index > row.index) ??
      rows.find((other) => !other.removed);
    const target = next
      ? document.getElementById(
          `proposal-${proposal.proposal_id}-edit-${next.index}`,
        )
      : document.getElementById(
          `proposal-${proposal.proposal_id}-confirm-region`,
        );
    target?.focus();
  }
  function apply(fields: CardDraft) {
    if (!editing || locked) return;
    editing.fields = fields;
    error = "";
    errorTitle = "";
    void closeEditor();
  }
  async function dismiss() {
    if (locked) return;
    try {
      if (ownerSubject)
        clearPendingAssistantProposal(ownerSubject, proposal.proposal_id);
    } catch {
      /* Clearing unavailable storage cannot change the user action. */
    }
    outcome = "dismissed";
    onstate?.({
      proposal_id: proposal.proposal_id,
      status: "dismissed",
      created_card_ids: [],
    });
    await tick();
    resultHeading?.focus();
  }
  function validationField(cause: ApiClientError, submitted: Row[]) {
    if (!Array.isArray(cause.details?.fields)) return null;
    for (const item of cause.details.fields) {
      if (!item || typeof item !== "object" || !Array.isArray(item.path))
        continue;
      const path: unknown[] = item.path.filter(
        (part: unknown) => part !== "body",
      );
      let row: Row | undefined;
      let field: unknown;
      if (submitted.length === 1) {
        row = submitted[0];
        field = path[0];
      } else if (
        path[0] === "cards" &&
        typeof path[1] === "number" &&
        path[2] === "fields"
      ) {
        row = submitted[path[1]];
        field = path[3];
      }
      if (row && typeof field === "string" && Object.hasOwn(row.fields, field))
        return {
          index: row.index,
          field,
          message:
            typeof item.message === "string"
              ? item.message
              : "Check this value.",
        };
    }
    return null;
  }
  const fieldLabels: Record<string, string> = {
    term: "Term",
    meaning: "Meaning",
    reading: "Reading",
    pronunciation: "Pronunciation",
    romanization: "Romanization",
    learned_on: "Learned on",
    part_of_speech: "Part of speech",
    part_of_speech_detail: "Type detail",
    target_language_definition: "Definition in the language",
    example_sentence: "Example sentence",
    example_translation: "Translation",
    example_source: "Source",
    synonyms: "Synonyms",
    antonyms: "Antonyms",
    note: "Note",
    supplementary_note: "Supplementary note",
  };
  async function highlightField() {
    await tick();
    if (!fieldError || !editorElement) return;
    const prefix = fieldLabels[fieldError.field];
    const label = [...editorElement.querySelectorAll("label")].find((label) =>
      label.textContent?.trim().startsWith(prefix),
    );
    const control =
      label?.querySelector<
        HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
      >("input,textarea,select") ??
      (label?.htmlFor ? document.getElementById(label.htmlFor) : null);
    if (control) {
      const details = control.closest("details");
      if (details) details.open = true;
      control.setAttribute("aria-invalid", "true");
      control.setAttribute(
        "aria-describedby",
        `proposal-${proposal.proposal_id}-field-error`,
      );
      control.focus();
    }
  }
  async function confirm() {
    if (busy || outcome || !selected.length || !ownerSubject || !current())
      return;
    const submitted = [...selected];
    if (!uncertain) {
      for (const row of submitted) row.key ??= crypto.randomUUID();
      command = createPendingAssistantProposal({
        ownerSubject,
        proposal_id: proposal.proposal_id,
        deck: proposal.deck,
        drafts: submitted.map((row) => row.fields),
        idempotencyKeys: submitted.map((row) => row.key!),
      });
    }
    if (!command) return;
    try {
      savePendingAssistantProposal(command);
      saveWarning = "";
    } catch {
      saveWarning =
        "The request can still be sent, but a reload may not restore it.";
    }
    busy = true;
    error = "";
    errorTitle = "";
    archived = false;
    const sent = command;
    try {
      const first = sent.drafts[0];
      const result =
        sent.drafts.length === 1
          ? [
              await createCard(
                { ...first, deck_id: sent.deck.id },
                sent.idempotencyKeys[0],
              ),
            ]
          : await createCards(sent.deck.id, {
              cards: sent.drafts.map((fields, index) => ({
                fields,
                idempotency_key: sent.idempotencyKeys[index],
              })),
            });
      if (!current()) return;
      created = result;
      outcome = "committed";
      uncertain = false;
      try {
        clearPendingAssistantProposal(ownerSubject, proposal.proposal_id);
      } catch {
        /* The API has confirmed success even if storage is unavailable. */
      }
      onstate?.({
        proposal_id: proposal.proposal_id,
        status: "committed",
        created_card_ids: result.map((card) => card.id),
      });
      await tick();
      resultHeading?.focus();
    } catch (cause) {
      if (!current()) return;
      uncertain =
        !(cause instanceof ApiClientError) ||
        cause.retryable ||
        cause.kind === "invalid_response" ||
        cause.kind === "network";
      if (cause instanceof ApiClientError && cause.code === "deck_archived") {
        archived = true;
        uncertain = true;
        error =
          "This deck is archived. Cards cannot be added. Your drafts are still here.";
      } else if (
        cause instanceof ApiClientError &&
        cause.code === "validation_failed" &&
        cause.status === 422
      ) {
        uncertain = false;
        fieldError = validationField(cause, submitted);
        error = cause.message;
        if (fieldError) {
          const row = rows.find((row) => row.index === fieldError?.index);
          if (row) {
            editing = row;
            editTrigger =
              (document.getElementById(
                `proposal-${proposal.proposal_id}-edit-${row.index}`,
              ) as HTMLButtonElement | null) ?? undefined;
            await highlightField();
          }
        }
      } else {
        errorTitle = uncertain
          ? "Result not confirmed"
          : "Cards were not added";
        error =
          cause instanceof Error
            ? cause.message
            : "Keep your drafts here and retry the same request.";
      }
      await tick();
      if (!fieldError) alertElement?.focus();
    } finally {
      if (current()) busy = false;
    }
  }
</script>

<section
  class="assistant-proposal"
  aria-label={`Card drafts for ${proposal.deck.title}`}
  aria-busy={busy}
>
  {#if outcome}
    <div class="proposal-result" aria-live="polite">
      <h3 tabindex="-1" bind:this={resultHeading}>
        {outcome === "committed"
          ? `Added to ${proposal.deck.title} · ${created.length} ${created.length === 1 ? "card" : "cards"}`
          : "Skipped. No cards were added."}
      </h3>
      {#if outcome === "committed"}
        <ul>
          {#each created as card (card.id)}<li>
              <a href={resolve("/cards/[cardId]", { cardId: card.id })}
                >{card.term}</a
              >
            </li>{/each}
        </ul>
      {/if}
    </div>
  {:else}
    <h3>Review drafts before adding</h3>
    <p>
      {proposal.deck.title} · {proposal.deck.target_language.toUpperCase()} · {selected.length}
      selected
    </p>
    {#if restored}<p class="proposal-restored">
        Your values are restored. Confirm again to retry the same request
        safely.
      </p>{/if}
    <ul class="proposal-rows">
      {#each rows as row (row.index)}
        {#if !row.removed}
          <li class="proposal-row">
            <label class="proposal-selection"
              ><input
                type="checkbox"
                aria-label={`Select ${row.fields.term}`}
                bind:checked={row.selected}
                disabled={locked}
              /><span
                ><strong>{row.fields.term}</strong><span
                  class="proposal-meaning">{row.fields.meaning}</span
                ></span
              ></label
            >
            {#each proposal.warnings.filter((warning) => warning.draft_index === row.index) as warning (warning)}
              <div class="proposal-warning">
                <span class="proposal-badge">duplicate term</span>
                {#each warning.existing_card_ids as cardId (cardId)}
                  <a href={resolve("/cards/[cardId]", { cardId })}
                    >Existing card: {warning.term}</a
                  >
                {/each}
              </div>
            {/each}
            <div class="proposal-row-actions">
              <button
                type="button"
                class="secondary-button"
                id={`proposal-${proposal.proposal_id}-edit-${row.index}`}
                aria-label={`Edit ${row.fields.term}`}
                disabled={locked}
                onclick={(event) => edit(row, event.currentTarget)}>Edit</button
              >
              <button
                type="button"
                class="secondary-button proposal-danger"
                aria-label={`Remove ${row.fields.term}`}
                disabled={locked}
                onclick={() => remove(row)}>Remove</button
              >
            </div>
          </li>
        {:else}
          <li class="proposal-removed">
            Removed {row.fields.term}.
            <button
              type="button"
              class="secondary-button"
              aria-label={`Undo remove ${row.fields.term}`}
              disabled={locked}
              onclick={() => {
                row.removed = false;
              }}>Undo</button
            >
          </li>
        {/if}
      {/each}
    </ul>
    {#if error}
      <div
        class="proposal-error"
        role="alert"
        tabindex="-1"
        bind:this={alertElement}
      >
        {#if errorTitle}<h4>{errorTitle}</h4>{/if}
        <p>{error}</p>
        {#if archived}<a
            href={`${resolve("/decks")}?language=${proposal.deck.target_language}&status=archived`}
            >Open deck management</a
          >{/if}
      </div>
    {/if}
    {#if saveWarning}<p class="proposal-error" role="alert">
        {saveWarning}
      </p>{/if}
    <div
      class="proposal-actions"
      tabindex="-1"
      id={`proposal-${proposal.proposal_id}-confirm-region`}
    >
      {#if uncertain}
        <button
          class="secondary-button"
          type="button"
          disabled={busy}
          onclick={confirm}>{busy ? "Adding…" : "Retry"}</button
        >
      {:else}
        <button
          class="proposal-confirm"
          id={`proposal-${proposal.proposal_id}-confirm`}
          type="button"
          disabled={busy || !selected.length}
          onclick={confirm}
          >{busy
            ? "Adding…"
            : `Add to ${proposal.deck.title} · ${selected.length} ${selected.length === 1 ? "card" : "cards"}`}</button
        >
      {/if}
      <button
        class="secondary-button"
        type="button"
        disabled={locked}
        onclick={dismiss}>Dismiss</button
      >
    </div>
  {/if}
</section>

{#if editing}
  <Drawer
    title={`Edit draft · ${editing.fields.term}`}
    onclose={closeEditor}
    onOpenAutoFocus={focusDraftForm}
  >
    <div bind:this={editorElement} class="proposal-editor">
      <p>
        {proposal.deck.title} · {proposal.deck.target_language.toUpperCase()}
      </p>
      {#if fieldError}<p
          class="proposal-error"
          id={`proposal-${proposal.proposal_id}-field-error`}
          role="alert"
        >
          {fieldError.message}
        </p>{/if}
      <CardForm
        language={proposal.deck.target_language}
        draft={editing.fields}
        inputIdPrefix={`proposal-${proposal.proposal_id}-${editing.index}`}
        submitLabel="Apply draft edits"
        onsave={apply}
        oncancel={closeEditor}
      />
    </div>
  </Drawer>
{/if}
