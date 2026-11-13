import { afterEach, expect, it, vi } from "vitest";
import { streamAssistantReply } from "$lib/api/client";

vi.mock("$env/dynamic/public", () => ({
  env: { PUBLIC_API_BASE_URL: "https://api.example.test" },
}));
vi.mock("$lib/auth", () => ({
  getTokenIfValid: () => "test-token",
  signOut: vi.fn(),
}));
afterEach(() => vi.unstubAllGlobals());

const delta = (text: string) =>
  `event: delta\ndata: ${JSON.stringify({ text })}\n\n`;
const done = `event: done\ndata: ${JSON.stringify({ stop_reason: "completed", tool_calls: [{ name: "get_due_cards", status: "ok" }], usage: null })}\n\n`;

async function read(
  chunks: string[],
  options?: Parameters<typeof streamAssistantReply>[3],
) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        new ReadableStream({
          start(controller) {
            for (const chunk of chunks)
              controller.enqueue(new TextEncoder().encode(chunk));
            controller.close();
          },
        }),
        { headers: { "Content-Type": "text/event-stream" } },
      ),
    ),
  );
  let text = "";
  const result = await streamAssistantReply(
    [{ role: "user", content: "hello" }],
    (chunk) => {
      text += chunk;
    },
    new AbortController().signal,
    options,
  );
  return { text, ...result };
}

it.each(["comments", "split", "crlf"])(
  "ignores %s while preserving text and tools",
  async (variant) => {
    const baseline = await read([delta("first"), delta(" second"), done]);
    const body =
      ": ping\n\n" +
      delta("first") +
      ": ping\n\n" +
      delta(" second") +
      ": ping\n\n" +
      done;
    const chunks =
      variant === "split"
        ? [body.slice(0, 3), body.slice(3, 7), body.slice(7)]
        : [variant === "crlf" ? body.replaceAll("\n", "\r\n") : body];
    expect(await read(chunks)).toEqual(baseline);
    expect(baseline).toEqual({
      text: "first second",
      stop: "completed",
      tools: [{ name: "get_due_cards", status: "ok" }],
    });
  },
);

it("rejects comment-only EOF as invalid_response", async () => {
  await expect(
    read([": pi", "ng\n\n", ": ping\r\n\r\n"]),
  ).rejects.toMatchObject({ kind: "invalid_response" });
});

it("ignores unknown event names between deltas", async () => {
  const baseline = await read([delta("first"), delta(" second"), done]);
  expect(
    await read([
      delta("first"),
      "event: future\ndata: {}\n\n",
      delta(" second"),
      done,
    ]),
  ).toEqual(baseline);
});

const cardPart = {
  id: "p1",
  type: "card_list",
  payload: {
    purpose: "due",
    items: [{ id: "card", deck_id: "deck", term: "harbor", meaning: "port" }],
  },
};
const partFrame = (part: unknown) =>
  `event: part\ndata: ${JSON.stringify(part)}\n\n`;

const proposalPart = {
  id: "p2",
  type: "card_proposal",
  payload: {
    proposal_id: "30000000-0000-0000-0000-000000000097",
    deck: {
      id: "10000000-0000-0000-0000-000000000097",
      title: "English",
      target_language: "en",
    },
    drafts: [{ term: "harbor", meaning: "port", synonyms: [], antonyms: [] }],
    warnings: [
      {
        code: "duplicate_term",
        term: "harbor",
        draft_index: 0,
        existing_card_ids: ["20000000-0000-0000-0000-000000000097"],
      },
    ],
  },
};

async function readPart(
  part: unknown,
  options: Parameters<typeof streamAssistantReply>[3] = {},
) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(partFrame(part) + delta("answer") + done, {
        headers: { "Content-Type": "text/event-stream" },
      }),
    ),
  );
  return streamAssistantReply(
    [{ role: "user", content: "hello" }],
    () => {},
    new AbortController().signal,
    options,
  );
}

it("delivers a strictly allow-listed card_list to onPart", async () => {
  const onPart = vi.fn();
  await readPart(cardPart, { capabilities: ["parts.v1"], onPart });
  expect(onPart.mock.calls).toEqual([[cardPart]]);
});

it("delivers a strictly allow-listed card_proposal without disturbing text or tools", async () => {
  const onPart = vi.fn();
  const result = await read(
    [
      ": ping\n\n",
      partFrame(cardPart),
      partFrame(proposalPart),
      ": ping\n\n",
      delta("A draft is ready."),
      done,
    ],
    { capabilities: ["parts.v1"], onPart },
  );
  expect(onPart.mock.calls).toEqual([[cardPart], [proposalPart]]);
  expect(result).toEqual({
    text: "A draft is ready.",
    stop: "completed",
    tools: [{ name: "get_due_cards", status: "ok" }],
  });
});

