# Issue #25 學習筆記：雙語 Deck／Card 管理與 Frontend Database Cutover

## 這張 ticket 的背景

Issue #25 的重點比前幾張 ticket 更偏向 frontend。前面的工作已經建立 FastAPI、PostgreSQL、Google
token verification、ownership、deck/card read API，以及 review flow 的 database cutover。這張 ticket
要把這些 backend 能力真正組成使用者可以操作的管理頁面，並補上 create、edit、archive 所缺少的
contract 與 recovery 行為。

這次並不是另外製作一套 Japanese application，而是讓 English 和 Japanese 共用相同的 route、API
client、domain model 與 UI components。語言差異只存在於 query state、顯示文字，以及少數
language-specific fields。

本機實作與驗證已完成；production API、正式 CORS、remote CI、deployment 與 deployed network
verification 仍需要透過 Issue #26 完成。因此這份筆記描述的是已驗證的 project/local evidence，不把它
寫成正式 production 經驗。

## 我們完成了哪些頁面

### `/decks?language=en|ja`

這是 English 和 Japanese 共用的 deck list page。

如果使用者進入 `/decks` 而沒有提供 `language`，前端會把 URL canonicalize 成
`/decks?language=en`。這讓 English default 不只是程式內的隱藏預設，而是會清楚反映在 URL，重新整理
或分享連結時也能得到相同狀態。

這個頁面包含：

- English／Japanese language tabs。
- Active／Archived filters。
- Deck list、loading、empty 與 error states。
- Pagination。
- 建立 deck 的 drawer。
- 編輯 deck 的 drawer。
- Archive confirmation。

不支援的語言值會顯示 validation state，而且不會先送出錯誤的 API request。

### `/decks/[deckId]?language=en|ja`

這是 deck detail 與 card list page。它會顯示目前 deck 的資料，以及屬於這個 deck 的 cards。

除了 card list、active/archive filtering、pagination 和 read failure states，這個頁面也提供較寬的
card-create drawer。新增 card 時，`learned_on` 會預設成 browser local date 的今天，使用者仍可在送出
前修改。

### `/cards/[cardId]?language=en|ja`

這是 card detail 與 edit page。English card 顯示 pronunciation；Japanese card 才顯示 reading 和
romanization。這些差異是同一個 card model 上的 conditional presentation，不是不同資料表、不同 API
或不同 component tree。

Card edit 放在 detail page 上，讓使用者能同時看到完整內容、目前 version 與 edit result。Archive
同樣需要 explicit confirmation。

## 共用雙語 UI 的策略

我們選擇用 `language=en|ja` query parameter 表示目前管理的 target language，而不是建立
`/english/decks` 和 `/japanese/decks` 兩套 route。

這個策略帶來幾個好處：

- Route family、API calls、loading/error logic 和 tests 可以共用。
- 新增其他語言時，不必先複製整套 application。
- Backend ownership 和 validation 不會因語言分成兩套規則。
- 語言差異集中在 field visibility 和 copy，比較容易檢查 contract drift。

Frontend 仍會把目前 language 傳給 list API，但不能把它當作 authorization boundary。使用者是否能讀寫
某個 deck/card，仍然由 backend 根據已驗證的 Google identity 和 owner-scoped query 決定。

## Frontend 與 Backend 的責任分工

### Frontend 負責

- URL 與 language/filter state。
- Loading、empty、success、validation、conflict、retryable 與 unknown outcome UI。
- 決定哪些欄位應該對 English 或 Japanese 顯示。
- 保存尚未確認結果的 create command。
- 在 stale edit 時保留表單內容，讓使用者決定是否 discard。
- 只有 response 通過 HTTP 與 runtime contract validation 後才顯示成功。

### Backend 負責

- 驗證 Google ID token，而不是信任前端解析出的 email。
- 從 verified identity 決定目前 user。
- 在所有 deck/card queries 中 enforce ownership。
- 驗證 create/edit payload。
- 使用 transaction 保護 card creation 與 initial review state。
- 檢查 optimistic version。
- 保存 idempotency key 與 normalized request hash。
- 決定 request 是 exact replay、stale conflict、validation failure 或 authorization failure。

Frontend 的 ownership check 只能改善 UX；真正的資料隔離必須留在 backend。

## 我們如何使用 Backend API

Frontend 透過統一的 typed API client 呼叫 FastAPI。Client 負責：

- 正確組合 `PUBLIC_API_BASE_URL` 與 `/v1` route。
- 將 Google ID token 放在 `Authorization: Bearer ...` header。
- 在 create request 加入 `Idempotency-Key`。
- 解析 success response 和統一 error envelope。
- 把 network、HTTP、authentication、conflict 與 invalid JSON 轉成可辨識的 client error。

