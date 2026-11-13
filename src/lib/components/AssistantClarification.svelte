<script lang="ts">
  import type { ClarificationQuestion } from "$lib/api/client";
  import type { ClarificationAnswer } from "$lib/assistant/history";
  import { historyCharacterLimit } from "$lib/assistant/history";

  let {
    question,
    answer,
    disabled = false,
    onanswer,
  }: {
    question: ClarificationQuestion;
    answer?: ClarificationAnswer;
    disabled?: boolean;
    onanswer: (choice: { optionId?: string; text?: string }) => void;
  } = $props();

  function submit(choice: Parameters<typeof onanswer>[0]) {
    if (unavailable || (!choice.optionId && !choice.text?.trim())) return;
    onanswer(choice);
  }

  const id = $props.id();
  let description = $state("");
  let selected = $state("");
  const deck = $derived(question.purpose === "deck");
  const locked = $derived(!!answer);
  const unavailable = $derived(disabled || locked);
  const chosen = $derived(answer?.option_id ?? selected);
  const answerLabel = $derived(
    answer?.text ??
      question.options.find((option) => option.id === answer?.option_id)?.label,
  );
</script>

<section
  class="clarify"
  class:is-locked={locked}
  aria-labelledby={`${id}-heading`}
>
  <h3 id={`${id}-heading`}>{question.question}</h3>
  <p class="meta">
    {deck
      ? "Deck choice · Listed by the server, never guessed"
      : question.allow_free_text
        ? "Term question · Choose one or write your own"
        : "Term question · Choose one"}
  </p>
  {#if deck}
    {#if question.options.length}
      <div
        class="deck-list"
        role="radiogroup"
        aria-labelledby={`${id}-heading`}
      >
        {#each question.options as option (option.id)}
          <label class="deck-row" class:is-selected={chosen === option.id}>
            <input
              type="radio"
              name={`${id}-deck`}
              value={option.id}
              checked={chosen === option.id}
              disabled={unavailable}
              onchange={() => (selected = option.id)}
            />
            <strong>{option.label}</strong>
          </label>
        {/each}
      </div>
      <div class="actions">
        <button
          type="button"
          class="primary"
          disabled={unavailable || !selected}
          onclick={() => submit({ optionId: selected })}>Use this deck</button
        >
      </div>
    {/if}
  {:else}
    <ul class="chips" aria-label="Answer options">
      {#each question.options as option (option.id)}
        <li>
          <button
            type="button"
            class="opt-chip"
            aria-pressed={answer?.option_id === option.id}
            disabled={unavailable}
            onclick={() => submit({ optionId: option.id })}
            >{option.label}</button
          >
        </li>
      {/each}
    </ul>
    {#if question.allow_free_text}
      <div class="free-text">
        <label for={`${id}-description`}>Or describe it yourself</label>
        <textarea
          id={`${id}-description`}
          rows="2"
          maxlength={historyCharacterLimit}
          value={answer?.text ?? description}
          disabled={unavailable}
          oninput={(event) => (description = event.currentTarget.value)}
        ></textarea>
      </div>
      <div class="actions">
        <button
          type="button"
          class="primary"
          disabled={unavailable || !description.trim()}
          onclick={() => submit({ text: description.trim() })}
          >Send description</button
        >
      </div>
    {/if}
  {/if}
  <p class="locked-flag" aria-live="polite">
    {answer ? `Answered: ${answerLabel}` : ""}
  </p>
</section>

<style>
  .clarify {
    margin-top: 0.85rem;
    padding-top: 0.15rem;
    min-width: 0;
  }
  h3 {
    margin: 0;
    font-family: Arial, sans-serif;
    font-size: 1.08rem;
    font-weight: 700;
    color: #20394e;
  }
  .meta {
    margin: 0.35rem 0 0;
    color: #60788c;
    font-size: 0.9rem;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin: 0.8rem 0 0;
    padding: 0;
    list-style: none;
  }
  button {
    min-height: 2.75rem;
    padding: 0.5rem 0.9rem;
    border: 1px solid #4075a655;
    border-radius: 0.65rem;
    background: #ffffffb8;
    color: #315f89;
    font: inherit;
    font-weight: 700;
    cursor: pointer;
    overflow-wrap: anywhere;
  }
  .opt-chip {
    border-radius: 999px;
    text-align: left;
  }
  .opt-chip[aria-pressed="true"],
  .primary,
  .is-locked .deck-row.is-selected {
    background: #315f89;
    border-color: #315f89;
    color: white;
  }
  button:disabled,
  .is-locked .deck-row:not(.is-selected) {
    opacity: 0.55;
    cursor: default;
  }
  .opt-chip[aria-pressed="true"]:disabled {
    opacity: 1;
  }
  .free-text {
    margin-top: 0.85rem;
    display: grid;
    gap: 0.45rem;
  }
  .free-text label {
    font-weight: 700;
    font-size: 0.9rem;
  }
  textarea {
    box-sizing: border-box;
    width: 100%;
    min-height: 2.75rem;
    padding: 0.55rem 0.75rem;
    border: 1px solid #4075a655;
    border-radius: 0.65rem;
    background: #ffffffcc;
    color: #20394e;
    font: inherit;
    resize: vertical;
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 0.8rem;
  }
  .deck-list {
    max-height: 19.25rem;
    overflow-y: auto;
    overscroll-behavior: contain;
    margin-top: 0.7rem;
    border: 1px solid #4075a633;
    border-radius: 0.75rem;
    background: #ffffff8c;
    scrollbar-width: thin;
    scrollbar-color: #4075a688 transparent;
  }
  .deck-row {
    box-sizing: border-box;
    display: flex;
    align-items: flex-start;
    gap: 0.65rem;
    width: 100%;
    min-height: 3.65rem;
    padding: 0.65rem 0.8rem;
    color: #20394e;
    cursor: pointer;
  }
  .deck-row + .deck-row {
    border-top: 1px solid #4075a633;
  }
  .deck-row strong {
    font-size: 0.98rem;
  }
  .deck-row input {
    margin-top: 0.3rem;
    accent-color: #4075a6;
  }
  .deck-row.is-selected {
    background: #4075a61f;
  }
  .locked-flag {
    margin: 0.55rem 0 0;
    color: #315f89;
    font-size: 0.9rem;
    font-weight: 700;
  }
  .locked-flag:empty {
    margin: 0;
  }
  :is(button, input, textarea):focus-visible {
    outline: 3px solid #4075a680;
    outline-offset: 2px;
  }
  @media (max-width: 640px) {
    .primary {
      width: 100%;
    }
  }
</style>
