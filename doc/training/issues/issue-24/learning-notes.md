# Issue #24 學習筆記：Review Flow 從 Google Sheets 切換到 FastAPI/PostgreSQL

## 本次完成的內容

這次完成了 Review Flow 從 Google Apps Script／Google Sheets 到 FastAPI／PostgreSQL 的前後端整合。

主要成果包括：

- 前端透過 `GET /v1/reviews/due` 取得待複習卡片。
- 前端透過 `POST /v1/reviews` 提交複習結果。
- Google ID token 只放在 `Authorization` header。
- 每次邏輯提交產生一組 idempotency key。
- 不確定是否成功的請求，使用相同 key 與相同 body 重試。
- 後端負責排程欄位與 review state transition。
- 前端只提交使用者的答案意圖與 `expected_version`。
- 保留翻卡後才能回答、四種答案、進度與成功畫面。
- Review runtime 不再呼叫 Google Apps Script，也沒有 fallback 或 dual write。
- 加入 CORS、錯誤狀態、卡片高度與匯入欄位顯示的修正。

## 前後端責任邊界

### Typed API client

Typed API client 負責 transport 與 protocol concerns：

- 組合 API URL。
- 把 Google ID token 放進 `Authorization` header。
- 設定 `Content-Type` 與 `Idempotency-Key`。
- 解析 JSON。
- 驗證成功與錯誤 response shape。
- 將 HTTP、network、authentication 和 invalid response 轉成統一錯誤。
- 不自行決定產品畫面。
- 不自動重試 review submission。

### Review page

Review page 負責 product 與 UX concerns：

- 顯示 loading、empty、reviewing、submitting、success 等狀態。
- 決定錯誤訊息與使用者可以採取的 recovery action。
- 管理目前答案與 pending submission。
- 只有收到並驗證成功 response 後才顯示成功。
- 在 `409` 時丟棄過期 command，重新取得目前資料。
- 在 retryable failure 時保留原始 command，讓使用者手動重試。

### SwipeCards component

`SwipeCards` 只負責 review interaction：

- 顯示卡片內容。
- 保留 flip-before-answer。
- 處理 swipe 與 yes/no action buttons。
- 回傳：

```ts
{
  (card_id, decision, expected_version);
}
```

它不再計算 `review_stage`、`ease_factor`、`interval_days` 或下一次複習時間。

### Backend

FastAPI/PostgreSQL 負責：

- 驗證 Google ID token。
- 建立或取得內部 user identity。
- 檢查資料 ownership。
- 驗證 request。
- 鎖定 review state。
- 檢查 `expected_version`。
- 計算新的 review schedule。
- 在同一個 transaction 寫入 batch、events 和 current states。
- 處理 idempotent replay。
- 避免跨帳號存取或覆寫 stale state。

## Authentication 與信任邊界

Google Identity Services 負責讓使用者登入並取得 Google ID token，但前端解析 token 只能作為 UX
與本機資料隔離用途，不能作為真正的安全驗證。

真正的 identity 與 authorization 必須由後端完成。

目前沒有建立自訂 backend session，也沒有把 Google token 換成另一組 access token。每次 protected
API request 都直接攜帶目前有效的 Google ID token：

```http
Authorization: Bearer <Google ID token>
```

後端會驗證 signature、issuer、audience、expiration、verified email 和 Google subject。

這次也釐清了：

- Google 登入不等於後端已經驗證成功。
- 第一個 protected API request 才會真正通過後端 authentication。
- `GET /v1/me` 可以作為額外確認，但不是這張 ticket 必須新增的 login flow。
- 前端 email whitelist 不是安全邊界。
- 跨帳號資料保護仍然要依靠後端 token verification 和 owner-scoped SQL。

## Idempotency lifecycle

一個 logical review submission 只會建立一組 idempotency key，並將 key、body、Google subject、建立時間
和 expiration 一起存進 `localStorage`。

Pending command 的有效期是 24 小時。

不同結果的處理方式如下：

- Network failure、timeout、`503` 或 invalid response：保留相同 key 與相同 body。
- `401`：清除 authentication state，但保留同一使用者的 pending command；重新登入後仍使用原 key
  和 body。
