import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

function git(args) {
  const result = spawnSync("git", args, { encoding: "utf8" });
  if (result.error || result.status !== 0) {
    console.error(result.error?.message || result.stderr);
    process.exit(result.status || 1);
  }
  return result.stdout;
}

let base = process.argv[2] || "HEAD";
if (/^0+$/.test(base)) {
  // A push creating a branch has no previous commit; compare with the empty tree.
  base = git(["hash-object", "-t", "tree", "--stdin"]).trim();
}

const generated = new Set([
  "apps/api/openapi.json",
  "src/lib/api/generated.ts",
  "src/lib/api/card-drafts.schema.json",
  "src/lib/api/guest-snapshot.schema.json",
]);
const files = [
  ...new Set([
    ...git([
      "diff",
      "--no-ext-diff",
      "--name-only",
      "--diff-filter=ACMR",
      "-z",
      base,
      "--",
    ]).split("\0"),
    ...git(["ls-files", "--others", "--exclude-standard", "-z"]).split("\0"),
  ]),
].filter((file) => file && existsSync(file) && !generated.has(file));

if (files.length === 0) {
  console.log(
    "No changed files to lint. Generated API artifacts use npm run api:check.",
  );
  process.exit(0);
}

for (const [binary, options] of [
  ["prettier/bin/prettier.cjs", ["--check", "--ignore-unknown"]],
  ["eslint/bin/eslint.js", ["--no-warn-ignored"]],
]) {
  const path = fileURLToPath(
    new URL(`../node_modules/${binary}`, import.meta.url),
  );
  const result = spawnSync(
    process.execPath,
    [path, ...options, "--", ...files],
    {
      stdio: "inherit",
    },
  );
  if (result.error || result.status !== 0) {
    if (result.error) console.error(result.error.message);
    process.exit(result.status || 1);
  }
}
