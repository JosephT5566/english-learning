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

async function read(chunks: string[]) {
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