- `409`：代表 command 已經不適合繼續提交，因此 retire 舊 key，重新取得 due state。
- `400`、`404`、`422`：屬於確定拒絕，清除 pending command。
- 成功：清除 pending key 與 body。
- 切換 Google 帳號：清除前一個帳號的 pending command。
- Pending command 超過 24 小時：清除並重新開始 review。

重要原則是：不確定結果時不能產生新 key，否則同一個使用者操作可能被當成兩次不同 command。

## Optimistic concurrency 與 stale recovery

每張 due card 都包含 `review_state.version`。

前端提交時把它當成 `expected_version` 傳給後端。後端會在 transaction 中重新檢查版本。

如果版本已經改變，API 回傳 `409 stale_review_state`，整個 batch 不寫入任何結果。

這次選擇較簡單、安全的 recovery：

- 不嘗試保留部分成功答案。
- 不把舊答案複製到新 idempotency key。
- 告知使用者這次沒有儲存。
- 重新取得目前 due cards。
- 讓使用者根據最新內容重新回答。

這避免了 mixed batch reconciliation 和偷偷覆寫新狀態的風險。

## Error 與成功邊界

前端不能因為使用者按下 Submit 就顯示成功。

只有以下條件全部成立才顯示成功：

1. API 回傳成功 HTTP status。
2. Response body 是可解析的 JSON。
3. Response 符合完整 `ReviewResult` contract。
4. Pending command 已經被確認完成。

對於 network error、invalid response、`401`、`409`、validation error、not found 和 unexpected
server error，前端都有不同的畫面與 recovery 行為。

失敗或不確定的 write 不會被呈現為成功。

## CORS 邊界

實際串接時遇到 `OPTIONS /v1/reviews/due` 回傳 `405`。

原因是含有 `Authorization` header 的跨來源 request 會先觸發 browser preflight。當時 FastAPI 沒有
CORS middleware，因此 browser 不會送出真正的 `GET`。

後來加入了可設定的 `CORS_ALLOWED_ORIGINS`：

- 只接受明確的 HTTP／HTTPS origins。
- 不允許 wildcard。
- 允許 `GET` 和 `POST`。
- 允許 `Authorization`、`Content-Type` 和 `Idempotency-Key`。
- 對瀏覽器 expose `X-Request-ID`。
- 不啟用 cookie credentials。
- Production 必須提供明確 origin，不能沿用 local default。

`ConfiguredCORSMiddleware` 等到 lifespan 載入設定後，再建立 Starlette `CORSMiddleware`。

Preflight request 由 CORS middleware 直接處理，不會進入 router；一般 request 則會繼續進入
request-ID middleware、authentication dependency 和 router。

## UI compatibility

### Card height

實際瀏覽器測試發現 `.swipe--cards` 只有約 40px 高。

原因是：

- `.swipe` 使用 `height: 100%`。
- Parent 沒有 definite height。
- `.swipe--card` 使用 percentage height。
- Cards 是 `position: absolute`，不會撐高 parent。
- 最後 parent 只剩 `padding-top: 40px` 的高度。

修正後建立完整的 definite-height flex chain：

```text
review page: 100dvh
→ reviewing wrapper: h-full
→ SwipeCards: flex: 1
→ cards container: flex: 1
→ card: height: 100%, max-height: 600px
```

另外把 `width: 100vw` 改為 `width: 100%`，避免超出 page padding。

### Imported card fields

匯入資料會把不在 canonical enum 裡的 legacy type 保存成：

```json
{
  "part_of_speech": "other",
  "part_of_speech_detail": "vocabulary"
}
```

前端原本只顯示 `other`，忽略了保存下來的原始 label。

修正後，如果 canonical value 是 `other` 且有 detail，就顯示 `part_of_speech_detail`，因此使用者會
看到 `vocabulary`，而不是失去資訊的 `other`。

## Cutover 與 rollback 邊界

部署新版前端後，FastAPI/PostgreSQL 會成為唯一的 review runtime。

本次刻意沒有加入：

- Google Apps Script fallback。
- Runtime feature switch。
- Google Sheets dual write。
- 自動把 PostgreSQL review 同步回 Sheets。