Page 和 feature components 不需要自己重複處理 `fetch` protocol，也不應直接依賴 Google Apps Script 的
response shape。

## 為了 Frontend Flow 補完的 Backend 功能

雖然這張 ticket 以 frontend 為主，實際串接 create/edit/archive 時，仍需要補完整 backend contract。

### Deck／Card create idempotency

Deck 和 card creation 現在都要求 UUID `Idempotency-Key`。Backend 會對 validated、normalized、帶有
版本的 request content 計算 hash，並利用既有的 per-owner unique boundary 儲存 key 與 hash。

結果分成：

- 相同 owner、相同 key、相同內容：回傳原本已建立的 resource。
- 相同 owner、相同 key、不同內容：回傳 `409 idempotency_key_reused`。
- 不同 owner 使用相同 key：各自在自己的 ownership boundary 內處理。

Card create 和 initial review state 位於同一個 transaction。Exact replay 不會多建立一張 card，也不會
多建立一筆 review state。

### CORS methods

原本 review flow 主要需要 `GET` 和 `POST`。Management edit/archive 加入後，browser 還需要
`PATCH` 和 `DELETE` 的 preflight permission。

我們只擴充實際需要的 methods，仍然維持：

- Exact configured origins。
- 不使用 wildcard。
- 不啟用 credentialed cookies。
- 只允許既有的 authorization、content type 與 idempotency headers。

## Generated OpenAPI TypeScript 與 runtime validation

這次選擇把 FastAPI OpenAPI schema deterministic export 到 repository，再使用 `openapi-typescript` 產生
checked-in TypeScript types。

資料流是：

```text
FastAPI request/response models
→ apps/api/openapi.json
→ src/lib/api/generated.ts
→ typed API client 和 management UI
```

CI 會重新產生這兩個 artifacts 並檢查 diff。如果 backend contract 改變、frontend generated types 卻沒有
更新，CI 會失敗，避免 contract drift 被帶進後續修改。

Generated TypeScript 只能在 compile time 幫助開發，不能證明真實 network response 一定正確。因此 API
client 仍保留 runtime guards。即使 TypeScript 認為資料是某個 type，malformed JSON 或舊版 server
response 仍會被視為 invalid response，而不會直接進入 UI。

## Create 的 unknown outcome 與安全重試

Create request 最麻煩的情況不是明確成功或明確失敗，而是 response 不清楚，例如：

- Network 中斷。
- Request timeout。
- Server 可能已 commit，但 browser 沒收到 response。
- Response 是成功 status，但 body 無法通過 contract validation。

此時前端不能顯示成功，也不能直接建立新的 idempotency key 重送，否則同一個使用者操作可能變成兩個
resource。

我們將一個 logical create command 的 key、exact body、Google subject 與 expiration 保存 24 小時。只要
結果仍然 unclear，重試就必須使用相同 key 和相同 body，表單內容也會先鎖住。使用者如果要改內容，必須
先放棄舊 command，再建立新的 logical command。

這個 local storage 不是 security boundary。Backend 仍然要以 verified owner、idempotency key 和 request
hash 決定 replay 是否有效。

## Edit 的 optimistic concurrency 與 stale recovery

Deck/card response 帶有 `version`，edit request 則帶 `expected_version`。Backend 只在目前 version 符合時
套用更新。

如果另一個 request 已先修改資料，backend 會回傳 stale conflict。這次沒有選擇自動覆蓋或 blind retry，
因為舊表單可能會覆寫較新的內容。

Frontend 的 recovery 是：

1. 保留使用者目前輸入的內容。
2. 明確告知資料已經變更。
3. 提供「Reload latest and discard my changes」。
4. 只有使用者確認後才重新讀取 server state，並捨棄舊表單。

這也符合我們討論的策略：不做複雜 merge，直接讓使用者重新取得最新資料再編輯，但 discard 必須是明確
操作，不能在收到 `409` 時偷偷清空輸入。

## Archive 的 ambiguous result

Archive request 也可能遇到「server 已完成，但 response 遺失」的情況。因為 archive 沒有像 create 一樣
產生新 resource，所以我們使用 follow-up read 進行 reconciliation。

- 如果 read 證明 `archived_at` 已存在，UI 才顯示 archive 成功。
- 如果 resource 仍是 active，保留 failure/unknown state。
- 如果 follow-up read 也不清楚，就不能假裝成功。

