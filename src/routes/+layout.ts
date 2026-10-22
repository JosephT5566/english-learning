import type { LayoutLoad } from "./$types";
import { browser } from "$app/environment";
import { redirect } from "@sveltejs/kit";
import { getIsSignedIn, initializeSession } from "$lib/auth";
import { base } from "$app/paths";

export const load: LayoutLoad = ({ url }) => {
  if (browser) {
    initializeSession();
    const publicRoute = [
      `${base}/`,
      `${base}/review`,
      `${base}/review/guest`,
    ].includes(url.pathname);
    if (!publicRoute && !getIsSignedIn()) redirect(307, `${base}/`);
  }
  return {};
};