it.each([
  {
    ...proposalPart,
    payload: { ...proposalPart.payload, proposal_id: undefined },
  },
  { ...proposalPart, payload: { ...proposalPart.payload, extra: true } },
  {
    ...proposalPart,
    payload: {
      ...proposalPart.payload,
      drafts: [{ ...proposalPart.payload.drafts[0], owner_id: "private" }],
    },
  },
  { ...proposalPart, payload: { ...proposalPart.payload, proposal_id: "bad" } },
  {
    ...proposalPart,
    payload: {
      ...proposalPart.payload,
      deck: { ...proposalPart.payload.deck, id: "bad" },
    },
  },
  {
    ...proposalPart,
    payload: {
      ...proposalPart.payload,
      deck: { ...proposalPart.payload.deck, owner_id: "private" },
    },
  },
  { ...proposalPart, payload: { ...proposalPart.payload, drafts: [] } },
  {
    ...proposalPart,
    payload: {
      ...proposalPart.payload,
      warnings: [
        { ...proposalPart.payload.warnings[0], existing_card_ids: ["bad"] },
      ],
    },
  },
  {
    ...proposalPart,
    payload: {
      ...proposalPart.payload,
      warnings: [{ ...proposalPart.payload.warnings[0], owner_id: "private" }],
    },
  },
])("rejects malformed card_proposal: %j", async (part) => {
  const onPart = vi.fn();
  await readPart(proposalPart, { onPart });
  expect(onPart).toHaveBeenCalledWith(proposalPart);
  await expect(readPart(part)).rejects.toMatchObject({
    kind: "invalid_response",
  });
});

it.each([
  {
    ...cardPart,
    payload: {
      ...cardPart.payload,
      items: [{ id: "card", deck_id: "deck", meaning: "port" }],
    },
  },
  { ...cardPart, extra: true },
  { ...cardPart, payload: { ...cardPart.payload, extra: true } },
  {
    ...cardPart,
    payload: {
      ...cardPart.payload,
      items: [{ ...cardPart.payload.items[0], note: "private" }],
    },
  },
  { ...cardPart, id: 1 },
  { ...cardPart, payload: { purpose: "other", items: [] } },
])("rejects malformed known parts: %j", async (part) => {
  // A valid control makes this fail on the old parser's blanket rejection of parts.
  await readPart(cardPart);
  await expect(readPart(part)).rejects.toMatchObject({
    kind: "invalid_response",
  });
});

it("ignores unknown part types", async () => {
  const onPart = vi.fn();
  await expect(
    readPart({ id: "p2", type: "future", payload: {} }, { onPart }),
  ).resolves.toMatchObject({ stop: "completed" });
  expect(onPart).not.toHaveBeenCalled();
});

it("sends capabilities only when non-empty", async () => {
  await read([delta("answer"), done]);
  expect(JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string)).toEqual(
    { messages: [{ role: "user", content: "hello" }] },
  );
  await read([delta("answer"), done], { capabilities: ["parts.v1"] });
  expect(JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string)).toEqual(
    {
      messages: [{ role: "user", content: "hello" }],
      capabilities: ["parts.v1"],
    },
  );
  await read([delta("answer"), done], { capabilities: [] });
  expect(JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string)).toEqual(
    { messages: [{ role: "user", content: "hello" }] },
  );
});

it("serializes stream history parts and does not retry a 422", async () => {
  const messages = [
    {
      role: "assistant" as const,
      content: "Earlier reply",
      parts: [
        {
          type: "card_refs" as const,
          card_ids: ["00000000-0000-0000-0000-000000000001"],
        },
      ],
    },
    { role: "user" as const, content: "those cards" },
  ];
  const send = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({
        error: {
          code: "validation_failed",
          request_id: "history-test",
          message: "Invalid",
          retryable: false,
        },
      }),
      { status: 422, headers: { "Content-Type": "application/json" } },
    ),
  );
  vi.stubGlobal("fetch", send);
  await expect(
    streamAssistantReply(messages, () => {}, new AbortController().signal, {
      capabilities: ["parts.v1"],
    }),
  ).rejects.toMatchObject({ code: "validation_failed" });
  expect(send).toHaveBeenCalledTimes(1);
  expect(JSON.parse(send.mock.calls[0][1].body)).toEqual({
    messages,
    capabilities: ["parts.v1"],
  });
});

const clarificationPart = {
  id: "p3",
  type: "clarification_question",
  payload: {
    question_id: "30000000-0000-0000-0000-000000000101",
    question: "Which meaning of bank?",
    options: [
      { id: "40000000-0000-0000-0000-000000000101", label: "River bank" },
      {
        id: "40000000-0000-0000-0000-000000000102",
        label: "Financial institution",
      },
    ],
    allow_free_text: true,
    purpose: "term",
  },
};

it("accepts clarification_question before text and preserves tool summaries", async () => {
  const onPart = vi.fn();
  const result = await read(
    [partFrame(clarificationPart), delta("Choose a meaning."), done],
    { onPart },
  );
  expect(onPart.mock.calls).toEqual([[clarificationPart]]);
  expect(result.text).toBe("Choose a meaning.");
  expect(result.tools).toEqual([{ name: "get_due_cards", status: "ok" }]);
});

