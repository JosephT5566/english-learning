import { describe, expect, it } from "vitest";
import { requestMessages, type HistoryTurn } from "$lib/assistant/history";

const ids = Array.from(
  { length: 50 },
  (_, i) => `00000000-0000-0000-0000-${String(i + 1).padStart(12, "0")}`,
);
const turn = (changes: Partial<HistoryTurn> = {}): HistoryTurn => ({
  question: "find cards",
  reply: "Here are cards.",
  complete: true,
  cardIds: [],
  ...changes,
});
const parts = (card_ids: string[]) => [{ type: "card_refs", card_ids }];

describe("assistant history", () => {
  it("deduplicates emitted ids in order on their own completed turn", () => {
    const result = requestMessages(
      [turn({ cardIds: [ids[2], ids[0], ids[2], ids[1]] })],
      "those three",
    );
    expect(result).toEqual([
      { role: "user", content: "find cards" },
      {
        role: "assistant",
        content: "Here are cards.",
        parts: parts([ids[2], ids[0], ids[1]]),
      },
      { role: "user", content: "those three" },
    ]);
  });

  it("omits incomplete turns and adds no parts without ids, preserving the old golden history", () => {
    expect(
      requestMessages(
        [
          turn(),
          turn({ complete: false, cardIds: ids }),
          turn({ reply: "  " }),
        ],
        "follow up",
      ),
    ).toEqual([
      { role: "user", content: "find cards" },
      { role: "assistant", content: "Here are cards." },
      { role: "user", content: "follow up" },
    ]);
  });

  it("drops oldest whole turns for message count", () => {
    const turns = Array.from({ length: 12 }, (_, i) =>
      turn({ question: String(i) }),
    );
    const result = requestMessages(turns, "next");
    expect(result).toHaveLength(19);
    expect(result[0].content).toBe("3");
    expect(result.at(-1)?.content).toBe("next");
  });

  it("counts serialized parts toward characters and drops oldest turns", () => {
    const older = turn({ question: "x".repeat(11750) });
    const newer = turn({ cardIds: ids.slice(0, 10) });
    expect(requestMessages([older, newer], "next")).toEqual(
      requestMessages([newer], "next"),
    );
    expect(
      requestMessages([turn({ ...older, cardIds: ids.slice(0, 10) })], "next"),
    ).toEqual([{ role: "user", content: "next" }]);
  });

  it("drops whole older turns when total refs exceed 40", () => {
    const newer = turn({ question: "newer", cardIds: ids.slice(0, 25) });
    expect(
      requestMessages([turn({ cardIds: ids.slice(0, 20) }), newer], "next"),
    ).toEqual(requestMessages([newer], "next"));
    expect(requestMessages([newer], "next")[1].parts).toEqual(
      parts(ids.slice(0, 25)),
    );
  });

  it("keeps the first 40 ids of an oversized kept turn", () => {
    expect(requestMessages([turn({ cardIds: ids })], "next")[1].parts).toEqual(
      parts(ids.slice(0, 40)),
    );
  });
});
