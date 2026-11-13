import type { AssistantMessage, ClarificationQuestion } from "$lib/api/client";

export type ProposalState = {
  type: "proposal_state";
  proposal_id: string;
  status: "pending" | "committed" | "dismissed";
  created_card_ids: string[];
};

export type ClarificationAnswer = {
  type: "clarification_answer";
  question_id: string;
  option_id?: string;
  text?: string;
  deck_id?: string;
};

export function makeClarificationAnswer(
  question: ClarificationQuestion,
  choice: { optionId?: string; text?: string },
): ClarificationAnswer {
  const option =
    choice.optionId === undefined
      ? undefined
      : question.options.find((item) => item.id === choice.optionId);
  const text = choice.text?.trim();
  if (
    (choice.optionId !== undefined && !option) ||
    (text && !question.allow_free_text) ||
    (!option && !text)
  )
    throw new Error("Choose an available option or provide an allowed answer.");
  return {
    type: "clarification_answer",
    question_id: question.question_id,
    ...(option ? { option_id: option.id } : {}),
    ...(text ? { text } : {}),
    ...(option?.deck_id ? { deck_id: option.deck_id } : {}),
  };
}

export type HistoryTurn = {
  question: string;
  reply: string;
  complete: boolean;
  cardIds: string[];
  proposalStates?: ProposalState[];
  clarificationQuestions?: ClarificationQuestion[];
  clarificationAnswer?: ClarificationAnswer;
};

// Match API defaults while keeping the full transcript visible locally.
export const historyCharacterLimit = 12000;
const historyMessageLimit = 20;
const historyCardRefLimit = 40;

export function requestMessages(
  turns: HistoryTurn[],
  question: string,
  answer?: ClarificationAnswer,
): AssistantMessage[] {
  const current: AssistantMessage = {
    role: "user",
    content: question,
    ...(answer ? { parts: [answer] } : {}),
  };
  const messages: AssistantMessage[] = [current];
  let characters =
    question.length +
    (current.parts ? JSON.stringify(current.parts).length : 0);
  if (characters > historyCharacterLimit)
    throw new Error("The message exceeds the history character limit.");
  let refs = 0;
  const seenProposals = new Set<string>();
  for (const turn of turns.toReversed()) {
    if (
      (!turn.complete || !turn.reply.trim()) &&
      !turn.proposalStates?.length &&
      !turn.clarificationQuestions?.length &&
      !turn.clarificationAnswer
    )
      continue;
    const content = turn.reply.trim()
      ? turn.reply
      : "The reply was interrupted.";
    const cardIds = [...new Set(turn.cardIds)].slice(0, historyCardRefLimit);
    const assistant: AssistantMessage = {
      role: "assistant",
      content,
    };
    const states: ProposalState[] = [];
    for (const state of (turn.proposalStates ?? []).toReversed()) {
      if (seenProposals.has(state.proposal_id)) continue;
      seenProposals.add(state.proposal_id);
      states.unshift(state);
    }
    const parts: NonNullable<AssistantMessage["parts"]> = [];
    if (cardIds.length) parts.push({ type: "card_refs", card_ids: cardIds });
    parts.push(...states);
    parts.push(
      ...(turn.clarificationQuestions ?? []).map((item) => ({
        type: "clarification_question" as const,
        ...item,
        purpose: item.purpose ?? "term",
      })),
    );
    if (parts.length) assistant.parts = parts;
    const turnRefs =
      cardIds.length +
      states.reduce((sum, state) => sum + state.created_card_ids.length, 0);
    const user: AssistantMessage = {
      role: "user",
      content: turn.question,
      ...(turn.clarificationAnswer
        ? { parts: [turn.clarificationAnswer] }
        : {}),
    };
    characters +=
      turn.question.length +
      (user.parts ? JSON.stringify(user.parts).length : 0) +
      content.length +
      (assistant.parts ? JSON.stringify(assistant.parts).length : 0);
    if (
      characters > historyCharacterLimit ||
      messages.length + 2 > historyMessageLimit ||
      refs + turnRefs > historyCardRefLimit
    )
      break;
    refs += turnRefs;
    messages.unshift(user, assistant);
  }
  return messages;
}

export function clarificationAnswerFor(
  turns: HistoryTurn[],
  question: ClarificationQuestion,
): ClarificationAnswer | undefined {
  return turns.find(
    (turn) => turn.clarificationAnswer?.question_id === question.question_id,
  )?.clarificationAnswer;
}

export function latestUnansweredClarification(
  turns: HistoryTurn[],
): ClarificationQuestion | undefined {
  return turns
    .flatMap((turn) => turn.clarificationQuestions ?? [])
    .findLast((question) => !clarificationAnswerFor(turns, question));
}
