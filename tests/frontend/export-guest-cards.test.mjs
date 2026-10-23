import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";
import { exportGuestCards } from "../../scripts/export-guest-cards.mjs";

const card = {
  id: "00000000-0000-4000-8000-000000000001",
  target_language: "en",
  term: "synthetic",
  meaning: "fixture",
  pronunciation: null,
  reading: null,
  romanization: null,
  part_of_speech: null,
  part_of_speech_detail: null,
  target_language_definition: null,
  example_sentence: null,
  example_translation: null,
  synonyms: [],
  antonyms: [],
};
const snapshot = {
  schema_version: 1,
  generated_at: "2026-10-23T00:00:00Z",
  items: [card],
};

for (const [name, value] of [
  ["version", { ...snapshot, schema_version: 2 }],
  ["timestamp", { ...snapshot, generated_at: "bad" }],
  ["timezone", { ...snapshot, generated_at: "2026-10-23T00:00:00" }],
  ["extra envelope", { ...snapshot, token: "private" }],
  ["private field", { ...snapshot, items: [{ ...card, note: "private" }] }],
  ["language", { ...snapshot, items: [{ ...card, target_language: "ja" }] }],
  ["duplicates", { ...snapshot, items: [card, card] }],
  [
    "51 cards",
    {
      ...snapshot,
      items: Array.from({ length: 51 }, (_, i) => ({
        ...card,
        id: `00000000-0000-4000-8000-${String(i).padStart(12, "0")}`,
      })),
    },
  ],
  ["missing fields", { ...snapshot, items: [{ id: card.id }] }],
]) {
  test(`rejects ${name} and retains previous output`, async () => {
    const dir = await mkdtemp(path.join(os.tmpdir(), "guest-export-"));
    const output = path.join(dir, "cards.json");
    try {
      await writeFile(output, "previous");
      await assert.rejects(
        exportGuestCards({
          apiOrigin: "https://api.example.test",
          token: "secret-token",
          output,
          fetcher: async () => new Response(JSON.stringify(value)),
        }),
        /Export failed/,
      );
      assert.equal(await readFile(output, "utf8"), "previous");
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });
}

test("writes validated empty or populated snapshot atomically without logging contents", async () => {
  const dir = await mkdtemp(path.join(os.tmpdir(), "guest-export-"));
  try {
    for (const items of [[], [card]]) {
      const output = path.join(dir, "cards.json");
      const result = await exportGuestCards({
        apiOrigin: "https://api.example.test",
        token: "short-token",
        output,
        fetcher: async (url, options) => {
          assert.equal(
            url,
            "https://api.example.test/v1/internal/guest-cards/export",
          );
          assert.equal(options.redirect, "error");
          assert.equal(options.headers.Authorization, "Bearer short-token");
          return new Response(JSON.stringify({ ...snapshot, items }));
        },
      });
      assert.equal(result.count, items.length);
      assert.deepEqual(JSON.parse(await readFile(output, "utf8")), {
        ...snapshot,
        items,
      });
    }
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

for (const [name, fetcher] of [
  [
    "redirect",
    async () =>
      new Response(null, {
        status: 302,
        headers: { Location: "https://evil.test" },
      }),
  ],
  ["oversize", async () => new Response("x".repeat(512 * 1024 + 1))],
  [
    "failed HTTP",
    async () => new Response("private-error-body", { status: 500 }),
  ],
  ["invalid JSON", async () => new Response("private-invalid-json")],
  [
    "network",
    async () => {
      throw new Error("private-token");
    },
  ],
])
  test(`safe failure on ${name}`, async () => {
    await assert.rejects(
      exportGuestCards({
        apiOrigin: "https://api.example.test",
        token: "private-token",
        output: "/tmp/unused-guest.json",
        fetcher,
      }),
      (error) =>
        error.message === "Export failed; existing snapshot was retained.",
    );
  });

test("rejects unsafe URLs before transport", async () => {
  for (const apiOrigin of [
    "http://api.test",
    "https://user:pass@api.test",
    "https://api.test/?secret=x",
    "https://api.test/path",
  ]) {
    await assert.rejects(
      exportGuestCards({
        apiOrigin,
        token: "token",
        output: "/tmp/unused-guest.json",
        fetcher: async () => assert.fail("must not fetch"),
      }),
    );
  }
});

test("timeout covers response streaming", async () => {
  await assert.rejects(
    exportGuestCards({
      apiOrigin: "https://api.example.test",
      token: "token",
      output: "/tmp/unused-guest.json",
      timeoutMs: 10,
      fetcher: async (_url, { signal }) =>
        new Response(
          new ReadableStream({
            start(controller) {
              signal.addEventListener("abort", () =>
                controller.error(new Error("aborted")),
              );
            },
          }),
        ),
    }),
    /Export failed/,
  );
});

for (const [name, options] of [
  ["rejected status", { status: 503 }],
  [
    "oversized header",
    { headers: { "Content-Length": String(512 * 1024 + 1) } },
  ],
]) {
  test(`cancels unread stream on ${name}`, async () => {
    let cancelled = false;
    const body = new ReadableStream({
      cancel() {
        cancelled = true;
      },
    });
    await assert.rejects(
      exportGuestCards({
        apiOrigin: "https://api.example.test",
        token: "short-token",
        output: "/tmp/unused-guest.json",
        fetcher: async () => new Response(body, options),
      }),
    );
    assert.equal(cancelled, true);
  });
}
