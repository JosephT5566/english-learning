import type { AssistantMessage } from "$lib/api/client";

export type ProposalState = {
  type: "proposal_state";
  proposal_id: string;
  status: "pending" | "committed" | "dismissed";
  created_card_ids: string[];
};

export type HistoryTurn = {
  question: string;
  reply: string;
  complete: boolean;
  cardIds: string[];
  proposalStates?: ProposalState[];
};

// Match API defaults while keeping the full transcript visible locally.
export const historyCharacterLimit = 12000;
const historyMessageLimit = 20;
const historyCardRefLimit = 40;

export function requestMessages(
  turns: HistoryTurn[],
  question: string,
): AssistantMessage[] {
  const messages: AssistantMessage[] = [{ role: "user", content: question }];
  let characters = question.length;
  let refs = 0;
  const seenProposals = new Set<string>();
  for (const turn of turns.toReversed()) {
    if (!turn.complete || !turn.reply.trim()) continue;
    const cardIds = [...new Set(turn.cardIds)].slice(0, historyCardRefLimit);
    const assistant: AssistantMessage = {
      role: "assistant",
      content: turn.reply,
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
    if (parts.length) assistant.parts = parts;
    const turnRefs =
      cardIds.length +
      states.reduce((sum, state) => sum + state.created_card_ids.length, 0);
    characters +=
      turn.question.length +
      turn.reply.length +
      (assistant.parts ? JSON.stringify(assistant.parts).length : 0);
    if (
      characters > historyCharacterLimit ||
      messages.length + 2 > historyMessageLimit ||
      refs + turnRefs > historyCardRefLimit
    )
      break;
    refs += turnRefs;
    messages.unshift({ role: "user", content: turn.question }, assistant);
  }
  return messages;
}
