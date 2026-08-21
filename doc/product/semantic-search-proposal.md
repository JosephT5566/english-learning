# Semantic Search Prototype Proposal

## 1. 文件資訊

- 狀態：Deferred proposal
- 文件語言：繁體中文
- 目標讀者：負責實作此功能的工程師或 coding agent
- 專案：English Learning
- 第一版定位：小型、可驗證搜尋品質的原型

## 2. 背景與目標

目前專案是部署於 GitHub Pages 的 SvelteKit 靜態應用，透過 Google Apps Script 讀取與更新 Google Sheets 中的英語學習資料。現有功能以複習流程為主，尚未提供依語意尋找單字、片語、解釋或例句的能力。

本提案的目標是：

> 以 Google Sheets 作為原始資料來源，在現有英語學習專案中建立一套使用 JSON 儲存 embeddings 的小型 Semantic Search 原型，支援使用者以中文或英文查詢相關學習內容。

此原型的主要目的，是先驗證 semantic search 對目前學習資料的實際價值與搜尋品質，再決定是否遷移至 SQLite、PostgreSQL、pgvector 或專用 Vector DB。

## 3. 成功標準

第一版須符合以下條件：

1. 管理員可以手動將指定 Google Sheet 範圍同步成私有的 `embeddings.json`。
2. 同步只為新增或內容已改變的項目重新產生 embedding。
3. 登入且位於使用者白名單的使用者，可以輸入中文或英文查詢。
4. 搜尋固定回傳 cosine similarity 最高的五筆結果。
5. 至少建立 20 個人工標註的測試查詢，其中至少 10 個中文、10 個英文；預期相關項目出現在 Top 5 的比例須達 80%。
6. 在正常索引與網路條件下，95% 搜尋請求須於 5 秒內完成。
7. 新功能不得破壞既有登入、Google Apps Script 更新或 review 流程。

## 4. 範圍

### 4.1 本期包含

- 獨立的 Cloudflare Worker Backend。
- Cloudflare Workers AI embedding。
- 私有 Cloudflare R2 JSON 索引。
- Google Sheets API 與 Service Account 整合。
- 受保護的手動同步 API。
- 新增 Svelte `/search` 頁面。
- 恢復全站 Header，提供 Home、Review、Search 導航。
- Google ID token 驗證、email allowlist 與 admin allowlist。
- 依使用者限制搜尋頻率。
- 搜尋、同步、錯誤狀態及搜尋品質測試。

### 4.2 本期不包含

- PostgreSQL、pgvector 或其他 Vector DB。
- SQLite。
- Hybrid search 或 keyword ranking。
- 相似度最低門檻。
- 自動排程同步。
- 搜尋歷史、個人化排序或推薦系統。
- 多租戶與複雜角色管理。
- 超過 1,000 筆資料的效能保證。
- RAG 回答生成或聊天功能。

## 5. 系統架構

```text
┌──────────────────────────────────┐
│ GitHub Pages                     │
│ SvelteKit static frontend        │
│                                  │
│ /search                          │
│ Google Identity Services         │
└────────────────┬─────────────────┘
                 │ HTTPS + Google ID token
                 ▼
┌──────────────────────────────────┐
│ Cloudflare Worker                │
│                                  │
│ POST /v1/search                  │
│ POST /v1/admin/sync              │
│ Auth / CORS / rate limiting      │
└───────┬───────────────┬──────────┘
        │               │
        ▼               ▼
┌───────────────┐  ┌──────────────────┐
│ Workers AI    │  │ Private R2       │
│ bge-m3        │  │ embeddings.json  │
└───────────────┘  └──────────────────┘
        ▲
        │ sync only
┌───────┴──────────────────────────┐
│ Google Sheets API               │
│ Service Account, read-only      │
└──────────────────────────────────┘
```

### 5.1 部署邊界

- 前端維持 GitHub Pages、`@sveltejs/adapter-static` 與既有 `BASE_PATH` 行為。
- Backend 為獨立 Cloudflare Worker，不與前端部署在同一服務。
- Production Worker API 僅允許指定的 GitHub Pages origin。
- Local development origin 亦須加入允許清單。
- R2 bucket 不開放公共讀取；所有讀寫均透過 Worker binding。

