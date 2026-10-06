# Issue #53：JSON 卡片建立功能與批次儲存筆記

日期：2026-10-06

分支：`feat/issue-53-json-card-authoring`

相關議題：[Issue #53](https://github.com/JosephT5566/english-learning/issues/53)

## 1. 功能目的與範圍

原本新增卡片需要在抽屜中逐一填寫欄位。本分支保留手動建立方式，新增 JSON 分頁，讓使用者在自己的 AI 工具產生卡片草稿，再回到應用程式驗證、編輯、選取與確認。

應用程式提供包含 JSON 格式與欄位限制的 prompt，依目前牌組的目標語言與解釋語言調整內容。這次沒有串接 AI 生成服務；AI 輸出與使用者貼上的內容都視為不可信輸入。

## 2. 本分支的變更歷程

| 階段          | 變更                                                                              | 提交             |
| ------------- | --------------------------------------------------------------------------------- | ---------------- |
| JSON 建立流程 | 新增分頁、牌組語言 prompt、後端草稿驗證、可編輯預覽與持久化重試                   | `1e2224d`        |
| 前端即時驗證  | 使用 Ajv 與後端匯出的 JSON Schema，在送出前顯示欄位錯誤                           | `c75629b`        |
| 批次確認儲存  | 以 `createCards()` 和批次 API 取代逐張呼叫 `createCard()`，加入原子交易與相關測試 | 與本筆記一起提交 |

最初的 JSON 流程沿用單張 API，因此前幾張成功、後一張失敗時會留下部分成功。最後的實作改為一次提交選取的卡片，讓本次新增資料一起成功或一起回滾。

## 3. 使用者操作與資料流程

1. 進入既有牌組，開啟新增卡片抽屜並切換到 JSON 分頁。
2. 複製牌組專用 prompt，交給自己的 AI 工具，並貼回 JSON。
3. 前端在輸入停止約 350 ms 後進行本機驗證，不呼叫 API。
4. 點選「Validate and preview」，由後端驗證欄位、牌組歸屬與封存狀態，回傳正規化的草稿。
5. 使用者編輯草稿或取消選取不需要的卡片。
6. 點選「Add selected cards」，重新驗證編輯後的選取內容，再用一個批次請求確認儲存。
7. 前端驗證成功回應的數量、重試鍵、牌組與卡片 ID，才將整組選取內容標示為已新增。

格式驗證通過不代表內容正確。AI 仍可能提供錯誤的意思、讀音或例句，所以預覽與明確確認是必要的產品步驟。

## 4. API 合約與輸入格式

| API                                             | 用途                               | 是否寫入卡片 |
| ----------------------------------------------- | ---------------------------------- | ------------ |
| `POST /v1/decks/{deck_id}/card-drafts/validate` | 驗證並回傳草稿                     | 否           |
| `POST /v1/cards`                                | 原有的單張卡片建立，供手動表單使用 | 是，單張     |
| `POST /v1/decks/{deck_id}/cards/bulk`           | 確認並儲存選取的多張卡片           | 是，批次交易 |

使用者貼上的 JSON 只包含學習內容：

```json
{
	"cards": [
		{ "term": "steady", "meaning": "穩定的" },
		{ "term": "practice", "meaning": "練習" }
	]
}
```

批次確認時，前端為每張卡片帶上穩定的 UUID 重試鍵。以下是確認請求的簡化範例；實際送出的是已正規化的欄位：

```json
{
	"cards": [
		{
			"idempotency_key": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
			"fields": { "term": "steady", "meaning": "穩定的" }
		},
		{
			"idempotency_key": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
			"fields": { "term": "practice", "meaning": "練習" }
		}
	]
}
```

`deck_id` 是前端從目前牌組取得的既有 ID，放在 URL 路徑中。卡片 JSON 不接受擁有者、牌組 ID、語言或複習排程等欄位；身分與牌組資料由後端決定。

驗證及批次 API 均限制為 1–20 張卡片與最多 100,000 bytes 的 JSON request body。批次大小包含重試鍵與外層結構，因此接近大小上限的原始 JSON 不保證確認請求仍在上限內。這是應用程式選擇的限制，不是 HTTP 或 PostgreSQL 的固定限制。

## 5. 前後端驗證如何分工

後端使用 Pydantic 的 `CardFields`、`CardDrafts` 與 `CardBulkCreate`，拒絕額外欄位，檢查必填值、型別、長度、日期及跨欄位依賴。批次請求內的重試鍵不得重複。

前端使用 Ajv 與 `ajv-formats`，載入從 Pydantic 匯出的 `src/lib/api/card-drafts.schema.json`。受限制的字串會先去除前後空白，列舉值與日期則保持原值。例句翻譯或來源需要例句，`part_of_speech` 為 `other` 時需要補充說明；這些既有規則也由後端公布在 Schema 中。

前端驗證提供即時回饋，不能取代後端驗證。直接呼叫 API 的使用者仍必須通過身分、歸屬、封存狀態及完整欄位驗證。OpenAPI、TypeScript 型別與草稿 Schema 都由後端產生並檢查同步。

## 6. 原子交易、重試與 embeddings

單張與批次 API 共用 `_create_card_in_transaction()`。這個函式建立或重播卡片，但不自行 commit；由外層 API 決定交易範圍。批次 API 在全部項目完成後才 commit，將新卡片、初始 review state 與 semantic content hash 一起保存。若後面的卡片發生重試鍵內容衝突，前面本次新增的資料也會回滾。

每張卡片沿用既有的 owner-scoped 重試鍵與正規化內容 hash。同一組內容與鍵再次送出會回傳既有卡片；同一鍵對應不同內容會被拒絕。這也讓舊版逐張儲存留下的待確認草稿可以重播，而不需新增重試資料表或資料庫 migration。

後端鎖定所屬牌組資料列，避免建立卡片與封存牌組交錯；批次按重試鍵排序處理，再依原輸入順序回傳結果。已存在卡片的完全相同重播可在牌組封存後回傳，但封存牌組不能新增卡片。

前端在寫入前保存整組選取內容與鍵。如果網路中斷、回應格式不完整或結果不明確，草稿不會自動過期，編輯與改變選取會被鎖定，重新載入後可以原樣重試。已確認的卡片會跳過；明確拒絕保留原鍵，編輯草稿時才產生新鍵。若本機儲存失敗，前端不開始寫入。

批次的 embeddings 在交易完成並回應後，以程序內的 background tasks 嘗試產生，不延遲卡片確認。它們不是持久化工作佇列；程序中斷或供應商失敗時，使用既有 backfill 修復，不能回滾已確認的卡片。

## 7. 主要修改位置

| 檔案                                         | 責任                                               |
| -------------------------------------------- | -------------------------------------------------- |
| `src/lib/components/JsonCardForm.svelte`     | JSON 分頁、預覽、編輯、選取、批次提交與重試狀態    |
| `src/lib/management/json-cards.ts`           | Prompt、草稿與 account-scoped 本機保存             |
| `src/lib/management/json-card-validation.ts` | Ajv 本機驗證與可讀錯誤                             |
| `src/lib/api/client.ts`                      | `validateCardDrafts()`、`createCards()` 與回應檢查 |
| `apps/api/app/writes.py`                     | Pydantic 模型、草稿驗證、共用單張寫入與批次交易    |
| `apps/api/scripts/export_openapi.py`         | OpenAPI 與草稿 JSON Schema 匯出                    |
| `doc/architecture.md`、`doc/decisions.md`    | 最終資料流程與設計決策                             |

## 8. 驗證結果與限制

本次批次改動完成以下本機驗證：

- `npm run check`：0 errors、0 warnings。
- 前端測試：22 個 Node 測試與 50 個 Vitest 測試通過。
- 後端 unit tests：168 個通過。
- PostgreSQL integration tests：25 個通過，涵蓋批次成功、回滾、並行重播、舊單張鍵重播、權限、封存與 embedding 失敗。
- Chrome browser tests：23 個通過，涵蓋一次請求新增兩張卡片、編輯與選取、重新載入後原樣重試，以及既有手動管理流程。
- `BASE_PATH=/english-learning npm run build` 通過，確認靜態子路徑建置。
- 後端 Ruff、修改檔案的 ESLint／Prettier 與 API 產物重新生成一致性檢查通過。

Repository-wide `npm run lint` 仍因全專案 95 個檔案的格式檢查失敗；這次沒有重排無關檔案。後端測試另有既有的 Starlette TestClient 棄用警告。

目前沒有 production 負載測試或部署驗證。20 張的上限是合理的起始界線，不能解讀為已證明 production 延遲或吞吐量；後續應觀察實際請求大小、回應時間與失敗率，再決定是否調整。

## 9. What we learned

### REST 路徑的複數不是批次保證

`/cards` 表示卡片集合，並不代表每次 POST 能建立多張。能接受單一物件還是陣列，由 request schema 決定。保留原本的單張合約，新增明確的 `/cards/bulk`，可避免破壞手動表單與既有客戶端。

### 批次 API 改變的是交易語意

把前端迴圈包成一個 `createCards()` 函式，若底層仍逐張發出請求，就沒有原子性。真正的批次儲存需要後端擁有整組交易，而且內部共用函式不能逐張 commit。

### 驗證成功與確認建立是兩個邊界

JSON 格式正確、欄位符合 Schema，只能證明輸入結構有效。學習內容是否值得加入牌組，仍需要使用者檢查。唯讀驗證 endpoint 與確認寫入 endpoint 分開，可以維持這個邊界。

### 重試安全要涵蓋「可能已成功」

前端沒收到有效回應，不等於後端沒有 commit。重試必須保留相同內容與鍵，並在重新載入後繼續使用；不能每次失敗就重新產生鍵。共用單張與批次的重試合約，也能避免流程升級後重複建立舊待確認卡片。

### 共用 Schema 降低規則漂移，但 BE 仍是權威

由 Pydantic 匯出 Schema，讓前端即時驗證與後端欄位限制使用同一來源。自訂跨欄位規則需要明確公布到 Schema，不能假設所有 Python validator 都會自動轉換。權限與資料庫狀態則仍只能在後端驗證。

### 批次限制有兩個維度

20 張控制工作量，100,000 bytes 控制輸入大小。多位元組文字與外層 metadata 都會影響大小，因此應計算 UTF-8 bytes，不能只計算 JavaScript 字串長度，也不能只看卡片數量。

### 可重建資料不應阻擋核心寫入

卡片與 review state 是核心資料；embeddings 是可重建的衍生資料。先確認交易，再嘗試產生 embeddings，可以避免外部供應商故障讓新增卡片失敗，但也必須承認程序內工作不保證完成，並保留修復途徑。
