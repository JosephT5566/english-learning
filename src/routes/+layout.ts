import type { LayoutLoad } from "./$types";
import { browser } from "$app/environment";
import { redirect } from "@sveltejs/kit";
import { getIsSignedIn, initializeSession } from "$lib/auth";
import { get } from "svelte/store";
import { authSession, authOffline } from "$lib/stores/auth";
import { base } from "$app/paths";

export const load: LayoutLoad = async ({ url }) => {
  if (browser) {
    // Navigation while offline must not start another refresh retry.
    if (!get(authOffline)) await initializeSession();
    const publicRoute = [
      `${base}/`,
      `${base}/review`,
      `${base}/review/guest`,
    ].includes(url.pathname);
    if (!publicRoute && !getIsSignedIn() && get(authSession).kind !== "expired")
      redirect(307, `${base}/`);
  }
  return {};
};
