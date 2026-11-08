<script lang="ts">
  import { untrack } from "svelte";
  import SendIcon from "@lucide/svelte/icons/arrow-up";
  import GenAIConsentPanel from "$lib/components/GenAIConsentPanel.svelte";
  import { authSession } from "$lib/stores/auth";
  import {
    ApiClientError,
    getGenAIConsent,
    grantGenAIConsent,
    streamAssistantReply,
    withdrawGenAIConsent,
    type AssistantMessage,
    type AssistantTool,
  } from "$lib/api/client";

  type Turn = {
    question: string;
    reply: string;
    tools: AssistantTool[];
    complete: boolean;
    issue: string;
  };

  const toolLabels: Record<string, string> = {
    search_cards: "Search cards",
    get_due_cards: "Get due cards",
    get_review_stats: "Get review stats",
  };
  // Match the API defaults while keeping the full transcript visible locally.
  const historyCharacterLimit = 12000;
  const historyMessageLimit = 20;
  let turns = $state<Turn[]>([]);
  let draft = $state("");
  let consent = $state<"unknown" | "required" | "granted" | "confirm-withdraw">(
    "unknown",
  );
  let consentBusy = $state(false);
  let sending = $state(false);
  let formError = $state("");
  let generation: AbortController | undefined;
  let sessionVersion = 0;

  $effect(() => {
    const session = $authSession;
    untrack(() => {
      turns = [];
      draft = "";
      consent = "unknown";
      consentBusy = false;
      sending = false;
      formError = "";
      if (session.kind === "authenticated") void updateConsent("read");
    });
    return () => {
      sessionVersion++;
      generation?.abort();
    };
  });

  async function updateConsent(action: "read" | "grant" | "withdraw") {
    if (consentBusy || sending) return;
    const version = sessionVersion;
    consentBusy = true;
    formError = "";
    try {
      const result = await (action === "read"
        ? getGenAIConsent()
        : action === "grant"
          ? grantGenAIConsent()
          : withdrawGenAIConsent());
      if (version === sessionVersion) {
        consent = result.genai_consent_at ? "granted" : "required";
        if (action === "withdraw") turns = [];
      }
    } catch (cause) {
      if (version === sessionVersion) {
        formError =
          cause instanceof ApiClientError
            ? cause.message
            : "Could not check AI consent.";
      }
    } finally {
      if (version === sessionVersion) consentBusy = false;
    }
  }

  function requestMessages(question: string): AssistantMessage[] {
    const messages: AssistantMessage[] = [{ role: "user", content: question }];
    let characters = question.length;
    for (const turn of turns.toReversed()) {
      if (!turn.complete || !turn.reply.trim()) continue;
      characters += turn.question.length + turn.reply.length;
      if (
        characters > historyCharacterLimit ||
        messages.length + 2 > historyMessageLimit
      )
        break;
      messages.unshift(
        { role: "user", content: turn.question },
        { role: "assistant", content: turn.reply },
      );
    }
    return messages;
  }

  async function send(event: SubmitEvent) {
    event.preventDefault();
    const question = draft.trim();
    if (!question || sending || consentBusy || consent !== "granted") return;
    const messages = requestMessages(question);
    const version = sessionVersion;
    const controller = new AbortController();
    generation = controller;
    sending = true;
    formError = "";
    draft = "";
    const turn = $state<Turn>({
      question,
      reply: "",
      tools: [],
      complete: false,
      issue: "",
    });
    turns.push(turn);
    try {
      const result = await streamAssistantReply(
        messages,
        (text) => {
          if (version === sessionVersion) turn.reply += text;
        },
        controller.signal,
      );
      if (version !== sessionVersion) return;
      turn.tools = result.tools;
      turn.complete = result.stop === "completed";
      if (result.stop === "timeout")
        turn.issue = "The assistant timed out. You can try again.";
      if (result.stop === "max_steps")
        turn.issue = "The assistant reached its tool-use limit.";
    } catch (cause) {
      if (version !== sessionVersion) return;
      const needsConsent =
        cause instanceof ApiClientError &&
        cause.code === "genai_consent_required";
      if (needsConsent) consent = "required";
      const message =
        cause instanceof ApiClientError
          ? cause.message
          : "Could not get a reply.";
      if (turn.reply) {
        turn.issue = message;
      } else {
        turns.pop();
        draft = question;
        if (!needsConsent) formError = message;
      }
    } finally {
      if (version === sessionVersion) {
        sending = false;
        generation = undefined;
      }
    }
  }
</script>

<svelte:head>
  <title>Learning assistant · English Learning</title>
  <meta
    name="description"
    content="Ask about your cards and what’s due for review."
  />
</svelte:head>