核心原則是：使用者按下按鈕不代表 mutation 成功；只有 server response 或 reconciliation evidence 才能
讓 UI 進入 confirmed success。

## Loading 與 error state 的設計

Read flow 明確區分：

- Loading：等待 response，先顯示可辨認的 loading state。
- Empty：request 成功，但沒有符合 filter 的資料。
- Validation：例如不支援的 language，不發 request。
- Unauthenticated：token 不存在、過期或 backend 拒絕。
- Not found／forbidden：使用不洩漏 ownership 的一致呈現。
- Retryable：暫時性 network、database 或 server problem，可讓使用者重試。
- Invalid response：HTTP 可能成功，但資料 contract 不可信。
- Server error：無法由 frontend 自行修正的錯誤。

這些狀態不能只共用一句「Something went wrong」，因為 recovery action 不同。Loading 也不能被當成
empty，否則使用者會在資料尚未回來時看到錯誤的「沒有資料」。

## shadcn-svelte 與 Bits UI 的選擇

一開始 management drawer 和 confirmation overlay 是較手工的實作。後來我們加入 shadcn-svelte 的
Sheet 和 Alert Dialog，底層仍保留 Bits UI。

這個選擇不是單純為了外觀，而是共用成熟的 accessible interaction：

- Focus trapping。
- Escape dismissal。
- Portal rendering。
- Background scroll locking。
- Dialog roles 與 ARIA semantics。

Repository 再用自己的 `Drawer` 和 `ConfirmDialog` 包住這些 primitive，保留既有 visual style 和
feature-facing API。這讓產品頁面不用直接知道 Bits UI 的細節，也沒有因導入 library 而進行整體 redesign。

## Static deployment 與 base path

Frontend 使用 `adapter-static` 部署到 GitHub Pages 類型的 subpath，因此 internal navigation 不能假設網站
永遠位於 `/`。新增 routes 和 CTA 都必須保持 `paths.base` compatibility，並透過 SvelteKit 的
base-aware URL resolution 建立 internal links。

Production-style build 使用 `BASE_PATH=/english-learning` 驗證，確保新增的 deck/card pages 不會只在
localhost root path 正常。

## Apps Script runtime cutover

完成 read/write flow 後，我們移除了 CI 和 GitHub Pages deployment 中的 `PUBLIC_APP_SCRIPT_URL`。
保留的 legacy Sheet wrapper 不再從 ambient environment 取得 endpoint；如果真的要使用，caller 必須明確
inject endpoint，而且 normal runtime modules 不會 import 它。

這裏發現一個容易忽略的 SvelteKit 行為：即使 application code 沒有使用某個 `PUBLIC_` variable，build
process 仍可能把 public environment values 放進 browser artifact。因此只刪除 import 不夠，還必須從
build environment 移除 Apps Script URL，並掃描生成的 static artifact。

Deployment 現在會檢查 `PUBLIC_API_BASE_URL`：必須存在、使用 HTTPS，且不能包含 credentials、query 或
fragment。這個 gate 避免 production build 在 API base 缺失時仍被部署。

## Cutover 的順序與 rollback 邊界

這次採用 read-before-write 的 cutover：

1. 先讓 deck/card list 和 detail reads 使用 FastAPI。
2. 驗證雙語欄位、ownership、not-found、loading、pagination 與 network traffic。
3. 補上 backend create idempotency contract。
4. 再開放 create、edit、archive UI。
5. 驗證 mutation failure、stale conflict 和 ambiguous result。
6. 最後移除 Apps Script runtime configuration。

先切 read 的理由是：read 有問題時不會新增或改寫資料，風險比 write 小。確認資料顯示、language filtering
與 authorization boundary 正確後，再進入 mutation cutover。

這次沒有 automatic fallback，也沒有 PostgreSQL／Google Sheets dual write。Production 出現第一筆只寫入
PostgreSQL 的 mutation 後，Sheet 就不再是最新 source of truth。若回到 legacy frontend，必須先停止寫入並
做 explicit reconciliation，否則會隱藏或覆寫 PostgreSQL-only changes。

## 我原本較不熟悉的部分

### 一套 UI 如何支援多語言 domain

一開始容易把 English 和 Japanese 想成不同頁面。這次比較具體理解：語言可以是 domain data 和 query
state，而 route、authorization、API client、components 與 database model 仍然共用。只有確實不同的
fields 才 conditional render。

### Generated types 不等於 runtime safety

以前可能會覺得 TypeScript type 已經足夠。這次理解 OpenAPI-generated types 解決的是 compile-time
contract drift，而 runtime guard 解決的是 server、proxy 或 malformed JSON 在執行時不符合預期。兩者不是
互相替代。

