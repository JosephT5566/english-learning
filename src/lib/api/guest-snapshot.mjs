import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import schema from "./guest-snapshot.schema.json" with { type: "json" };

export const MAX_SNAPSHOT_BYTES = 512 * 1024;
const ajv = new Ajv2020();
addFormats(ajv, { mode: "full" });
/** @type {import('ajv').ValidateFunction<import('./generated').components['schemas']['GuestSnapshot']>} */
const validate = ajv.compile(schema);

/**
 * @param {unknown} value
 * @returns {value is import('./generated').components['schemas']['GuestSnapshot']}
 */
export function isGuestSnapshot(value) {
  return (
    validate(value) &&
    new Set(value.items.map((card) => card.id)).size === value.items.length
  );
}

/** @param {Response} response */
export async function readGuestSnapshot(response) {
  if (
    !response.ok ||
    response.redirected ||
    !response.body ||
    Number(response.headers.get("Content-Length")) > MAX_SNAPSHOT_BYTES
  ) {
    await response.body?.cancel().catch(() => {});
    throw new Error("Invalid snapshot");
  }
  const reader = response.body.getReader();
  const chunks = [];
  let bytes = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > MAX_SNAPSHOT_BYTES) throw new Error("Invalid snapshot");
      chunks.push(value);
    }
  } catch (error) {
    await reader.cancel().catch(() => {});
    throw error;
  } finally {
    reader.releaseLock();
  }
  const buffer = new Uint8Array(bytes);
  let offset = 0;
  for (const chunk of chunks) {
    buffer.set(chunk, offset);
    offset += chunk.byteLength;
  }
  /** @type {unknown} */
  const value = JSON.parse(
    new TextDecoder("utf-8", { fatal: true }).decode(buffer),
  );
  if (!isGuestSnapshot(value)) throw new Error("Invalid snapshot");
  return { snapshot: value, bytes };
}