Rollback 的方式是重新部署上一版前端。

這代表：

- Rollback 過程可能有短暫 downtime。
- Cutover 後寫入 PostgreSQL 的 review 不會存在 Google Sheets。
- Rollback 後會產生 PostgreSQL／Google Sheets divergence。
- 資料必須保留，之後再用明確的 reconciliation 程序處理。

Production API URL、正式 CORS origin、部署和 post-deployment verification 屬於後續 deployment
milestone。

## 我原本較不熟悉的部分

### Backend login 與 Google sign-in 的差別

一開始不確定是否應該透過 backend 完成 login。後來釐清目前架構不是 backend session flow，而是
Google Identity Services 取得 token，再由 FastAPI 在每次 protected request 驗證。

### CORS preflight

一開始看到的是 CORS error 和 `405`，後來才理解真正失敗的是 browser 自動送出的 `OPTIONS`
preflight，而不是 `GET /v1/reviews/due` 本身不存在。

### FastAPI middleware 註冊方式

這次理解了：

- `app.middleware("http")` 是 function/decorator 形式。
- FastAPI 內部會用 `BaseHTTPMiddleware` 包裝它。
- `app.add_middleware()` 直接註冊 middleware class。
- 後加入的 user middleware 會位在較外層。
- CORS 適合使用 class／ASGI middleware，因為它需要攔截並直接回應 preflight。

### Percentage height 與 flex layout

原本看到 `.swipe--card { height: 90% }`，容易以為它會自然填滿畫面。但 percentage height 必須沿著
parent chain 找到 definite height。

另外，`position: absolute` 的 card 不會撐高 parent。這也是為什麼自動化功能測試通過，實際畫面卻
可能只剩 40px。

### Idempotency key 的生命週期

這次更具體理解 idempotency key 不是「每次 HTTP request 一個 key」，而是「每個 logical command
一個 key」。

只要結果仍然 ambiguous，就必須保留相同 key 和相同 body。

### Client storage 與安全邊界

在 `localStorage` 儲存 Google subject 可以避免帳號切換時顯示前一個帳號的 pending data，但這只是
client-side privacy boundary。

它不能代替後端 authentication、ownership check 或 database authorization。

## What we've learned

1. 前端應該提交使用者意圖，而不是提交自己計算出的 authoritative state。
2. Typed API client 應該處理 transport 和 protocol；page 應該處理產品狀態與 recovery UX。
3. Idempotency 的單位是 logical command，不是 network attempt。
4. 對 ambiguous write，正確狀態是「尚未確認」，不是成功，也不是立即建立新 command。
5. Optimistic concurrency 不只是回傳 `409`，還需要設計清楚、可理解的使用者 recovery。
6. Client-side identity marker 能保護畫面隱私，但真正的 ownership 必須由後端強制執行。
7. CORS 是 browser security boundary。API 可以被 `curl` 呼叫，不代表 browser 一定能呼叫。
8. Mock browser tests 很適合覆蓋 deterministic error states，但不能完全取代真實 browser、FastAPI、
   Google token 和 PostgreSQL 的整合驗證。
9. CSS percentage height 依賴完整的 definite-height chain；absolute children 不會決定 parent height。
10. Cutover 不只是換 endpoint，也需要明確定義 runtime authority、fallback policy、rollback downtime
    和資料 divergence。

## 驗證結果

- Frontend contract/state/component tests：11 passed
- Playwright Chrome tests：10 passed
- Svelte check：0 errors，3 個既有 footer CSS warnings
- Targeted ESLint：passed
- Backend Ruff／format／lock checks：passed
- PostgreSQL-backed backend tests：231 passed
- Real local CORS preflight：passed
- Live Google-authenticated review：10 cards successfully submitted
- PostgreSQL verification：
  - 1 review batch
  - 10 review events
  - 10 distinct cards
  - 10 current states matching their recorded `srs-v1` results

## 尚未完成的範圍

- Remote CI verification
- Production API configuration
- Production CORS origin
- Production deployment
- Post-deployment verification
- Production rollback exercise

這些項目屬於後續 deployment milestone，不應被描述成本次已完成的 production evidence。
