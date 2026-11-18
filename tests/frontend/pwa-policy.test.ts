import { describe, expect, it } from "vitest";
import {
  eligibleRequest,
  precacheFile,
  shellPrecache,
  cachesToDelete,
  cacheableSnapshot,
  SHELL_PREFIX,
  GUEST_CACHE,
} from "../../src/lib/pwa/policy";

describe("PWA cache boundaries", () => {
  it("only intercepts same-origin GETs inside the base", () => {
    const accepts = (path: string, method = "GET") =>
      eligibleRequest(
        { method, url: new URL(path, "https://example.com").href },
        "https://example.com",
        "/study",
      );
    expect(accepts("/study/")).toBe(true);
    for (const path of [
      "/study2/a",
      "/v1/cards",
      "/study/v1/cards",
      "/study/_app/version.json",
      "/study/service-worker.js",
      "/study/robots.txt",
      "/study/.nojekyll",
      "https://accounts.google.com/a",
      "https://fonts.googleapis.com/a",
    ])
      expect(accepts(path)).toBe(false);
    expect(accepts("/study/a", "POST")).toBe(false);
  });
  it("excludes guest, dotfiles and metadata from shell precache", () => {
    for (const path of [
      "/study/guest/cards.json",
      "/study/robots.txt",
      "/study/.nojekyll",
      "/study/a/.hidden",
      "/study/_app/version.json",
    ])
      expect(precacheFile(path)).toBe(false);
    expect(precacheFile("/study/manifest.webmanifest")).toBe(true);
    expect(precacheFile("/study/icons/icon-192.png")).toBe(true);
  });
  it.each(["", "/study"])(
    "includes generated startup files under base %s",
    (base) => {
      const entries = shellPrecache(
        base,
        [`${base}/asset.js`],
        [`${base}/_app/version.json`, `${base}/guest/cards.json`],
        [`${base}/`],
      );
      expect(entries).toEqual([
        `${base}/asset.js`,
        `${base}/`,
        `${base}/404.html`,
        `${base}/_app/env.js`,
      ]);
      expect(
        eligibleRequest(
          { method: "GET", url: `https://example.com${base}/_app/env.js` },
          "https://example.com",
          base,
        ),
      ).toBe(true);
    },
  );
  it("cleans only owned obsolete caches and supports kill switch", () => {
    const names = [
      SHELL_PREFIX + "old",
      SHELL_PREFIX + "current",
      GUEST_CACHE,
      "english-learning-guest-v0",
      "foreign",
    ];
    expect(cachesToDelete(names, SHELL_PREFIX + "current")).toEqual([
      names[0],
      names[3],
    ]);
    expect(cachesToDelete(names, null)).toEqual(names.slice(0, 4));
  });
  it("accepts empty snapshots and rejects invalid status, redirects, size, JSON and shape", async () => {
    const response = (body: string, status = 200) =>
      new Response(body, { status });
    expect(
      await cacheableSnapshot(response('{"schema_version":1,"items":[]}')),
    ).toBe(true);
    for (const value of [
      response("{}"),
      response("bad"),
      response('{"schema_version":2,"items":[]}'),
      response('{"schema_version":1,"items":{}}'),
      response(
        JSON.stringify({
          schema_version: 1,
          items: [],
          padding: "x".repeat(512 * 1024),
        }),
      ),
      response("{}", 404),
      response("{}", 201),
    ])
      expect(await cacheableSnapshot(value)).toBe(false);
    const redirected = response('{"schema_version":1,"items":[]}');
    Object.defineProperty(redirected, "redirected", { value: true });
    expect(await cacheableSnapshot(redirected)).toBe(false);
  });
});