## 6. 資料來源與索引規格

### 6.1 Google Sheets

- Google Sheets 是唯一的 source of truth。
- Worker 透過 Google Sheets API 讀取資料，不沿用目前 `getList&count=10` 的 Google Apps Script 查詢。
- 存取方式為 Google Service Account server-to-server OAuth。
- 指定 Sheet 必須以唯讀權限分享給 Service Account。
- Sheet ID 與單一 tab 的 A1 range 透過 Worker 環境設定提供，不可硬編於程式碼。
- 第一列是 header，名稱須與現有 `WordItem` 型別一致。
- `id` 與 `content` 為必要欄位。
- 每一列的 `id` 必須唯一。
- Sheet 內所有 `status` 都必須進入索引，包括非 `active` 狀態。
- 若某個 ID 已不在目前 Sheet 範圍內，下一次成功同步時必須從 JSON 移除。

### 6.2 Embedding 文字

每筆資料使用以下欄位建立 `indexedText`：

1. `content`
2. `chineseExplain`
3. `engExplain`
4. `example`
5. `type`
6. `tags`

組合規則：

- 欄位順序固定。
- 去除每個值前後空白。
- 空值欄位不輸出。
- 保留欄位名稱，使模型能區分英文內容、解釋、例句、類型與標籤。
- 不將 review stage、日期、ease factor 或 interval 等複習狀態加入 embedding。

範例：

```text
Content: look forward to
Chinese explanation: 期待
English explanation: to feel pleased and excited about something
Example: I look forward to hearing from you.
Type: phrase
Tags: business, email
```

### 6.3 Embedding 模型

- Provider：Cloudflare Workers AI。
- Model：`@cf/baai/bge-m3`。
- 維度：1024。
- Distance metric：cosine similarity。
- 索引資料與查詢必須使用完全相同的模型。
- 若模型名稱或索引 schema version 改變，所有 embeddings 必須視為失效並重新產生。

### 6.4 Content hash

`contentHash` 使用 SHA-256 計算，輸入至少包含：

```text
schemaVersion + model + indexedText
```

相同 ID 的 hash 未變時，沿用既有 embedding；hash 改變時重新產生。

## 7. R2 JSON Schema

R2 bucket 中使用固定 key：

```text
embeddings.json
```

概念 schema：

```ts
interface EmbeddingIndex {
  schemaVersion: 1;
  model: "@cf/baai/bge-m3";
  dimensions: 1024;
  generatedAt: string; // ISO 8601
  itemCount: number;
  items: EmbeddingItem[];
}

interface EmbeddingItem {
  id: string;
  content: string;
  chineseExplain: string;
  engExplain?: string;
  example?: string;
  type: string;
  tags?: string;
  status?: string;
  indexedText: string;
  contentHash: string;
  embedding: number[]; // exactly 1024 values
}
```

JSON 必須包含顯示搜尋結果所需的完整快照。搜尋時不得再向 Google Sheets 取得個別項目，以免增加延遲與額外失敗點。

## 8. 同步流程

### 8.1 觸發方式

- Endpoint：`POST /v1/admin/sync`。
- 僅登入且位於 admin email allowlist 的使用者可呼叫。
- `/search` 頁面為管理員顯示「同步索引」按鈕。
- Worker 必須再次執行伺服器端授權；隱藏按鈕不能作為安全機制。
- 第一版不提供 cron 排程。

### 8.2 同步步驟

1. 驗證 Google ID token 與管理員權限。
2. 若已有同步進行中，拒絕新同步並回傳 HTTP 409。
3. 從 R2 讀取現有 `embeddings.json`；首次同步時允許不存在。
4. 取得 Google Service Account access token。
5. 從設定的 Sheet ID 與 A1 range 讀取所有列。
6. 驗證 header、必要欄位、欄位格式與 ID 唯一性。
7. 為每列建立 `indexedText` 與 `contentHash`。
8. Hash 未變者沿用既有 embedding。
9. 新增或已變更者透過 Workers AI 產生 embedding。
10. 移除不再存在於 Sheet 的 ID。
11. 驗證所有 embeddings 都是 1024 維有限數字。
12. 在記憶體中建立完整新快照。
13. 僅在以上步驟全部成功後，以單次 R2 `put` 覆寫 `embeddings.json`。