### Idempotency 不只是「加一個 header」

真正的 idempotency 需要定義 logical command lifecycle、key ownership、request hash、exact replay、
different-content conflict，以及 unclear response 後如何保存原始 command。Frontend 和 backend 必須共同
遵守同一個 protocol。

### 明確失敗與不確定結果不同

`422` validation failure 可以確定資料沒有被接受；network timeout 卻不能證明 server 沒有 commit。這兩種
failure 不能使用相同 recovery。Unknown outcome 需要 replay 或 reconciliation，UI 也不能直接顯示成功或
清除所有 state。

### Optimistic version 的 UX

Backend 回傳 `409` 只是 concurrency control 的一半。Frontend 還要決定是否保留輸入、如何解釋 conflict，
以及何時允許 discard。這次選擇 explicit reload，讓資料一致性優先於自動 merge 的便利性。

### Accessible drawer/dialog 的完整行為

Modal UI 不只是畫出 fixed overlay。Keyboard focus、Escape、portal、scroll lock、ARIA 和 nested interaction
都容易遺漏。使用 shadcn-svelte 加 Bits UI 可以共用這些 primitive，但仍需要 project-level wrapper 來維持
一致的 feature contract。

### Public build environment 也是 runtime contract

Frontend static build 會把 `PUBLIC_` variables 交給 browser，因此 CI/deployment variables 不是單純 DevOps
設定，而是 application runtime contract。Cutover verification 也必須檢查 build artifact，而不只搜尋 source
imports。

## 我學到了哪些

### 1. Full-stack feature 的完成不只是一張新頁面

一個管理頁面會牽涉 API contract、authentication、ownership、database transaction、concurrency、retry、
CORS、static routing、accessibility 與 deployment configuration。Frontend 是使用者看到的部分，但安全與
一致性必須由整條 request path 一起保證。

### 2. Shared multilingual design 的核心是共用規則

真正可維護的 multilingual application，不是複製兩套 UI，而是讓語言成為明確資料，並讓相同 ownership、
validation、pagination、error handling 和 component behavior 套用到所有語言。

### 3. 只有被確認的 mutation 才能顯示成功

HTTP request 已送出不代表操作完成。Create 可以使用 idempotent replay，archive 可以 follow-up read，edit
可以透過 optimistic version 阻止 stale overwrite。不同 mutation 需要不同 recovery，但共同原則是沒有證據
就不能顯示成功。

### 4. Contract safety 有 compile-time 和 runtime 兩層

OpenAPI generation 讓 backend contract change 可以在 CI 被發現；runtime guards 則保護實際 network
boundary。保留兩層檢查，比完全手寫 types 或完全相信 generated types 更可靠。

### 5. Cutover 必須先定義資料何時開始分歧

Rollback 不是「切回舊網址」這麼簡單。一旦 PostgreSQL 收到 Sheets 沒有的 writes，legacy system 就已經
stale。正確的 rollback 文件必須說明 safe window、停止寫入、資料 reconciliation，以及不能自動 fallback
的原因。

### 6. Automated browser test 也可以驗證架構邊界

Playwright 不只測按鈕能不能點。這次也用它檢查 bilingual navigation、failure recovery、keyboard
interaction，以及 normal review/management flows 的 network requests 是否只前往 FastAPI、沒有呼叫 Apps
Script。

## 驗證結果與目前限制

本機驗證包含：

- Svelte／TypeScript check：零 errors 和 warnings。
- Frontend contract、state、component 與 runtime-configuration tests：20 passed。
- Critical Playwright Chrome flows：28 passed。
- PostgreSQL-backed backend suite 在 Part 2 checkpoint：236 passed。
- Static production build with `BASE_PATH=/english-learning`：passed。
- Generated OpenAPI contract check：passed。
- Normal review/management network trace：只有 configured FastAPI `/v1` traffic，沒有 Apps Script request。
- Generated static artifact：沒有 Apps Script variable、host 或 endpoint fragment。

目前仍未驗證：

- Production API host 與 managed PostgreSQL。
- 正式 GitHub Pages origin 的 CORS 設定。
- Remote CI 與 deployed static build。
- Production Google authentication、owned read 與 mutation。
- 第一筆 production PostgreSQL-only write 的實際時間。
- Production rollback rehearsal。

這些限制會由 Issue #26 的 deployment work 繼續處理；在完成前，Issue #25 可以說「local implementation
and verification complete」，但不能宣稱 production cutover 已完成。
