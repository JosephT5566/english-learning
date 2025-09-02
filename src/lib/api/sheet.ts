import type { UpdateFields, WordItem, WordListResponse } from '$lib/types';
import { PUBLIC_APP_SCRIPT_URL } from '$env/static/public';
import { mockWordItems } from './mock';
import { getValidTokenOrPrompt } from '$lib/auth';

const ENDPOINT = PUBLIC_APP_SCRIPT_URL; // .env 讀

export async function getMockWordItems(): Promise<WordItem[]> {
	// 模擬從伺服器取得資料
	return new Promise((resolve) => {
		setTimeout(() => {
			resolve(mockWordItems);
		}, 1000);
	});
}

export async function getWordList(): Promise<WordItem[]> {
	// const res = await fetch(`${ENDPOINT}?action=getList`);
	// const data = (await res.json()) as WordListResponse;
	const data = await getMockWordItems().then((items) => ({
		ok: true,
		result: items,
	}));

	if (!data.ok) {
		throw new Error('getWordList failed');
	}

	console.log('Fetched word list:', data);

	return data.result;
}

// export async function appendWord(payload: Partial<WordItem> & { word:string; meaning:string; reviewStage?: number }) {
//   const res = await fetch(ENDPOINT, {
//     method:'POST',
//     headers:{'Content-Type':'application/json'},
//     body: JSON.stringify({ token: TOKEN, op:'append', ...payload })
//   });
//   return res.json();
// }

export async function updateReview(updateFields: UpdateFields) {
  const idToken = await getValidTokenOrPrompt();
  if (!idToken) {
    throw new Error('No valid token for updateReview');
  }

	const res = await fetch(ENDPOINT, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			op: 'updateReview',
			token: idToken,
			fields: updateFields,
		}),
	});
	return res.json();
}