### 8.3 失敗處理

以下任一情況均須使整次同步失敗，且保留舊索引：

- Sheets API 無法存取。
- Sheet schema 不符。
- 缺少 `id` 或 `content`。
- 出現重複 ID。
- Workers AI 呼叫失敗。
- Embedding 維度或內容無效。
- R2 寫入失敗。

錯誤回應須包含可操作的原因；資料列錯誤須包含 Sheet row number，但不得回傳或記錄 Service Account credentials。

### 8.4 成功回應

```json
{
  "data": {
    "total": 120,
    "created": 4,
    "updated": 2,
    "reused": 113,
    "removed": 1,
    "generatedAt": "2026-08-19T10:00:00.000Z"
  }
}
```

## 9. Search API

### 9.1 Request

```http
POST /v1/search
Authorization: Bearer <google-id-token>
Content-Type: application/json
```

```json
{
  "query": "有哪些適合商務信件表達期待的片語？"
}
```

規則：

- `query` 必須是字串。
- 去除前後空白後長度必須介於 1–500 字元。
- 支援中文及英文。
- 每次表單提交只產生一次 query embedding。

### 9.2 搜尋流程

1. 驗證 Google ID token 與使用者 email allowlist。
2. 依已驗證 token 的 `sub` 套用每分鐘 30 次的 rate limit。
3. 驗證 query。
4. 從 R2 讀取並解析 `embeddings.json`。
5. 驗證索引 model、schema version 與 embedding dimensions。
6. 使用 `@cf/baai/bge-m3` 產生 query embedding。
7. 對所有項目計算 cosine similarity。
8. 依 similarity 由高至低排序。
9. 固定回傳前五筆；不使用最低分數門檻。

### 9.3 Success response

```json
{
  "data": {
    "indexGeneratedAt": "2026-08-19T10:00:00.000Z",
    "results": [
      {
        "id": "word-123",
        "score": 0.87,
        "content": "look forward to",
        "chineseExplain": "期待",
        "engExplain": "to feel pleased and excited about something",
        "example": "I look forward to hearing from you.",
        "type": "phrase",
        "tags": "business, email",
        "status": "active"
      }
    ]
  }
}
```

`score` 使用未格式化的原始數值回傳；前端可以格式化顯示，但不得改變排序。

### 9.4 Error response

所有 API 使用一致格式：

```json
{
  "error": {
    "code": "INDEX_NOT_READY",
    "message": "Search index has not been created yet."
  }
}
```

至少定義：

| HTTP | Code               | 情境                                      |
| ---- | ------------------ | ----------------------------------------- |
| 400  | `INVALID_QUERY`    | query 缺少、不是字串、為空或超過 500 字元 |
| 401  | `UNAUTHENTICATED`  | token 缺少、失效或過期                    |
| 403  | `FORBIDDEN`        | email 不在使用者或管理員白名單            |
| 409  | `SYNC_IN_PROGRESS` | 已有同步進行中                            |
| 429  | `RATE_LIMITED`     | 超過每人每分鐘 30 次搜尋                  |
| 500  | `INDEX_INVALID`    | JSON 或 embedding schema 無效             |
| 502  | `UPSTREAM_FAILURE` | Google 或 Workers AI 呼叫失敗             |
| 503  | `INDEX_NOT_READY`  | R2 尚無可搜尋索引                         |

## 10. Authentication and Security

### 10.1 使用者驗證

- 前端沿用 Google Identity Services。
- 前端將 ID token 放在 `Authorization: Bearer` header。
- Worker 必須驗證 JWT signature、issuer、audience、expiry 與 `email_verified`。
- Worker 使用自己的使用者 allowlist；不得信任前端的登入狀態或公開設定。
- Admin endpoint 額外檢查 admin allowlist。
- Rate-limit key 使用已驗證的 Google `sub`，不得使用 client 提供的 email 或 IP。

