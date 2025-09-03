import type { LayoutLoad } from './$types';
import { browser } from '$app/environment';
import { redirect } from '@sveltejs/kit';
import { getIsSignedIn } from '$lib/auth';

export const load: LayoutLoad = async ({ url }) => {
    // 僅在瀏覽器端檢查（localStorage 僅存在於瀏覽器）
    if (browser) {
        const isHome = url.pathname === '/';
        if (!isHome && !getIsSignedIn()) {
            throw redirect(307, '/');
        }
    }
    return {};
};