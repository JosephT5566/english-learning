import type { WordItem, WordListResponse } from "$lib/types";
import { PUBLIC_APP_SCRIPT_URL } from "$env/static/public";
import { mockWordItems } from "./mock";

const ENDPOINT = PUBLIC_APP_SCRIPT_URL; // .env 讀

export async function getMockWordItems(): Promise<WordItem[]> {
  // 模擬從伺服器取得資料
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve(mockWordItems);
    }, 500);
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
    throw new Error("listDue failed");
  }

  console.log("Fetched word list:", data);

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

export async function updateReview(id: string, correct: boolean) {
  const res = await fetch(ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ op: "updateReview", id, correct }),
  });
  return res.json();
}