### 10.2 Secrets 與設定

建議 bindings、variables 與 secrets：

| 名稱                                 | 類型                  | 用途                              |
| ------------------------------------ | --------------------- | --------------------------------- |
| `AI`                                 | Workers AI binding    | 產生 embeddings                   |
| `EMBEDDINGS_BUCKET`                  | R2 binding            | 存取 `embeddings.json`            |
| `SEARCH_RATE_LIMITER`                | Rate Limiting binding | 每人每分鐘 30 次                  |
| `GOOGLE_OAUTH_CLIENT_ID`             | variable              | 驗證 ID token audience            |
| `GOOGLE_SHEET_ID`                    | variable              | 指定來源 spreadsheet              |
| `GOOGLE_SHEET_RANGE`                 | variable              | 指定單一 tab 與 A1 range          |
| `ALLOWED_EMAILS`                     | secret                | 可搜尋的 email allowlist          |
| `ADMIN_EMAILS`                       | secret                | 可同步的管理員 allowlist          |
| `GOOGLE_SERVICE_ACCOUNT_EMAIL`       | secret                | Sheets API Service Account        |
| `GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY` | secret                | 簽署 Service Account JWT          |
| `ALLOWED_ORIGINS`                    | variable              | GitHub Pages 與 localhost origins |

不得將 Service Account JSON、private key、allowlists 或實際 Sheet ID 提交至 Git。

### 10.3 CORS

- 僅回傳符合 `ALLOWED_ORIGINS` 的 `Access-Control-Allow-Origin`。
- 支援 production GitHub Pages origin 與指定 localhost development origin。
- 處理 `OPTIONS` preflight。
- 允許 `Authorization` 與 `Content-Type` headers。
- 不使用 `Access-Control-Allow-Origin: *`。

## 11. Frontend Requirements

### 11.1 Header

- 恢復現有 `Header.svelte`。
- 顯示 Home、Review、Search。
- 所有連結必須使用 SvelteKit base path utilities，維持 GitHub Pages `BASE_PATH` 相容性。
- 正確標示目前所在頁面。

### 11.2 Search page

`/search` 僅允許已登入使用者使用，並包含：

- 1–500 字元搜尋輸入。
- Search 按鈕。
- Enter 提交。
- 搜尋期間 loading 狀態。
- Top 5 結果列表。
- 每筆結果的核心內容、解釋、例句、type、tags、status 與 similarity score。
- 最近一次成功索引時間。
- 明確的空結果、索引未建立、登入過期、rate limit、網路與服務錯誤訊息。
- 發生錯誤時保留原查詢並提供重試。
- 不使用輸入 debounce；只有表單提交才呼叫 API。

### 11.3 Admin sync control

- 僅對管理員顯示同步按鈕。
- 同步期間停用按鈕並顯示進度狀態。
- 成功後顯示 created、updated、reused、removed 與 generated time。
- 失敗後顯示可操作訊息，不將失敗誤呈現為空搜尋結果。
- Worker 仍須獨立驗證管理員權限。

## 12. Privacy and Observability

Production logs 不得包含：

- 原始搜尋文字。
- Google ID token。
- Service Account access token 或 private key。
- 完整 embeddings。

可記錄：

- Request ID。
- 匿名化或不可逆處理的 user identifier。
- Endpoint、status code 與 error code。
- 搜尋耗時與結果數量。
- 同步 created、updated、reused、removed 統計。
- Workers AI、Sheets API 與 R2 操作耗時。
- Rate-limit event。

## 13. Non-functional Requirements

- 預期資料量：1,000 筆以下。
- 搜尋延遲：95% 請求低於 5 秒。
- 同步必須具備 all-or-nothing 行為。
- 搜尋服務在同步失敗時繼續使用上一版成功索引。
- Worker 不得將完整 JSON 或 embeddings 回傳給前端。
- 搜尋結果只能包含 API contract 列出的顯示欄位。
- 所有時間使用 ISO 8601 UTC。
- 所有程式碼與 API contract 使用 TypeScript 型別。

