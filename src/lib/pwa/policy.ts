export const SHELL_PREFIX = "english-learning-shell-";
export const GUEST_PREFIX = "english-learning-guest-";
export const GUEST_CACHE = `${GUEST_PREFIX}v1`;
export const GUEST_TIMEOUT_MS = 3000;
export const MAX_SNAPSHOT_BYTES = 512 * 1024;

export function precacheFile(path: string): boolean {
  return (
    !path.split("/").some((part) => part.startsWith(".")) &&
    !/(?:^|\/)(?:guest\/cards\.json|robots\.txt|_app\/version\.json|service-worker\.js)$/.test(
      path,
    )
  );
}

// SvelteKit generates these startup files outside its build/files lists.
export function shellPrecache(
  base: string,
  build: readonly string[],
  files: readonly string[],
  prerendered: readonly string[],
): string[] {
  return [
    ...new Set([
      ...build,
      ...files.filter(precacheFile),
      ...prerendered,
      `${base}/404.html`,
      `${base}/_app/env.js`,
    ]),
  ];
}

export function eligibleRequest(
  request: Pick<Request, "method" | "url">,
  origin: string,
  base: string,
): boolean {
  const url = new URL(request.url);
  if (
    request.method !== "GET" ||
    url.origin !== origin ||
    !(url.pathname === base || url.pathname.startsWith(`${base}/`))
  )
    return false;
  const relative = url.pathname.slice(base.length);
  return (
    !relative.startsWith("/v1/") &&
    precacheFile(relative.replace(/\/guest\/cards\.json$/, "/guest-snapshot"))
  );
}

export function cachesToDelete(
  names: string[],
  currentShell: string | null,
): string[] {
  return names.filter(
    (name) =>
      (name.startsWith(SHELL_PREFIX) && name !== currentShell) ||
      (name.startsWith(GUEST_PREFIX) &&
        (currentShell === null || name !== GUEST_CACHE)),
  );
}

export async function cacheableSnapshot(response: Response): Promise<boolean> {
  if (response.status !== 200 || response.redirected) return false;
  try {
    const bytes = await response.clone().arrayBuffer();
    if (bytes.byteLength > MAX_SNAPSHOT_BYTES) return false;
    const value = JSON.parse(new TextDecoder().decode(bytes));
    return (
      value !== null && value.schema_version === 1 && Array.isArray(value.items)
    );
  } catch {
    return false;
  }
}
