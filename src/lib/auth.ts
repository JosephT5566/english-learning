import { PUBLIC_GOOGLE_AUTH_CLIENT_ID, PUBLIC_EMAIL_WHITE_LIST } from '$env/static/public';

// ======== 設定 ========
const STORAGE_TOKEN = 'gid_id_token';
const STORAGE_EXP = 'gid_exp'; // 秒級 UNIX time
const SAFETY_BUFFER_SEC = 60; // 快過期前 60 秒就視為無效
const MAX_SKEW_SEC = 60; // 允許裝置時間偏差（保守）

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

// 按鈕觸發：顯式登入（改為回傳 Promise）
export function signIn(): Promise<{ token: string; payload: JwtPayload }> {
	return new Promise((resolve, reject) => {
		try {
			const EMAIL_WHITE_LIST: string[] = PUBLIC_EMAIL_WHITE_LIST.split(',');
			const gis = window?.google?.accounts?.id;
			if (!gis) {
				reject(new Error('Google Identity Services has not been loaded'));
				return;
			}

			gis.initialize({
				client_id: PUBLIC_GOOGLE_AUTH_CLIENT_ID,
				callback: (res) => {
					try {
						const idToken = res?.credential as string | undefined;
						if (!idToken) {
							reject(new Error('Did not receive Google ID token'));
							return;
						}
						const payload = decodeJwt(idToken);

						if (!payload.email || !payload.email_verified) {
							reject(new Error('Google login failed: Email not verified'));
							return;
						}
						if (!EMAIL_WHITE_LIST.includes(payload.email)) {
							reject(new Error('Google login failed: Email not in whitelist'));
							return;
						}
						if (!payload.exp) {
							reject(new Error('Google login failed: No exp in token'));
							return;
						}

						saveToken(idToken, payload.exp);
						resolve({ token: idToken, payload });
					} catch (e) {
						reject(e instanceof Error ? e : new Error('Google login failed'));
					}
				},
			});

			// 顯示 One Tap；若未顯示或被略過，回傳 reject 方便外部處理
			gis.prompt?.((notification) => {
				try {
					if (notification?.isNotDisplayed?.()) {
						const reason = notification?.getNotDisplayedReason?.() ?? 'unknown';
						reject(new Error(`Google login not displayed: ${reason}`));
					} else if (notification?.isSkippedMoment?.()) {
						const reason = notification?.getSkippedReason?.() ?? 'unknown';
						reject(new Error(`Google login skipped: ${reason}`));
					}
				} catch {
					// 忽略 prompt 回呼中的例外
				}
			});
		} catch (err) {
			reject(err instanceof Error ? err : new Error('Google login failed'));
		}
	});
}

// 在需要時（頁面載入或提交前）確保有有效 token；沒有就彈登入
export async function getValidTokenOrPrompt() {
	const token = getTokenIfValid();
	if (token) {
		return { token: token, payload: decodeJwt(token) };
	}
	// 沒有或快過期 → 重新登入（回傳 Promise）
	return await signIn();
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
