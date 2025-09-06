import type { LayoutLoad } from './$types';
import { browser } from '$app/environment';
import { redirect } from '@sveltejs/kit';
import { getIsSignedIn } from '$lib/auth';
import { setSignIn } from '$lib/stores/auth';
import { base } from '$app/paths'; // using the paths.base set in svelte.config.js

export const load: LayoutLoad = async ({ url }) => {
    // 僅在瀏覽器端檢查（localStorage 僅存在於瀏覽器）
    if (browser) {
        const isHome = url.pathname === `${base}/`;
        const isLocalStorageSignedIn = getIsSignedIn();
        if (isLocalStorageSignedIn) {
            setSignIn();
        }
        if (!isHome && !isLocalStorageSignedIn) {
            throw redirect(307, `${base}/`);
        }
    }
    return {};
};