it("accepts zero through twenty server-built deck choices and optional purpose", async () => {
  for (const count of [0, 2, 20]) {
    const part = {
      ...clarificationPart,
      payload: {
        ...clarificationPart.payload,
        purpose: "deck",
        allow_free_text: false,
        options: Array.from({ length: count }, (_, i) => ({
          id: `40000000-0000-0000-0000-${String(i + 1).padStart(12, "0")}`,
          label: "Deck title ".repeat(12),
          deck_id: `10000000-0000-0000-0000-${String(i + 1).padStart(12, "0")}`,
        })),
      },
    };
    const onPart = vi.fn();
    await readPart(part, { onPart });
    expect(onPart).toHaveBeenCalledWith(part);
  }
  const payload = {
    question_id: clarificationPart.payload.question_id,
    question: clarificationPart.payload.question,
    options: clarificationPart.payload.options,
    allow_free_text: clarificationPart.payload.allow_free_text,
  };
  const onPart = vi.fn();
  await readPart({ ...clarificationPart, payload }, { onPart });
  expect(onPart).toHaveBeenCalledOnce();
});

it("accepts a free-text-only question and four distinct term options", async () => {
  for (const count of [0, 4]) {
    const part = {
      ...clarificationPart,
      payload: {
        ...clarificationPart.payload,
        options: Array.from({ length: count }, (_, i) => ({
          id: `40000000-0000-0000-0000-${String(i + 1).padStart(12, "0")}`,
          label: "A meaning",
        })),
      },
    };
    const onPart = vi.fn();
    await readPart(part, { onPart });
    expect(onPart).toHaveBeenCalledWith(part);
  }
});

it.each<unknown>([
  {
    ...clarificationPart,
    payload: {
      ...clarificationPart.payload,
      purpose: "deck",
      allow_free_text: false,
      options: Array.from({ length: 21 }, (_, i) => ({
        id: `40000000-0000-0000-0000-${String(i + 1).padStart(12, "0")}`,
        label: "Deck",
        deck_id: `10000000-0000-0000-0000-${String(i + 1).padStart(12, "0")}`,
      })),
    },
  },
  { ...clarificationPart, extra: true },
  {
    ...clarificationPart,
    payload: { ...clarificationPart.payload, extra: true },
  },
  {
    ...clarificationPart,
    payload: { ...clarificationPart.payload, question_id: "bad" },
  },
  {
    ...clarificationPart,
    payload: { ...clarificationPart.payload, question: " " },
  },
  {
    ...clarificationPart,
    payload: { ...clarificationPart.payload, question: "x".repeat(301) },
  },
  {
    ...clarificationPart,
    payload: { ...clarificationPart.payload, purpose: "write" },
  },
  {
    ...clarificationPart,
    payload: { ...clarificationPart.payload, allow_free_text: "true" },
  },
  {
    ...clarificationPart,
    payload: {
      ...clarificationPart.payload,
      options: [],
      allow_free_text: false,
    },
  },
  {
    ...clarificationPart,
    payload: {
      ...clarificationPart.payload,
      options: Array.from({ length: 5 }, (_, i) => ({
        id: `40000000-0000-0000-0000-${String(i + 1).padStart(12, "0")}`,
        label: "A meaning",
      })),
    },
  },
  {
    ...clarificationPart,
    payload: {
      ...clarificationPart.payload,
      options: [{ id: "bad", label: "River" }],
    },
  },
  {
    ...clarificationPart,
    payload: {
      ...clarificationPart.payload,
      options: [
        { ...clarificationPart.payload.options[0], label: "x".repeat(81) },
      ],
    },
  },
  {
    ...clarificationPart,
    payload: {
      ...clarificationPart.payload,
      options: [
        { ...clarificationPart.payload.options[0], owner_id: "private" },
      ],
    },
  },
  {
    ...clarificationPart,
    payload: {
      ...clarificationPart.payload,
      options: [
        {
          ...clarificationPart.payload.options[0],
          deck_id: "10000000-0000-0000-0000-000000000101",
        },
      ],
    },
  },
  {
    ...clarificationPart,
    payload: {
      ...clarificationPart.payload,
      purpose: "deck",
      allow_free_text: false,
    },
  },
  {
    ...clarificationPart,
    payload: {
      ...clarificationPart.payload,
      purpose: "deck",
      options: [],
      allow_free_text: true,
    },
  },
])("rejects malformed clarification_question: %j", async (part) => {
  const onPart = vi.fn();
  await readPart(clarificationPart, { onPart });
  expect(onPart).toHaveBeenCalledWith(clarificationPart);
  await expect(readPart(part)).rejects.toMatchObject({
    kind: "invalid_response",
  });
});
