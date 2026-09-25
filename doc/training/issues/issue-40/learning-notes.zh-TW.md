# Issue #40 學習筆記：具所有權邊界的語意單字搜尋

更新日期：2026-09-25

## 1. 這個 ticket 解決了什麼問題

Issue #40 把 Issue #38 的 retrieval 設計與 Issue #39 已儲存的 card embeddings，接成一條可由
使用者操作的搜尋流程：登入後輸入一段意思或概念，後端將 query 轉成 embedding，再從該使用者
自己的有效單字卡中找出語意最接近的 Top-K 結果。

這不是 chatbot，也不是讓模型產生 SQL。結構化問題仍走既有 SQL API；semantic search 只負責
以 vector distance 排列已經通過 SQL 授權與 eligibility predicates 的 rows。

核心安全原則是：**vector 只負責 ranking，不負責 authorization。** Browser 不能傳入
`owner_id`，所有權只來自後端驗證 Google bearer token 後取得的 internal user ID。

## 2. 完成的後端功能

新增 `POST /v1/cards/semantic-search`：

- query 先做 NFC normalization 與 trim，長度限制為 2 到 500 字元。
- `limit` 預設 10，限制為 1 到 20。
- MVP 僅接受 English target language，並可選擇一個 owned `deck_id`。
- Request schema 禁止額外欄位，避免把未定義的 client input 當成搜尋控制條件。
- Authentication 與 request validation 通過後，每個 request 只呼叫一次 Vertex
  `RETRIEVAL_QUERY` embedding。
- Provider timeout、rate limit 或 unavailable 會回傳安全的 retryable 503；不會偽裝成成功但
  沒結果。
- Database failure 使用既有安全 error envelope，不洩漏 SQL、credentials 或 private content。

Top-K SQL 在排序與 `LIMIT` 前套用：

- authenticated card owner；
- authenticated deck owner；
- active card 與 active deck；
- target language 與可選 deck；
- active embedding model version；
- `ready` state 與 non-null vector；
- embedding `content_hash` 必須等於 confirmed card 現在的 semantic hash。

因此 cross-owner、archived、wrong-language、wrong-deck、stale-model、missing-vector 與
stale-content rows 都不會進入 cosine ranking。

Response 回傳卡片顯示欄位，以及：

- `distance`：pgvector cosine distance，範圍 `[0, 2]`，越低越接近；
- `score = 1 - distance`：cosine similarity，範圍 `[-1, 1]`，越高越接近；
- `index_status`：`complete`、`partial` 或 `empty`；
- eligible 與 indexed counts。

API 不回傳 raw vectors，也沒有聲稱某個 score threshold 代表一定相關。

## 3. 完成的前端功能

新增 static-deployment-compatible `/search` 頁面，沿用現有 Google bearer token 與 generated
OpenAPI TypeScript contract：

- 顯示 loading 狀態；
- 區分真的沒有 eligible cards 與 cards 尚未完成 indexing；
- partial coverage 時清楚顯示 indexed/eligible counts；
- auth expired 時引導重新登入；
- provider、database 或 network failure 不會被顯示成空結果；
- retry 時保留原 query；
- route 與 card links 使用 `$app/paths.resolve()`，保留 GitHub Pages base-path 相容性。

## 4. 本機驗證完成了什麼

Repository verification 包含：

- 完整 backend PostgreSQL suite：289 tests passed；
- semantic-search focused pgvector suite：3 tests passed；
- backend unit suite：128 tests passed；
- frontend contract/component tests：20 tests passed；
- Svelte check：0 errors、0 warnings；
- static production build：passed；
- critical Playwright search flow：1 passed；
- Ruff 與 whitespace checks：passed。

Focused PostgreSQL tests 使用 deterministic fake vectors，驗證 ranking，並明確排除另一位
owner、archived、wrong-language、wrong-deck、stale-model 與 missing-vector rows。測試也證明
unauthenticated 或 malformed request 不會呼叫 fake provider，而 provider timeout 會回 retryable
503。

## 5. `EXPLAIN` 是什麼

PostgreSQL 收到 SQL 後，不會只照文字由上到下執行。Query planner 會根據資料量、statistics、
indexes 與成本估計，選擇 table scan、join order、join algorithm、sort method 等 execution plan。

