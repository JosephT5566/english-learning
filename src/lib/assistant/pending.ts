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
type PendingStorage = Pick<
  Storage,
  "getItem" | "setItem" | "removeItem" | "key" | "length"
>;
const slotPrefix = "pending_assistant_proposal_v2:";
function slotKey(ownerSubject: string, proposalId: string): string {
  return `${slotPrefix}${encodeURIComponent(ownerSubject)}:${proposalId}`;
}
function sameCommand(
  a: PendingAssistantProposal,
  b: PendingAssistantProposal,
): boolean {
  return (
    JSON.stringify([a.deck, a.drafts, a.idempotencyKeys]) ===
    JSON.stringify([b.deck, b.drafts, b.idempotencyKeys])
  );
}
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
  const key = slotKey(pending.ownerSubject, pending.proposal_id);
  const raw = storage.getItem(key);
  if (raw) {
    const existing: unknown = JSON.parse(raw);
    if (
      !isPending(existing) ||
      existing.ownerSubject !== pending.ownerSubject ||
      existing.proposal_id !== pending.proposal_id ||
      !sameCommand(existing, pending)
    )
      throw new Error(
        "An unresolved command already occupies this proposal slot.",
      );
  }
  // Keep legacy data in place until this exact command is confirmed or dismissed.
  const legacyRaw = storage.getItem(PENDING_ASSISTANT_STORAGE_KEY);
  if (legacyRaw) {
    let legacy: unknown;
    try {
      legacy = JSON.parse(legacyRaw);
    } catch {
      /* An unrelated malformed legacy slot is left untouched. */
    }
    if (
      isPending(legacy) &&
      legacy.ownerSubject === pending.ownerSubject &&
      legacy.proposal_id === pending.proposal_id &&
      !sameCommand(legacy, pending)
    )
      throw new Error(
        "An unresolved legacy command already occupies this proposal slot.",
      );
  }
  storage.setItem(key, JSON.stringify(pending));
}

function readPending(
  storage: PendingStorage,
  key: string,
  ownerSubject: string,
  now: number,
): PendingAssistantProposal | null {
  const raw = storage.getItem(key);
  if (!raw) return null;
  let pending: unknown;
  try {
    pending = JSON.parse(raw);
  } catch {
    /* Removed below, only from this slot. */
  }
  if (!isPending(pending)) {
    storage.removeItem(key);
    return null;
  }
  if (pending.ownerSubject !== ownerSubject) return null;
  if (
    pending.expiresAt <= now ||
    (key !== PENDING_ASSISTANT_STORAGE_KEY &&
      key !== slotKey(ownerSubject, pending.proposal_id))
  ) {
    storage.removeItem(key);
    return null;
  }
  return pending;
}

export function loadPendingAssistantProposals(
  ownerSubject: string,
  now = Date.now(),
  storage?: PendingStorage,
): PendingAssistantProposal[] {
  try {
    storage ??= localStorage;
    const keys = [PENDING_ASSISTANT_STORAGE_KEY];
    const ownerPrefix = `${slotPrefix}${encodeURIComponent(ownerSubject)}:`;
    for (let index = 0; index < storage.length; index++) {
      const key = storage.key(index);
      if (key?.startsWith(ownerPrefix)) keys.push(key);
    }
    const commands = new Map<string, PendingAssistantProposal>();
    for (const key of keys) {
      const pending = readPending(storage, key, ownerSubject, now);
      if (pending) commands.set(pending.proposal_id, pending);
    }
    return [...commands.values()];
  } catch {
    return [];
  }
}

export function loadPendingAssistantProposal(
  ownerSubject: string,
  now = Date.now(),
  storage?: PendingStorage,
): PendingAssistantProposal | null {
  return loadPendingAssistantProposals(ownerSubject, now, storage)[0] ?? null;
}

export function clearPendingAssistantProposal(
  ownerSubject: string,
  proposalId: string,
  storage: PendingStorage = localStorage,
): void {
  storage.removeItem(slotKey(ownerSubject, proposalId));
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
