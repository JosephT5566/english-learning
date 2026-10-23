import { createReadStream } from "node:fs";
import { Readable } from "node:stream";
import { readGuestSnapshot } from "../src/lib/api/guest-snapshot.mjs";

try {
  if (process.argv.length !== 3) throw new Error("Missing snapshot path");
  const { snapshot, bytes } = await readGuestSnapshot(
    new Response(Readable.toWeb(createReadStream(process.argv[2]))),
  );
  process.stdout.write(
    `Validated ${snapshot.items.length} guest cards (${bytes} bytes).\n`,
  );
} catch {
  process.stderr.write("Guest snapshot validation failed.\n");
  process.exitCode = 1;
}