`EXPLAIN` 顯示 planner **預計**怎麼執行，但不真正執行查詢。`EXPLAIN ANALYZE` 會真正執行
query，並把估計與實際結果放在一起。這次使用：

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS, FORMAT JSON)
```

其中：

- `ANALYZE`：顯示實際時間、rows 與 loops；
- `BUFFERS`：顯示資料頁從 shared cache 命中或由 storage 讀取；
- `SETTINGS`：保留可能影響 planner 的設定；
- `FORMAT JSON`：提供完整、可結構化閱讀的 plan，而不是只看 UI 圖形。

`EXPLAIN ANALYZE` 對這次的 `SELECT` 會真正執行 vector ranking，但整段包在 read-only
transaction，沒有 provider call，也沒有 product-data mutation。

## 6. 如何閱讀這次的 query plan

這次最重要的欄位如下：

- `Plan Rows`：planner 事前估計會有幾筆；
- `Actual Rows`：實際通過該 node 的筆數；
- `Actual Loops`：該 node 被執行幾次；
- `Actual Total Time`：該 node 的實際時間；
- `Shared Hit Blocks`：已在 PostgreSQL shared buffer/cache 的資料頁；
- `Shared Read Blocks`：需要從較下層 storage 讀入的資料頁；
- `Sort Method` 與 `Sort Space Used`：排序算法、記憶體與是否 spill 到 disk；
- `Rows Removed by Filter`：被 predicate 排除的 rows；
- `Index Cond`、`Filter` 與 `Join Filter`：條件在哪個 execution stage 生效。

看到 `Seq Scan` 不代表 query 一定有問題。當 table 只有約 597 rows，掃完整張小表通常比透過
index 做大量 random lookups 更便宜。是否需要 index 應由實際 candidate cardinality、latency、
memory 與 recall 共同判斷，而不是看到 sequential scan 就立即增加 index。

## 7. Production coverage 檢查

Operator 在 production Neon branch 以 read-only SQL Editor 查得：

| Language | Eligible cards | Current indexed cards |
| --- | ---: | ---: |
| English | 596 | 596 |
| Japanese | 1 | 1 |

這表示當下所有 eligible production cards 都有 active-model、ready、non-null 且 hash-current 的
embedding。這是一次 operator-supplied production observation，不是持續性 coverage guarantee。

## 8. Query-plan 測試如何演進

### 8.1 第一版：動態 params CTE

第一版為了不複製 owner、deck 或 raw vector，使用 CTE 動態找一筆 query vector 與 owner/language。
無 deck filter 的 execution time 為 10.545 ms；有 deck filter 為 12.177 ms。

但 plan 顯示：

- active decks 先依 owner 展開；
- 形成 1,194 個中間 rows；
- 對 cards 做 1,194 次 index lookup；
- 最後才縮回 596 個 English candidates。

這是 probe SQL 的 CTE/join shape 所造成，不完全代表正式 API 使用固定 bind parameters 時的
plan。兩個 English plans 的 candidate count 都是 596，表示當下 selected English deck 並沒有
縮小 corpus；單次約 1.6 ms 的差異不能解讀成 deck filter 比較慢。

### 8.2 第二版：固定 owner，但 query-vector CTE 每 row 掃描

第二版固定 production owner 與 English language，join 從 1,194 個中間 rows 改善為約 597 rows，
並改用小表 sequential scans 加 in-memory hash join。

該次觀察為：

- Planning Time：46.236 ms；
- Execution Time：128.336 ms；
- Shared reads：258；
- `query_vector` CTE loops：596。

這次包含 storage reads/cache warming，而且 query-vector CTE 被每個 candidate 重複掃描，因此不能
把 128 ms 當成正式 API latency。它的重要價值是讓我們看到 cold/read-heavy observation，以及
probe SQL 與真正 bind vector 仍有差異。

`Shared Dirtied Blocks` 也不代表產品資料被修改。PostgreSQL 的 read-only query 仍可能因
visibility hint bits 將記憶體 buffer 標記為 dirty；沒有 logical row mutation。

### 8.3 最終版：query vector 成為一次性 InitPlan

最後將 query vector 改成 scalar subquery。Plan 顯示 query-vector CTE 與兩個使用 vector 的
InitPlans 都只有 `Actual Loops: 1`，更接近正式 API 直接使用 query-vector bind parameter 的形狀。

Operator-supplied production observation：

| Metric | Observed value |
| --- | ---: |
| Planning Time | 1.354 ms |
| Execution Time | 10.054 ms |
| Eligible English candidates | 596 |
| Returned rows | 10 |
| Card scan | 0.282 ms |
| Embedding scan | 0.128 ms |
| Card/embedding hash join | 0.810 ms |
| Main eligibility/ranking path | 9.111 ms |
| Sort method | top-N heapsort |
| Sort memory | 27 kB |
| Shared reads | 0 |
| Temporary reads/writes | 0 |

Probe 額外花約 1.357 ms 從現有 row 取得測試 vector；正式 API 的 vector 已由 provider 產生，因此
database query 不需要這段 seed-vector 查詢。

## 9. 最終 planner 判斷

在 596 個 English candidates 上，PostgreSQL 選擇：

- sequential scan 小型 `learning_cards` relation；
- sequential scan 小型 `card_embeddings` relation；
- in-memory hash join，並檢查 current content hash；
- owned deck composite index lookup；
- 27 kB in-memory top-N heapsort 回傳 10 rows。

Plan 仍有 cardinality estimation mismatch：部分 node 的 `Plan Rows` 是 1，而 `Actual Rows` 是
597。這值得保留為後續成長時的觀察點，但目前沒有導致不良 plan、disk spill 或不可接受的資料庫
時間，因此不為了這個小 corpus 新增 index 或調整 production statistics。

## 10. 為什麼現在不加 HNSW

HNSW 是 approximate nearest-neighbor index。它在大 corpus 可避免對每個 vector 做 exact
comparison，但會增加 index storage、build/update 成本與 operational complexity；在先套用 owner
與其他 SQL filters 的情況下，也需要另外量測 filtered recall，不能只看速度。

目前不加 HNSW 的實測理由：

- English corpus 只有 596 vectors；
- warm-cache exact production observation 約 10 ms；
- embedding sequential scan 約 0.13 ms；
- Top-K sort 只有 27 kB；
- 沒有 temporary I/O 或 sort spill；
- exact scan 保留完整 filtered recall。

未來只有在 owner-filtered corpus 顯著增加，而且多次量測的 database p95 成為真實瓶頸時，才應
重新評估 HNSW，並同時比較 latency 與 owner-filtered recall。

## 11. 這些數字不能證明什麼

本次數字是 Neon SQL Editor 的少數單次 observations，不能當成：

- p50 或 p95；
- Cloud Run end-to-end latency；
- Vertex provider latency；
- 真實使用者感受到的整體搜尋時間；
- corpus 成長後仍相同的效能保證。

完整 request 還包括 authentication、query embedding network call、database connection、JSON
serialization、Cloud Run/Neon network path 與 browser network。這些要在 candidate deployment 的
provider-backed smoke 分開觀察。

## 12. 五分鐘說明版本

後端先驗證 Google token，取得 internal owner ID。Query 被限制長度並只做一次
`RETRIEVAL_QUERY` embedding。SQL 在 vector ranking 前先排除另一位 owner、archived card/deck、
wrong language/deck、old model、missing vector 與 hash-stale embedding，再對剩下的 rows 做 exact
cosine Top-K。Production 當下 596 張 English cards 全部 indexed；最終 read-only plan 使用小表
sequential scans、hash join 與 27 kB top-N heapsort，單次 warm-cache execution observation 是
10.054 ms。因此目前 exact scan 足夠，不增加 HNSW。Provider failure 是 retryable error，不會被
呈現成空搜尋。

## 13. What we learned

### 13.1 Authorization 必須在 ranking 前完成

先做全域 Top-K 再由 frontend 或 application code 過濾 owner，不只可能洩漏資料，也可能讓其他
owner 的結果佔滿 Top-K，造成合法使用者看到錯誤的空結果。正確邊界是把 owner 與 eligibility
predicates 放在 ranked SQL relation 內。

### 13.2 `EXPLAIN ANALYZE` 測到的是 SQL shape，不只是資料庫

第一版與第二版 probe 的 CTE 寫法產生額外 join rows 或重複 CTE scans。這些結果不是資料庫
「很慢」，而是測試 query 與 production bind-parameter shape 不夠接近。閱讀 plan 時要追蹤 rows、
loops 與 predicates 在哪個 node 生效，而不是只看最上層 execution time。

### 13.3 Cold observation 與 warm observation 都有價值，但不能混為一談

128.336 ms 的 run 有 258 shared reads；10.054 ms 的 final run 全部 cache hits。前者提醒我們
serverless/cache 狀態會影響單次結果，後者則描述 warm exact-ranking path。沒有多次取樣就不能
聲稱 p95。

### 13.4 Sequential scan 不等於缺少最佳化

對約 597 rows 的小表，sequential scan 只花約 0.13 到 0.28 ms，可能比維護與使用 ANN index 更
合理。Index 是針對被量測到的瓶頸，不是看到 `Seq Scan` 就自動加入。

### 13.5 Coverage 與 relevance 是不同問題

596/596 表示 current embeddings 完整，不表示搜尋結果一定符合使用者意圖。Coverage、retrieval
quality、provider latency 與 end-to-end latency 必須分別量測。下一步仍需要 bounded
provider-backed quality/latency smoke。

### 13.6 Evidence 要保留限制

這次可以防守的說法是：「在當下 production 的 596-card English corpus 上，一次 warm-cache
exact SQL observation 為 10.054 ms，且沒有 disk spill，因此沒有 HNSW 的 measured need。」不能
延伸成 production SLA、p95、規模化保證或使用者成效。
