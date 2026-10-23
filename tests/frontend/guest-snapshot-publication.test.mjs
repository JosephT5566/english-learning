import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import { exportGuestCards } from "../../scripts/export-guest-cards.mjs";
import { MAX_SNAPSHOT_BYTES } from "../../src/lib/api/guest-snapshot.mjs";

const validator = fileURLToPath(
  new URL("../../scripts/validate-guest-snapshot.mjs", import.meta.url),
);
const preparer = fileURLToPath(
  new URL("../browser/prepare-guest-fixture.mjs", import.meta.url),
);
const fixture = new URL(
  "../browser/fixtures/guest-cards.json",
  import.meta.url,
);
const snapshot = JSON.parse(await readFile(fixture, "utf8"));

for (const [name, content, valid] of [
  ["empty", JSON.stringify({ ...snapshot, items: [] }), true],
  ["public cards", JSON.stringify(snapshot), true],
  [
    "private fields",
    JSON.stringify({ ...snapshot, token: "private-sentinel" }),
    false,
  ],
  [
    "duplicate cards",
    JSON.stringify({
      ...snapshot,
      items: [snapshot.items[0], snapshot.items[0]],
    }),
    false,
  ],
  ["invalid JSON", "private-sentinel", false],
  ["oversize", "private-sentinel".repeat(40000), false],
  ["invalid UTF-8", Buffer.from([0xff]), false],
]) {
  test(`local validation handles ${name} without leaking content`, async () => {
    const directory = await mkdtemp(path.join(os.tmpdir(), "guest-validator-"));
    try {
      await writeFile(path.join(directory, "cards.json"), content);
      const result = spawnSync(process.execPath, [validator, "cards.json"], {
        cwd: directory,
        encoding: "utf8",
      });
      assert.equal(result.status, valid ? 0 : 1, result.stderr);
      assert.doesNotMatch(
        result.stdout + result.stderr,
        /private-sentinel|synthetic guest/,
      );
      if (valid)
        assert.match(
          result.stdout,
          /^Validated \d+ guest cards \(\d+ bytes\).\n$/,
        );
      else assert.equal(result.stderr, "Guest snapshot validation failed.\n");
      assert.deepEqual(
        await readFile(path.join(directory, "cards.json")),
        Buffer.from(content),
      );
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });
}

test("missing local snapshot fails with a fixed safe message", () => {
  const result = spawnSync(
    process.execPath,
    [validator, "/missing/private-sentinel.json"],
    { encoding: "utf8" },
  );
  assert.equal(result.status, 1);
  assert.equal(result.stderr, "Guest snapshot validation failed.\n");
  assert.equal(result.stdout, "");
});

test("browser fixture preparation updates only build output and preserves source snapshot", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "guest-fixture-"));
  try {
    await mkdir(path.join(directory, "static/guest"), { recursive: true });
    await writeFile(
      path.join(directory, "static/guest/cards.json"),
      "source-sentinel",
    );
    const result = spawnSync(process.execPath, [preparer], {
      cwd: directory,
      encoding: "utf8",
    });
    assert.equal(result.status, 0, result.stderr);
    assert.equal(
      await readFile(path.join(directory, "static/guest/cards.json"), "utf8"),
      "source-sentinel",
    );
    assert.deepEqual(
      await readFile(path.join(directory, "build/guest/cards.json")),
      await readFile(fixture),
    );
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

const prettier = fileURLToPath(
  new URL("../../node_modules/prettier/bin/prettier.cjs", import.meta.url),
);

for (const nearLimit of [false, true]) {
  test(`proposal formatting ${nearLimit ? "rejects growth beyond size cap" : "passes changed-file formatting after compact export"}`, async () => {
    const directory = await mkdtemp(path.join(os.tmpdir(), "guest-proposal-"));
    try {
      const value = structuredClone(snapshot);
      if (nearLimit) {
        const compactBytes = Buffer.byteLength(JSON.stringify(value));
        value.items[0].meaning += "x".repeat(
          MAX_SNAPSHOT_BYTES - compactBytes - 20,
        );
      }
      const output = path.join(directory, "cards.json");
      await exportGuestCards({
        apiOrigin: "https://api.example.test",
        token: "synthetic-token",
        output,
        fetcher: async () => new Response(JSON.stringify(value)),
      });
      assert.equal(spawnSync(process.execPath, [validator, output]).status, 0);
      assert.equal(
        spawnSync(process.execPath, [prettier, "--write", output]).status,
        0,
      );
      const validated = spawnSync(process.execPath, [validator, output], {
        encoding: "utf8",
      });
      assert.equal(validated.status, nearLimit ? 1 : 0);
      if (nearLimit) {
        assert.equal(validated.stderr, "Guest snapshot validation failed.\n");
        assert.ok((await readFile(output)).length > MAX_SNAPSHOT_BYTES);
      } else {
        assert.equal(
          spawnSync(process.execPath, [prettier, "--check", output]).status,
          0,
        );
        assert.deepEqual(JSON.parse(await readFile(output, "utf8")), value);
      }
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });
}