## 14. Test Plan

### 14.1 Unit tests

- Sheet header 與 row parsing。
- `indexedText` 欄位順序、空值與 trimming。
- `contentHash` 穩定性。
- 模型或 schema version 改變時 hash 改變。
- Cosine similarity 與排序。
- Top 5 截取。
- Query 長度驗證。
- Google ID token claims 與 allowlist 判斷。
- Admin 權限與 rate-limit key。

### 14.2 Sync integration tests

- 首次同步建立 JSON。
- 未變更項目沿用 embedding。
- 新增項目產生 embedding。
- 修改核心索引欄位重新產生 embedding。
- 修改非索引欄位不重新產生 embedding，但更新顯示快照。
- 所有 status 均保留。
- Sheet 實體刪除後從索引移除。
- 缺少必要欄位時拒絕同步。
- 重複 ID 時拒絕同步。
- Workers AI 中途失敗時保留舊索引。
- R2 寫入失敗時保留舊索引。
- 並行同步回傳 409。

### 14.3 Search API tests

- 中文查詢。
- 英文查詢。
- Top 5 排序正確。
- 少於五筆資料時回傳所有可用結果。
- R2 索引不存在、格式錯誤或 model 不符。
- Token 缺少、過期、audience 不符與 email 不在白名單。
- 第 31 次同分鐘搜尋回傳 429。
- CORS production、localhost 及不允許 origin。
- Workers AI 失敗時回傳一致錯誤格式。

### 14.4 Frontend tests

- Header navigation 與 GitHub Pages base path。
- 未登入時的 redirect 或登入提示。
- 空查詢與超長查詢。
- Loading、success、empty、error 與 retry 狀態。
- 登入過期時提示重新登入。
- 非管理員不顯示同步按鈕。
- 管理員可以觸發同步並看到摘要。

### 14.5 Search quality evaluation

- 建立至少 20 個固定測試案例。
- 至少 10 個中文查詢、10 個英文查詢。
- 每題指定一個或多個可接受的相關 `id`。
- 若至少一個可接受 ID 出現在 Top 5，該題視為通過。
- 通過率必須至少 80%。
- 測試集應涵蓋單字、片語、中文含義、英文解釋、例句情境、type 與 tags。
- 模型、`indexedText` 格式或資料集有重大變更時須重新執行品質評估。

## 15. Rollout

1. 建立 Cloudflare Worker、AI binding、私有 R2 bucket 與 rate-limit binding。
2. 建立 Google Service Account、啟用 Sheets API，並將指定 Sheet 以唯讀權限分享給 Service Account。
3. 設定 production 與 local development variables/secrets。
4. 部署 Worker 並驗證 auth、CORS 與空索引錯誤。
5. 使用管理員按鈕執行首次同步。
6. 執行 API、前端與 20 題搜尋品質測試。
7. 確認 80% Top 5 命中率與 95% 低於 5 秒。
8. 將 Search 導航開放給使用者白名單。

## 16. 後續評估條件

出現以下任一情況時，重新評估 JSON brute-force 方案：

- 資料量接近或超過 1,000 筆且延遲目標無法維持。
- R2 JSON 大小造成明顯解析或 Worker 記憶體壓力。
- 需要複雜 metadata filtering。
- 需要更高頻率或多人同時同步。
- 需要 hybrid search、近似最近鄰索引或高可用資料庫。

下一階段候選方案為 SQLite、PostgreSQL + pgvector 或 Cloudflare Vectorize；是否遷移須以本原型的搜尋品質、延遲與實際使用情況決定。

## 17. References

- [Cloudflare Workers AI bindings](https://developers.cloudflare.com/workers-ai/configuration/bindings/)
- [Cloudflare bge-m3 model](https://developers.cloudflare.com/workers-ai/models/bge-m3/)
- [Cloudflare R2 Workers API](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/)
- [Cloudflare Workers Rate Limiting](https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/)
- [Google OAuth 2.0 for server-to-server applications](https://developers.google.com/identity/protocols/oauth2/service-account)