<section class="assistant-page">
  <h1>Learning assistant</h1>
  <p class="intro">Ask about your cards or what’s due for review.</p>
  <GenAIConsentPanel
    {consent}
    busy={consentBusy || sending}
    {updateConsent}
    onConfirmWithdraw={() => (consent = "confirm-withdraw")}
    onKeepConsent={() => (consent = "granted")}
    heading="Allow the learning assistant?"
    description="Your messages and relevant card information are sent to Google Vertex AI. You can withdraw consent here at any time."
    allowedMessage="AI consent is active."
    withdrawalMessage="Withdrawing consent deletes your existing embeddings and stops AI features. It cannot recall information already sent to Google Vertex AI."
  />

  {#if turns.length > 0}
    <ol class="conversation" aria-label="Conversation">
      {#each turns as turn (turn)}
        <li class="turn">
          <p class="question">
            <span class="speaker">You</span>{turn.question}
          </p>
          <div class="reply">
            <span class="speaker">Assistant</span>
            {#if turn.reply}<p>{turn.reply}</p>{/if}
            {#if sending && turn === turns.at(-1) && !turn.reply}
              <p>Waiting for a reply…</p>
            {/if}
            {#if turn.issue}<p class="error" role="alert">{turn.issue}</p>{/if}
            {#if turn.tools.length > 0}
              <details>
                <summary
                  >Tools used · {turn.tools.length}
                  {turn.tools.length === 1 ? "call" : "calls"}</summary
                >
                <ul>
                  {#each turn.tools as tool (tool)}
                    <li>
                      {Object.hasOwn(toolLabels, tool.name)
                        ? toolLabels[tool.name]
                        : "Unknown tool"}{tool.succeeded
                        ? ""
                        : " · Unsuccessful"}
                    </li>
                  {/each}
                </ul>
              </details>
            {/if}
          </div>
        </li>
      {/each}
    </ol>
  {/if}

  <form onsubmit={send} aria-busy={sending}>
    <label for="assistant-question">Ask the assistant</label>
    <div class="composer">
      <textarea
        id="assistant-question"
        bind:value={draft}
        maxlength={historyCharacterLimit}
        rows="2"
        placeholder="What should I review today?"
        readonly={sending}
      ></textarea>
      <button
        type="submit"
        disabled={!draft.trim() ||
          sending ||
          consentBusy ||
          consent !== "granted"}
      >
        Send <SendIcon size={18} aria-hidden="true" />
      </button>
    </div>
    {#if formError}<p class="error" role="alert">{formError}</p>{/if}
    <p class="hint">Refreshing the page clears this conversation.</p>
  </form>
  <p class="sr-only" role="status">
    {sending
      ? "The assistant is replying."
      : turns.at(-1)?.complete
        ? "Assistant reply ready."
        : ""}
  </p>
</section>

<style>
  .assistant-page {
    width: min(46rem, calc(100% - 2rem));
    margin: clamp(2.5rem, 8vh, 5rem) auto 4rem;
    color: #20394e;
  }
  h1 {
    margin: 0;
    font-family: "Bodoni Moda", Georgia, serif;
    font-size: clamp(2.25rem, 8vw, 4rem);
    font-weight: 600;
    line-height: 1;
  }
  .intro {
    margin: 0.8rem 0 0;
    color: #526b7f;
  }
  .conversation {
    display: grid;
    gap: 1.5rem;
    padding: 0;
    margin: 1.5rem 0 0;
    list-style: none;
  }
  .turn {
    display: grid;
    gap: 0.65rem;
    min-width: 0;
  }
  .question,
  .reply {
    min-width: 0;
    margin: 0;
    padding: 0.75rem 1rem;
    border: 1px solid #4075a633;
    border-radius: 0.9rem;
    overflow-wrap: anywhere;
  }
  .question {
    justify-self: end;
    max-width: 88%;
    background: #e3edf7;
    white-space: pre-wrap;
  }
  .reply {
    background: rgba(255, 255, 255, 0.65);
  }
  .speaker {
    display: block;
    color: #315f89;
    font:
      700 0.72rem "Fira Mono",
      monospace;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .reply p {
    margin: 0.35rem 0 0;
    white-space: pre-wrap;
  }
  details {
    margin-top: 0.65rem;
    color: #526b7f;
    font-size: 0.875rem;
  }
  summary {
    padding: 0.25rem 0;
    cursor: pointer;
  }
  details ul {
    margin: 0.25rem 0 0;
    padding-left: 1.25rem;
    list-style: disc;
  }
  form {
    margin-top: 1.5rem;
  }
  label {
    display: block;
    font-weight: 700;
    margin-bottom: 0.4rem;
  }
  .composer {
    display: flex;
    gap: 0.65rem;
    align-items: end;
  }
  textarea {
    flex: 1;
    min-width: 0;
    padding: 0.72rem 0.8rem;
    border: 1px solid #4075a666;
    border-radius: 0.55rem;
    background: rgba(255, 255, 255, 0.86);
    resize: vertical;
    font: inherit;
  }
  button {
    display: inline-flex;
    gap: 0.35rem;
    align-items: center;
    justify-content: center;
    min-height: 2.75rem;
    padding: 0.7rem 1rem;
    border: 1px solid #315f89;
    border-radius: 0.65rem;
    background: #315f89;
    color: white;
    font: inherit;
    font-weight: 700;
  }
  button:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }
  :is(textarea, button, summary):focus-visible {
    outline: 3px solid #4075a680;
    outline-offset: 2px;
  }
  .hint,
  .error {
    margin: 0.45rem 0 0;
    font-size: 0.875rem;
  }
  .hint {
    color: #526b7f;
  }
  .error {
    color: #a34646;
  }
  @media (max-width: 640px) {
    .composer {
      flex-direction: column;
      align-items: stretch;
    }
    .composer button {
      align-self: end;
    }
  }
</style>
