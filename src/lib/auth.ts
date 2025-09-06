import { PUBLIC_GOOGLE_AUTH_CLIENT_ID, PUBLIC_EMAIL_WHITE_LIST } from '$env/static/public';
import { browser } from '$app/environment';
import { setSignIn } from './stores/auth';

// ======== 設定 ========
const STORAGE_TOKEN = 'gid_id_token';
const STORAGE_EXP = 'gid_exp'; // 秒級 UNIX time
const SAFETY_BUFFER_SEC = 60; // 快過期前 60 秒就視為無效
const MAX_SKEW_SEC = 60; // 允許裝置時間偏差（保守）

let buttonRendered = false;
let gsiInitialized = false;

// ======== 公用工具 ========
type JwtPayload = {
	iss: string;
	aud: string;
	exp: number; // seconds
	email?: string;
	email_verified?: boolean;
	name?: string;
	picture?: string;
	sub?: string;
};

function decodeJwt(token: string): JwtPayload {
	const [, payload] = token.split('.');
	const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
	return JSON.parse(json);
}

function nowSec() {
	return Math.floor(Date.now() / 1000);
}

// ======== localStorage 存取 ========
function saveToken(token: string, exp: number) {
	localStorage.setItem(STORAGE_TOKEN, token);
	localStorage.setItem(STORAGE_EXP, String(exp));
}

function loadToken(): { token: string | null; exp: number } {
	const token = localStorage.getItem(STORAGE_TOKEN);
	const exp = Number(localStorage.getItem(STORAGE_EXP) || 0);
	return { token, exp };
}

function clearToken() {
	localStorage.removeItem(STORAGE_TOKEN);
	localStorage.removeItem(STORAGE_EXP);
}

// 是否有效（含緩衝與時間偏差）
function isTokenStillValid(exp: number) {
	const now = nowSec();
	return now + SAFETY_BUFFER_SEC + MAX_SKEW_SEC < exp;
}

// ======== 狀態查詢 ========
export function getIsSignedIn(): boolean {
	const { token, exp } = loadToken();
	if (!token || !exp) {
		return false;
	}
	return isTokenStillValid(exp);
}

export function getProfile(): JwtPayload | null {
	const { token, exp } = loadToken();
	if (!token || !exp || !isTokenStillValid(exp)) {
		return null;
	}

	try {
		return decodeJwt(token);
	} catch {
		return null;
	}
}

export function getTokenIfValid(): string | null {
	const { token, exp } = loadToken();
	if (!token || !exp || !isTokenStillValid(exp)) {
		return null;
	}

	return token;
}

// ======== 登入流程（按鈕/自動） ========

export function initGsiOnce(onError?: (e: Error) => void) {
	if (!browser) {
		return;
	}

	const gis = window?.google?.accounts?.id;
	if (!gis) {
		throw new Error('Google Identity Services 未載入');
	}

	const EMAIL_WHITE_LIST: string[] = PUBLIC_EMAIL_WHITE_LIST.split(',');
	if (gsiInitialized) {
		return;
	}
	gis.initialize({
		client_id: PUBLIC_GOOGLE_AUTH_CLIENT_ID,
		cancel_on_tap_outside: false,
		use_fedcm_for_prompt: true,
		callback: (res: { credential?: string }) => {
			try {
				const idToken = res?.credential;
				if (!idToken) {
					throw new Error('Did not receive Google ID token');
				}
				const payload = decodeJwt(idToken) as JwtPayload;

				if (!payload.email || !payload.email_verified) {
					throw new Error('Google login failed: Email not verified');
				}
				const email = String(payload.email).toLowerCase();
				if (!EMAIL_WHITE_LIST.includes(email)) {
					throw new Error('Google login failed: Email not in whitelist');
				}

				if (!payload.exp) {
					throw new Error('Google login failed: No exp in token');
				}
				saveToken(idToken, payload.exp);
				setSignIn();
			} catch (e) {
				onError?.(e instanceof Error ? e : new Error('Google login failed'));
			}
		},
	});
	gsiInitialized = true;
}

export function renderGoogleButton(container: HTMLElement) {
	if (!container || buttonRendered) {
		return;
	}

	const gis = window.google.accounts.id;
	container.innerHTML = '';
	gis.renderButton(container, {
		type: 'standard',
		theme: 'outline',
		size: 'large',
		text: 'signin_with',
		shape: 'pill',
		logo_alignment: 'left',
		width: 320,
	});
	buttonRendered = true;
}

// ======== 登出 ========
export function signOut() {
	clearToken();
	// 可選：通知 GIS 取消自動選擇
	try {
		window.google?.accounts?.id?.disableAutoSelect?.();
	} catch {
		console.log('Signout failed');
	}
}
