import { copyFile, mkdir } from "node:fs/promises";
await mkdir("static/guest", { recursive: true });
await copyFile(
  "tests/browser/fixtures/guest-cards.json",
  "static/guest/cards.json",
);
