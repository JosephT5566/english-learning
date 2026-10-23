import { mkdir, rename, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { randomUUID } from "node:crypto";
import {
  readGuestSnapshot,
  MAX_SNAPSHOT_BYTES,
} from "../src/lib/api/guest-snapshot.mjs";

export async function exportGuestCards({
  apiOrigin,
  token,
  output,
  fetcher = fetch,
  timeoutMs = 30000,
}) {
  let temporary;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const url = new URL(apiOrigin);
    if (
      url.protocol !== "https:" ||
      url.username ||
      url.password ||
      url.search ||
      url.hash ||
      url.pathname !== "/" ||
      !token ||
      !output
    )
      throw new Error("Invalid configuration");
    const response = await fetcher(
      `${url.origin}/v1/internal/guest-cards/export`,
      {
        headers: { Authorization: `Bearer ${token}` },
        redirect: "error",
        signal: controller.signal,
      },
    );
    const { snapshot } = await readGuestSnapshot(response);
    const data = `${JSON.stringify(snapshot)}\n`;
    const bytes = Buffer.byteLength(data);
    if (bytes > MAX_SNAPSHOT_BYTES) throw new Error("Invalid snapshot");
    await mkdir(path.dirname(output), { recursive: true });
    temporary = `${output}.${randomUUID()}.tmp`;
    await writeFile(temporary, data, { flag: "wx", mode: 0o600 });
    await rename(temporary, output);
    return { count: snapshot.items.length, bytes };
  } catch {
    throw new Error("Export failed; existing snapshot was retained.");
  } finally {
    controller.abort();
    clearTimeout(timer);
    if (temporary) await rm(temporary, { force: true }).catch(() => {});
  }
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  try {
    const result = await exportGuestCards({
      apiOrigin: process.env.GUEST_EXPORT_API_ORIGIN,
      token: process.env.GUEST_EXPORT_TOKEN,
      output: process.argv[2],
    });
    process.stdout.write(
      `Exported ${result.count} cards (${result.bytes} bytes).\n`,
    );
  } catch {
    process.stderr.write("Export failed; existing snapshot was retained.\n");
    process.exitCode = 1;
  }
}
