import {
  isCardDraft,
  JSON_CARD_LIMIT,
  type CardDraft,
} from "$lib/management/json-cards";
import type { AssistantPart } from "$lib/api/client";

export type CardProposalPayload = Extract<
  AssistantPart,
  { type: "card_proposal" }
>["payload"];
export const PENDING_ASSISTANT_STORAGE_KEY = "pending_assistant_proposal_v1";
export const PENDING_ASSISTANT_TTL_MS = 24 * 60 * 60 * 1000;
type PendingCommand = {
  ownerSubject: string;
  proposal_id: string;
  deck: CardProposalPayload["deck"];
  drafts: CardDraft[];
  idempotencyKeys: string[];
};
export type PendingAssistantProposal = PendingCommand & {
  version: 1;
  createdAt: number;
  expiresAt: number;
};
type PendingStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;
function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function uuid(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      value,
    )
  );
}
function isPending(value: unknown): value is PendingAssistantProposal {
  return (
    record(value) &&
    value.version === 1 &&
    typeof value.ownerSubject === "string" &&
    uuid(value.proposal_id) &&
    record(value.deck) &&
    uuid(value.deck.id) &&
    typeof value.deck.title === "string" &&
    (value.deck.target_language === "en" ||
      value.deck.target_language === "ja") &&
    Array.isArray(value.drafts) &&
    value.drafts.length >= 1 &&
    value.drafts.length <= JSON_CARD_LIMIT &&
    value.drafts.every(isCardDraft) &&
    Array.isArray(value.idempotencyKeys) &&
    value.idempotencyKeys.length === value.drafts.length &&
    value.idempotencyKeys.every(uuid) &&
    new Set(value.idempotencyKeys).size === value.idempotencyKeys.length &&
    typeof value.createdAt === "number" &&
    Number.isFinite(value.createdAt) &&
    typeof value.expiresAt === "number" &&
    value.expiresAt === value.createdAt + PENDING_ASSISTANT_TTL_MS
  );
}
export function createPendingAssistantProposal(
  command: PendingCommand,
  now = Date.now(),
): PendingAssistantProposal {
  return {
    ...command,
    deck: { ...command.deck },
    drafts: command.drafts.map((fields) => ({
      ...fields,
      synonyms: [...fields.synonyms],
      antonyms: [...fields.antonyms],
    })),
    idempotencyKeys: [...command.idempotencyKeys],
    version: 1,
    createdAt: now,
    expiresAt: now + PENDING_ASSISTANT_TTL_MS,
  };
}
export function savePendingAssistantProposal(
  pending: PendingAssistantProposal,
  storage: PendingStorage = localStorage,
): void {
  storage.setItem(PENDING_ASSISTANT_STORAGE_KEY, JSON.stringify(pending));
}
export function loadPendingAssistantProposal(
  ownerSubject: string,
  now = Date.now(),
  storage?: PendingStorage,
): PendingAssistantProposal | null {
  try {
    storage ??= localStorage;
    const raw = storage.getItem(PENDING_ASSISTANT_STORAGE_KEY);
    if (!raw) return null;
    const pending: unknown = JSON.parse(raw);
    if (!isPending(pending)) {
      storage.removeItem(PENDING_ASSISTANT_STORAGE_KEY);
      return null;
    }
    // A second signed-in account must not erase the first account's unfinished command.
    if (pending.ownerSubject !== ownerSubject) return null;
    if (pending.expiresAt <= now) {
      storage.removeItem(PENDING_ASSISTANT_STORAGE_KEY);
      return null;
    }
    return pending;
  } catch {
    try {
      storage?.removeItem(PENDING_ASSISTANT_STORAGE_KEY);
    } catch {
      /* Storage may be unavailable. */
    }
    return null;
  }
}
export function clearPendingAssistantProposal(
  ownerSubject: string,
  proposalId: string,
  storage: PendingStorage = localStorage,
): void {
  const raw = storage.getItem(PENDING_ASSISTANT_STORAGE_KEY);
  if (!raw) return;
  const pending: unknown = JSON.parse(raw);
  if (
    isPending(pending) &&
    pending.ownerSubject === ownerSubject &&
    pending.proposal_id === proposalId
  )
    storage.removeItem(PENDING_ASSISTANT_STORAGE_KEY);
}
