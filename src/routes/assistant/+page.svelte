<script lang="ts">
  import { onMount, tick, untrack } from "svelte";
  import AssistantCardProposal from "$lib/components/AssistantCardProposal.svelte";
  import {
    loadPendingAssistantProposals,
    type PendingAssistantProposal,
  } from "$lib/assistant/pending";
  import { shouldSendOnEnter } from "$lib/assistant/composer";
  import SendIcon from "@lucide/svelte/icons/arrow-up";
  import GenAIConsentPanel from "$lib/components/GenAIConsentPanel.svelte";
  import { authSession } from "$lib/stores/auth";
  import {
    ApiClientError,
    getGenAIConsent,
    grantGenAIConsent,
    streamAssistantReply,
    withdrawGenAIConsent,
    type AssistantTool,
    type AssistantPart,
  } from "$lib/api/client";

  import {
    historyCharacterLimit,
    requestMessages,
    type HistoryTurn,
    type ProposalState,
  } from "$lib/assistant/history";

  type Turn = HistoryTurn & {
    tools: AssistantTool[];
    issue: string;
    proposals: Extract<AssistantPart, { type: "card_proposal" }>["payload"][];
  };

  const toolLabels: Record<string, string> = {
    propose_cards: "Propose cards",
    ask_clarification: "Ask clarification",
    search_cards: "Search cards",
    get_due_cards: "Get due cards",
    get_review_stats: "Get review stats",
  };
  const toolStatusSuffix: Record<AssistantTool["status"], string> = {
    ok: "",
    invalid_call: " · Rejected",
    too_many_calls: " · Rejected",
    tool_unavailable: " · Unavailable",
    tools_disabled: " · Rejected",
    timeout: " · Timed out",
  };
  let turns = $state<Turn[]>([]);
  let draft = $state("");
  let consent = $state<"unknown" | "required" | "granted" | "confirm-withdraw">(
    "unknown",
  );
  let consentBusy = $state(false);
  let sending = $state(false);
  let formError = $state("");
  let consentError = $state("");
  let failedAction = $state<"read" | "grant" | "withdraw" | undefined>();
  let focusConsentHeading = $state(false);
  let restored = $state<PendingAssistantProposal[]>([]);
  let restoredStates = $state<ProposalState[]>([]);
  let composing = false;
  let messageList: HTMLDivElement;
  let textarea = $state<HTMLTextAreaElement>();
  let followBottom = true;
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
      consentError = "";
      failedAction = undefined;
      focusConsentHeading = false;
      restoredStates = [];
      restored =
        session.kind === "authenticated"
          ? loadPendingAssistantProposals(session.profile.sub ?? "")
          : [];
      restoredStates = restored.map((command) => ({
        type: "proposal_state",
        proposal_id: command.proposal_id,
        status: "pending",
        created_card_ids: [],
      }));
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
    consentError = "";
    failedAction = undefined;
    focusConsentHeading = false;
    try {
      const result = await (action === "read"
        ? getGenAIConsent()
        : action === "grant"
          ? grantGenAIConsent()
          : withdrawGenAIConsent());
      if (version === sessionVersion) {
        consent = result.genai_consent_at ? "granted" : "required";
        if (action === "withdraw") {
          turns = [];
          restored = [];
          restoredStates = [];
          focusConsentHeading = true;
        }
      }
    } catch (cause) {
      if (version === sessionVersion) {
        failedAction = action;
        consentError =
          cause instanceof ApiClientError
            ? cause.message
            : "Could not check AI consent.";
      }
    } finally {
      if (version === sessionVersion) consentBusy = false;
    }
  }

  function recordState(turn: Turn, state: Omit<ProposalState, "type">) {
    turn.proposalStates = [
      ...(turn.proposalStates ?? []).filter(
        (item) => item.proposal_id !== state.proposal_id,
      ),
      { type: "proposal_state", ...state },
    ];
  }

  function resizeInput() {
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  }
  $effect(() => {
    void draft;
    void tick().then(resizeInput);
  });
  $effect(() => {
    // Read text and proposal state so streaming follows only an already-following reader.
    turns.map((turn) => [turn.reply, turn.proposals.length]);
    void restored;
    if (followBottom)
      void tick().then(() => {
        if (messageList) messageList.scrollTop = messageList.scrollHeight;
      });
  });
  onMount(() => {
    const viewport = window.visualViewport;
    const root = document.documentElement;
    document.body.classList.add("assistant-route");
    root.classList.add("assistant-route");
    function fitViewport() {
      if (viewport)
        root.style.setProperty(
          "--assistant-viewport-height",
          `${viewport.height + viewport.offsetTop}px`,
        );
    }
    window.addEventListener("resize", fitViewport);
    viewport?.addEventListener("resize", fitViewport);
    viewport?.addEventListener("scroll", fitViewport);
    fitViewport();
    return () => {
      window.removeEventListener("resize", fitViewport);
      viewport?.removeEventListener("resize", fitViewport);
      viewport?.removeEventListener("scroll", fitViewport);
      root.style.removeProperty("--assistant-viewport-height");
      root.classList.remove("assistant-route");
      document.body.classList.remove("assistant-route");
    };
  });

  async function send(event?: SubmitEvent) {
    event?.preventDefault();
    const question = draft.trim();
    if (!question || sending || consentBusy || consent !== "granted") return;
    const restoreHistory: HistoryTurn[] = restoredStates.length
      ? [
          {
            question: "Recovered unfinished card proposal",
            reply: "Your unfinished card proposal.",
            complete: true,
            cardIds: [],
            proposalStates: restoredStates,
          },
        ]
      : [];
    const messages = requestMessages([...restoreHistory, ...turns], question);
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
      cardIds: [],
      complete: false,
      issue: "",
      proposals: [],
      proposalStates: [],
      clarificationQuestions: [],
    });
    turns.push(turn);
    try {
      const result = await streamAssistantReply(
        messages,
        (text) => {
          if (version === sessionVersion) turn.reply += text;
        },
        controller.signal,
        {
          capabilities: ["parts.v1"],
          onPart: (part) => {
            // TODO(#101): render and answer questions after the clarification UI design gate.
            if (
              version === sessionVersion &&
              part.type === "clarification_question"
            )
              turn.clarificationQuestions?.push(part.payload);
            if (version === sessionVersion && part.type === "card_list")
              turn.cardIds = [
                ...new Set([
                  ...turn.cardIds,
                  ...part.payload.items.map((item) => item.id),
                ]),
              ];
            if (
              version === sessionVersion &&
              part.type === "card_proposal" &&
              !turn.proposals.some(
                (proposal) => proposal.proposal_id === part.payload.proposal_id,
              )
            ) {
              turn.proposals.push(part.payload);
              turn.proposalStates?.push({
                type: "proposal_state",
                proposal_id: part.payload.proposal_id,
                status: "pending",
                created_card_ids: [],
              });
            }
          },
        },
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
      if (
        turn.reply ||
        turn.proposals.length ||
        turn.proposalStates?.length ||
        turn.clarificationQuestions?.length
      ) {
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
  <div class="heading-row">
    <div>
      <h1>Learning assistant</h1>
      <p class="intro">Ask about your cards or what’s due for review.</p>
    </div>
    <GenAIConsentPanel
      presentation="chip"
      {consent}
      busy={consentBusy || sending}
      {updateConsent}
      onConfirmWithdraw={() => (consent = "confirm-withdraw")}
      onKeepConsent={() => (consent = "granted")}
      allowedMessage="AI consent is active."
      inputIdPrefix="assistant-consent"
    />
  </div>
  <div
    class="message-list"
    bind:this={messageList}
    onscroll={() => {
      followBottom =
        messageList.scrollHeight -
          messageList.scrollTop -
          messageList.clientHeight <
        64;
    }}
  >
    {#each restored as command (`${command.ownerSubject}:${command.proposal_id}`)}
      <AssistantCardProposal
        proposal={{
          proposal_id: command.proposal_id,
          deck: command.deck,
          drafts: command.drafts,
          warnings: [],
        }}
        restored={command}
        onstate={(state) =>
          (restoredStates = [
            ...restoredStates.filter(
              (item) => item.proposal_id !== state.proposal_id,
            ),
            { type: "proposal_state", ...state },
          ])}
      />
    {/each}
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
              {#if turn.issue}<p class="error" role="alert">
                  {turn.issue}
                </p>{/if}
              {#each turn.proposals as proposal (proposal.proposal_id)}
                <AssistantCardProposal
                  {proposal}
                  onstate={(state) => recordState(turn, state)}
                />
              {/each}
              {#if turn.tools.length > 0}
                <details>
                  <summary>Tool call attempts · {turn.tools.length}</summary>
                  <ul>
                    {#each turn.tools as tool (tool)}
                      <li>
                        {Object.hasOwn(toolLabels, tool.name)
                          ? toolLabels[tool.name]
                          : "Unknown tool"}{toolStatusSuffix[tool.status]}
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
  </div>
  <div class="bottom-row">
    <GenAIConsentPanel
      presentation="panel"
      {consent}
      busy={consentBusy || sending}
      {updateConsent}
      error={consentError}
      {failedAction}
      focusHeading={focusConsentHeading}
      inputIdPrefix="assistant-consent"
      onConfirmWithdraw={() => (consent = "confirm-withdraw")}
      onKeepConsent={() => (consent = "granted")}
      heading="Allow the learning assistant?"
      description="Your messages and relevant card information are sent to Google Vertex AI. You can withdraw consent here at any time."
      allowedMessage="AI consent is active."
      withdrawalMessage="Withdrawing consent deletes your existing embeddings and stops AI features. It cannot recall information already sent to Google Vertex AI."
    />
    {#if consent === "granted" || consent === "confirm-withdraw"}
      <form onsubmit={send} aria-busy={sending}>
        <label for="assistant-question">Ask the assistant</label>
        <div class="composer">
          <textarea
            id="assistant-question"
            bind:this={textarea}
            bind:value={draft}
            maxlength={historyCharacterLimit}
            rows="1"
            placeholder="What should I review today?"
            readonly={sending || consentBusy || consent !== "granted"}
            aria-describedby="assistant-keyboard assistant-input-reason"
            oncompositionstart={() => (composing = true)}
            oncompositionend={() => (composing = false)}
            onkeydown={(event) => {
              if (shouldSendOnEnter(event, composing)) {
                event.preventDefault();
                void send();
              }
            }}
          ></textarea>
          <button
            type="submit"
            aria-label={sending ? "Replying…" : "Send message"}
            disabled={!draft.trim() ||
              sending ||
              consentBusy ||
              consent !== "granted"}
          >
            <SendIcon size={22} aria-hidden="true" />
          </button>
        </div>
        {#if formError}<p class="error" role="alert">{formError}</p>{/if}
        <p class="hint" id="assistant-keyboard">
          Enter to send · Shift+Enter for newline · IME Enter confirms text
        </p>
        <p class="hint" id="assistant-input-reason">
          {sending
            ? "Replying…"
            : consentBusy || consent !== "granted"
              ? "Sending is unavailable until consent is active and no consent action is pending."
              : !draft.trim()
                ? "Type a message to enable Send."
                : "Ready to send."}
        </p>
      </form>
    {/if}
    <p class="hint">Refreshing the page clears this conversation.</p>
    {#if restored.length}<p class="hint">
        Your unfinished commit is restored. Retry when you are ready.
      </p>{/if}
  </div>
  <p class="sr-only" role="status">
    {sending
      ? "The assistant is replying."
      : turns.at(-1)?.complete
        ? "Assistant reply ready."
        : ""}
  </p>
</section>

<style>
  :global(html.assistant-route),
  :global(body.assistant-route) {
    overflow: hidden;
    height: 100%;
    min-height: 0;
  }
  :global(body.assistant-route .app) {
    height: var(--assistant-viewport-height, 100dvh);
    max-height: var(--assistant-viewport-height, 100dvh);
    min-height: 0;
    overflow: hidden;
  }
  :global(body.assistant-route main) {
    min-height: 0;
    overflow: hidden;
  }
  .assistant-page {
    width: min(46rem, calc(100% - 2rem));
    margin: 1.5rem auto 0;
    height: auto;
    flex: 1;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    min-height: 0;
    box-sizing: border-box;
    padding-bottom: max(0.5rem, env(safe-area-inset-bottom));
    color: #20394e;
  }
  .heading-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    flex-shrink: 0;
    padding-bottom: 1rem;
  }
  .message-list {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior: contain;
  }
  .bottom-row {
    flex-shrink: 0;
    padding: 0 0.5rem;
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
    padding: 0 0 1rem;
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
    margin-top: 0.5rem;
  }
  label {
    display: block;
    font-weight: 700;
    margin-bottom: 0.4rem;
  }
  .composer {
    position: relative;
    border: 1px solid #4075a666;
    border-radius: 0.9rem;
    background: rgba(255, 255, 255, 0.75);
    box-shadow: 0 6px 20px rgba(47, 78, 105, 0.08);
    padding: 0.5rem;
  }
  textarea {
    display: block;
    width: 100%;
    box-sizing: border-box;
    min-height: 2.75rem;
    max-height: min(9rem, 30dvh);
    overflow-y: auto;
    padding: 0.65rem 3.6rem 0.65rem 0.35rem;
    border: 0;
    border-radius: 0.55rem;
    background: transparent;
    resize: none;
    font: inherit;
    line-height: 1.5;
  }
  .composer button {
    position: absolute;
    right: 0.5rem;
    bottom: 0.5rem;
    width: 2.75rem;
    height: 2.75rem;
    display: inline-flex;
    gap: 0.35rem;
    align-items: center;
    justify-content: center;
    min-height: 2.75rem;
    padding: 0.5rem;
    border: 1px solid #315f89;
    border-radius: 50%;
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
  .assistant-page :global(.assistant-proposal) {
    margin-top: 1rem;
  }
  .assistant-page :global(.proposal-rows) {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .assistant-page :global(.proposal-meaning) {
    display: block;
    color: #60788c;
  }
  .assistant-page :global(.proposal-row-actions) {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
  }
  .assistant-page :global(.proposal-row) {
    border-bottom: 1px solid #4075a633;
    padding: 0.8rem 0;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.6rem;
  }
  .assistant-page :global(.proposal-row label) {
    flex: 1;
    min-width: 10rem;
    display: flex;
    gap: 0.6rem;
    align-items: start;
  }
  .assistant-page :global(.proposal-row input) {
    margin-top: 0.3rem;
    accent-color: #4075a6;
  }
  .assistant-page :global(.proposal-row small) {
    display: block;
    color: #60788c;
  }
  .assistant-page :global(.proposal-actions) {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 0.8rem;
  }
  .assistant-page :global(.assistant-proposal button),
  .assistant-page :global(.assistant-proposal a) {
    font: inherit;
  }
  .assistant-page :global(.assistant-proposal button) {
    min-height: 2.75rem;
    border: 1px solid #4075a655;
    border-radius: 0.65rem;
    padding: 0.5rem 0.8rem;
    background: #ffffffb8;
    color: #315f89;
    font-weight: 700;
  }
  .assistant-page :global(.assistant-proposal button:disabled) {
    opacity: 0.55;
    cursor: not-allowed;
  }
  .assistant-page :global(.assistant-proposal .proposal-confirm) {
    background: #ff3e00;
    border-color: #ff3e00;
    color: white;
  }
  .assistant-page :global(.assistant-proposal .proposal-danger),
  .assistant-page :global(.proposal-error) {
    color: #a34646;
  }
  .assistant-page :global(.proposal-warning) {
    display: inline-flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.35rem;
    color: #89502b;
    border: 1px solid #b46b3980;
    border-radius: 999px;
    padding: 0.1rem 0.4rem;
    font-size: 0.8rem;
  }
  .assistant-page :global(.assistant-proposal a) {
    color: #315f89;
    text-decoration: underline;
  }
  .assistant-page :global(.assistant-proposal h2),
  .assistant-page :global(.assistant-proposal h3) {
    font-family: Arial, sans-serif;
    font-size: 1.08rem;
    font-weight: 700;
  }
  .assistant-page
    :global(.assistant-proposal :is(button, a, input):focus-visible) {
    outline: 3px solid #4075a680;
    outline-offset: 2px;
  }
  @media (max-height: 600px) {
    .assistant-page {
      margin-top: 0.5rem;
    }
    .heading-row {
      gap: 0.35rem;
      padding-bottom: 0.5rem;
    }
    h1 {
      font-size: 1.75rem;
    }
    .intro {
      margin-top: 0.25rem;
      font-size: 0.875rem;
    }
    .hint {
      margin-top: 0.25rem;
      font-size: 0.75rem;
    }
  }
  @media (max-width: 640px) {
    .assistant-page :global(.proposal-confirm) {
      width: 100%;
    }
  }
</style>
