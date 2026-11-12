import { describe, expect, it, vi } from "vitest";
import {
  PENDING_ASSISTANT_STORAGE_KEY,
  PENDING_ASSISTANT_TTL_MS,
  createPendingAssistantProposal,
  loadPendingAssistantProposal,
  savePendingAssistantProposal,
  clearPendingAssistantProposal,
} from "../../src/lib/assistant/pending";

const id = "10000000-0000-4000-8000-000000000001";
const other = "10000000-0000-4000-8000-000000000002";
const deck = { id, title: "Travel English", target_language: "en" as const };
function storage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
    removeItem: (key: string) => {
      values.delete(key);
    },
  };
}
function pending() {
  return createPendingAssistantProposal(
    {
      ownerSubject: "owner-a",
      proposal_id: id,
      deck,
      drafts: [
        {
          term: "wander",
          meaning: "walk without a destination",
          synonyms: [],
          antonyms: [],
        },
      ],
      idempotencyKeys: [other],
    },
    1000,
  );
}

describe("pending assistant proposal", () => {
  it("restores the exact command and caller-minted keys for its owner within 24 hours", () => {
    const store = storage();
    const command = pending();
    savePendingAssistantProposal(command, store);
    expect(PENDING_ASSISTANT_STORAGE_KEY).toBe("pending_assistant_proposal_v1");
    expect(PENDING_ASSISTANT_TTL_MS).toBe(24 * 60 * 60 * 1000);
    expect(loadPendingAssistantProposal("owner-a", 1001, store)).toEqual(
      command,
    );
  });
  it("does not load or delete another account command", () => {
    const store = storage();
    savePendingAssistantProposal(pending(), store);
    expect(loadPendingAssistantProposal("owner-b", 1001, store)).toBeNull();
    clearPendingAssistantProposal("owner-b", id, store);
    expect(loadPendingAssistantProposal("owner-a", 1001, store)).toEqual(
      pending(),
    );
  });
  it("removes expired and malformed commands, including mismatched keys and invalid draft fields", () => {
    const store = storage();
    savePendingAssistantProposal(pending(), store);
    expect(
      loadPendingAssistantProposal(
        "owner-a",
        1000 + PENDING_ASSISTANT_TTL_MS,
        store,
      ),
    ).toBeNull();
    expect(store.getItem(PENDING_ASSISTANT_STORAGE_KEY)).toBeNull();
    for (const value of [
      "bad json",
      JSON.stringify({ ...pending(), idempotencyKeys: [] }),
      JSON.stringify({
        ...pending(),
        drafts: [{ term: "wander", meaning: 3 }],
      }),
      JSON.stringify({ ...pending(), idempotencyKeys: ["not-a-uuid"] }),
    ]) {
      store.setItem(PENDING_ASSISTANT_STORAGE_KEY, value);
      expect(loadPendingAssistantProposal("owner-a", 1001, store)).toBeNull();
      expect(store.getItem(PENDING_ASSISTANT_STORAGE_KEY)).toBeNull();
    }
  });
  it("returns null when browser storage access itself is denied without touching account data", () => {
    const store = storage();
    savePendingAssistantProposal(pending(), store);
    const original = Object.getOwnPropertyDescriptor(
      globalThis,
      "localStorage",
    );
    const getter = vi.fn(() => {
      throw new DOMException("Blocked", "SecurityError");
    });
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      get: getter,
    });
    try {
      expect(loadPendingAssistantProposal("owner-a", 1001)).toBeNull();
      expect(getter).toHaveBeenCalledTimes(1);
      expect(loadPendingAssistantProposal("owner-a", 1001, store)).toEqual(
        pending(),
      );
    } finally {
      if (original) Object.defineProperty(globalThis, "localStorage", original);
      else Reflect.deleteProperty(globalThis, "localStorage");
    }
  });
  it("restores UUIDs accepted by the incoming proposal parser, including nil and version-zero ids", () => {
    const store = storage();
    const command = {
      ...pending(),
      proposal_id: "00000000-0000-0000-0000-000000000000",
      deck: { ...deck, id: "10000000-0000-0000-0000-000000000001" },
    };
    savePendingAssistantProposal(command, store);
    expect(loadPendingAssistantProposal("owner-a", 1001, store)).toEqual(
      command,
    );
  });
  it("propagates a storage failure so the UI cannot claim it was saved", () => {
    const store = storage();
    store.setItem = () => {
      throw new Error("quota");
    };
    expect(() => savePendingAssistantProposal(pending(), store)).toThrow(
      "quota",
    );
  });
});
