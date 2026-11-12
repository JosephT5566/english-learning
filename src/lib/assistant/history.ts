import type { AssistantMessage } from "$lib/api/client";

export type HistoryTurn = {
  question: string;
  reply: string;
  complete: boolean;
  cardIds: string[];
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
  for (const turn of turns.toReversed()) {
    if (!turn.complete || !turn.reply.trim()) continue;
    const cardIds = [...new Set(turn.cardIds)].slice(0, historyCardRefLimit);
    const assistant: AssistantMessage = {
      role: "assistant",
      content: turn.reply,
    };
    if (cardIds.length)
      assistant.parts = [{ type: "card_refs", card_ids: cardIds }];
    characters +=
      turn.question.length +
      turn.reply.length +
      (assistant.parts ? JSON.stringify(assistant.parts).length : 0);
    if (
      characters > historyCharacterLimit ||
      messages.length + 2 > historyMessageLimit ||
      refs + cardIds.length > historyCardRefLimit
    )
      break;
    refs += cardIds.length;
    messages.unshift({ role: "user", content: turn.question }, assistant);
  }
  return messages;
}
