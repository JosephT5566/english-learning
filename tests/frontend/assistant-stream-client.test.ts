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
