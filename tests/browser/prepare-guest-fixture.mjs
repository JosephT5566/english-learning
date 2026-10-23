import { copyFile, mkdir } from "node:fs/promises";

await mkdir("build/guest", { recursive: true });
await copyFile(
  new URL("./fixtures/guest-cards.json", import.meta.url),
  "build/guest/cards.json",
);
