# Issue #41 學習筆記：語意檢索品質、成本與失敗評估

## 這張 ticket 想解決什麼問題？

Issue #40 已經證明 semantic search 的 API、權限過濾與前端流程可以運作，但「功能可以跑」
不等於「結果值得信任」。Issue #41 的目的，是在考慮 grounded tutor 以前回答以下問題：

> 語意檢索是否夠有用、夠可靠，而且成本與延遲合理，值得保留或繼續擴充？

這是一個 release/evaluation boundary，不是 LLM generation ticket。我們沒有建立聊天回答、
沒有讓模型修改卡片，也沒有因為搜尋有結果就宣稱系統 `ai-ready`。

這張 ticket 最後必須做出三選一的決策：

- **go**：檢索已足以成為 grounded tutor 的基礎。
- **iterate**：搜尋值得保留，但 tutor 以前仍需改善。
- **stop**：語意搜尋沒有提供足夠價值，不值得繼續擴充。

最後的決策是 **iterate**。

## 為什麼不能只看「搜尋結果感覺不錯」？

語意搜尋至少包含三個不同問題：

1. **系統正確性**：有沒有洩漏別人的卡片？archive、model version、stale embedding 是否被
   正確排除？
2. **模型相關性**：embedding model 排出的 Top-K 是否真的符合人的語意判斷？
3. **操作特性**：每次搜尋會呼叫幾次 provider？延遲、token 與成本是多少？失敗時會發生
   什麼事？

如果只用幾個看起來成功的例子，容易把以下問題混在一起：

- expected card 根本不存在於 corpus，卻把它當成 retrieval miss；
- vector ranking 正確，但 owner filter 寫錯而洩漏資料；
- provider timeout 被偽裝成「沒有搜尋結果」；
- Top-K 永遠回傳五筆，卻沒有一筆真的相關；
- 單次 warm query 很快，就誤稱為穩定的 p95 latency。

因此，我們先凍結評估規則，再看最終結果。

## 預先凍結的品質規則

Issue #38 已建立 synthetic relevance fixture，使用以下標籤：

- `2`：strong relevance，直接回答 query。
- `1`：related，有關聯但不是直接答案。
- `0`：irrelevant，對 query 沒有實際幫助。

主要 synthetic metric 是 macro nDCG@5，預先設定的 gate 是：

```text
macro nDCG@5 >= 0.75
```

安全 gate 是 deterministic PostgreSQL tests 不得出現 cross-owner 或 archived data leakage。
Recall@5、hit@5、coverage、latency 與 cost 是必要觀察，但不能在看到結果後才挑一個有利的
數字當門檻。

## Deterministic correctness 與 model relevance 的差別

### Deterministic correctness tests

這些測試使用固定 fake vectors 和真正的 PostgreSQL/pgvector。相同 input 應該永遠得到相同
結果，因此適合放在 CI。

它們回答的是：

- authenticated owner 以外的資料會不會出現？
- foreign deck 是否被遮蔽成 404？
- archived card/deck 是否被排除？
- missing、stale hash、錯誤 model version 的 vector 是否被排除？
- cosine ordering 與 UUID tie-break 是否穩定？
- empty、fully unindexed、partial coverage 是否誠實呈現？
- provider timeout 是否回傳 retryable 503，而不是空的 200？

這些測試不能證明 embedding model「懂英文語意」，但可以證明系統不會因 vector search
繞過授權與 lifecycle rules。

### Model relevance evaluation

這部分使用真正的 Vertex embedding，再由人或預先標記的 relevance labels 判斷 Top-K。

它回答的是：

- paraphrase 是否能找到沒有出現相同字面的卡片？
- exact term 是否能穩定找到目標？
- ambiguous word sense 是否會找錯意思？
- 沒有好答案時，系統是否仍回傳看似合理但其實無關的內容？

模型輸出、provider latency 與網路狀況可能變動，所以 provider evaluation 必須是明確執行的
評估，不應成為會隨機失敗的 deterministic CI test。

## 我們建立的 SQL 與用途

### `production-inspection.sql`

用途是安全地檢查 production Neon 的 coverage 與 query plan。

它只執行 `SELECT` 和 `EXPLAIN (ANALYZE, BUFFERS)`，不輸出：

- card text；
- card ID 或 owner ID；
- content hash；
- raw vector。

它回答：

- active English cards 有幾張？
- 有幾張 current ready embeddings？
- 是否存在 null vector 或 stale hash？
- owner、archive、language、model、state、hash filters 是否在 Top-K 前套用？
- PostgreSQL 使用什麼 scan、sort 與記憶體？
- 是否產生 temporary I/O？

我們一開始使用資料庫內的一個 stored vector 當 probe，但 materialized CTE 的 detoasting／
重複引用形狀與 API parameter 不同，兩次分別花費約 133 ms 與 123 ms。這提醒我們：

> 看似相似的 SQL probe，不一定代表真實 API query shape。

後來改用 deterministic synthetic 512-dimensional constant，讓右側 query vector 更接近 API
傳入的 parameter。該次 read-heavy observation 為約 130 ms；Issue #40 另有一次 shared-hit-only
的 API-shaped observation 約 10 ms。這些結果證明 latency 會受 cache／compute 狀態影響，不能
只取最快的一次做 performance claim。

不論哪一份 plan，596 candidates 的 exact ranking 都只使用約 25–27 kB Top-N heapsort，沒有
temporary I/O。因此目前沒有 measured reason 加入 HNSW。

### `expected-concept-check.sql`

這是 v1 fixture 的 corpus presence check。

它發現 17 個 expected terms 在實際 active English corpus 中全部都是 0。這代表我們錯把 Issue
#38 的 synthetic concepts 當成 production corpus 的 target，v1 的 hit/miss 全部無法作為品質
證據。

這不是 retrieval model failure，而是 evaluation design failure。

### `expected-concept-check-v2.sql`

v2 改用使用者同意的八個實際 terms：

```text
communism, severance, brat, hotshot,
fragrance, diligently, endangered, obtain
```

SQL 只回傳 sanitized term 與 aggregate count。Neon preflight 證明每個 term 都剛好有一張
active English card。直到這個 preflight 通過後，我們才執行 v2 quality evaluation。

這建立了一個重要規則：

> expected target 不存在時是 fixture/corpus mismatch；存在但沒有進 Top-K，才可能是
> retrieval failure。

## 我們建立的 Python scripts 與用途

### `run_deployed_evaluation.py`

這是 deployed semantic-search workload runner，會呼叫：

```text
POST /v1/cards/semantic-search
```

主要功能：

- 從 frozen JSON fixture 載入 10 個 queries；
- 驗證 fixture 結構並記錄 SHA-256；
- 從隱藏提示或 `GOOGLE_ID_TOKEN` 環境變數取得 Google ID token；
- 不接受 CLI token，避免 token 留在 shell history；
- 可傳入 stable API base URL、owned deck ID、repetitions 與 report path；
- 收集 HTTP status、request ID、coverage 與 end-to-end latency；
- 第一次結果在本機 terminal 顯示，讓使用者用 0/1/2 評分；
- report 不保存 query text、card ID、term、meaning、score、distance 或 token；
- 計算 nearest-rank p50/p95、strong hit@5 與 best strong rank。

第一次執行時，50 個結果全部被評成 2，包含預期 no-match 的 query。這讓我們發現評分尺度
使用錯誤。Runner 後來補上：

- 更嚴格的 grade 2 說明；
- 五筆全部為 2 時顯示警告；
- no-confident-match 出現 grade 2 時要求明確確認。

這說明 evaluation tooling 本身也需要防止人為誤用，不能只相信輸入數字。

### `deployed-queries.json`

這是保留下來的 v1 fixture。它的目標不存在於實際 corpus，因此不能作為 deployed relevance
證據。保留它是為了記錄錯誤與修正過程，而不是假裝第一次設計就正確。

### `deployed-queries-v2.json`

這是正式 corpus-grounded fixture，包含：

- 2 個 paraphrase；
- 2 個 exact terms；
- 2 個 ambiguous queries；
- 2 個 natural sentences；
- 1 個 no-confident-match negative control；
- 1 個 near-synonym query。

Fixture 在 retrieval 前凍結，SHA-256 為：

```text
4756caf33424266c5722b344124a5d226427fc065dece6e02c8746fd7e86a5a4
```

### `measure_vertex_query_cost.py`

Production provider client 會驗證 Vertex 回傳的 `token_count`，但不保留它，因此 deployed API
report 無法回推實際 token usage。

這支 script：

- 驗證 v2 fixture hash；
- 對 10 個 sanitized queries 各送一次 `RETRIEVAL_QUERY`；
- 不輸出 access token、query text 或 vector；
- 記錄 provider-reported input tokens；
- 計算 provider p50/p95；
- 使用有日期與來源的公開費率估算成本；
- 明確標示 actual billing 未檢查。

## 實際完成了哪些工作？

### 1. 凍結評估邊界

在最終結果前記錄 metric、threshold、failure matrix、query workload 與報告格式，避免看到結果
後才改規則。

### 2. 重現 synthetic baseline

- Lexical word-overlap baseline：macro nDCG@5 `0.5655`。
- Vertex synthetic evaluation：macro nDCG@5 `1.0`、strong Recall@5 `1.0`。
- 17 requests、314 input tokens。

Synthetic 結果證明固定小資料集上的模型能力，但不能代表實際 owned corpus。

### 3. 檢查 production coverage 與 query plan

- 596/596 active English cards 有 current ready embedding。
- 0 null vectors。
- 0 stale hashes。
- exact Top-K 使用小型 in-memory sort，沒有 temporary I/O。
- 沒有證據需要 HNSW。

### 4. 完成 deployed latency workload

30/30 requests 回傳 HTTP 200 與 complete 596/596 coverage。

- End-to-end p50：`1789.565 ms`。
- End-to-end p95：`2793.855 ms`。
- 20 次 repeated observations p50/p95：`1782.699/1856.942 ms`。
- 有一次 `10824.294 ms` outlier，無法從現有資料判斷是 Cloud Run cold start、Vertex、網路或
  PostgreSQL，因此只記錄 observation，不捏造 root cause。

### 5. 發現並修正 v1 fixture failure

v1 所有 targets 都不存在於 corpus，因此相關性結論作廢，但 latency、HTTP success 與 coverage
證據仍有效。之後用八個真實、同意使用的 cards 建立 v2。

### 6. 完成 corpus-grounded v2 quality run

九個 positive queries 中，八個有 grade-2 Top-5 result：

```text
positive strong hit@5 = 8/9 = 0.8889
```

七個 strong targets 位於 rank 1。

分類結果：

- paraphrase：2/2；
- exact：2/2；
- natural sentence：2/2；
- near-synonym：1/1；
- ambiguous：1/2。

唯一 positive miss 是 ambiguous severance。表示同一張 `severance` 卡在「遣散費」語境可以
rank 1，但「切斷關係／終止」語境沒有成為 grade-2 Top-5，顯示 word-sense sensitivity。

Negative control 的五筆全部為 0。這證明固定 Top-K 會在沒有好答案時仍回傳五筆 nearest
neighbors。

### 7. 測量 provider tokens、latency 與成本

10 個 v2 queries：

- 84 input tokens；
- provider p50：`1280.6 ms`；
- provider p95：`1713.1 ms`；
- 以 `$0.15 / 1M input tokens` 估算成本：`$0.0000126`；
- actual billing 未檢查。

這個估算不包含 document backfill embeddings、Cloud Run、Neon 或網路成本。

### 8. 完成 deterministic failure matrix

11 個 PostgreSQL/pgvector integration tests 通過，涵蓋：

- empty corpus；
- fully unindexed corpus；
- partial coverage；
- content edit／stale hash；
- card/deck archive；
- model mismatch；
- provider timeout；
- cross-owner card/deck；
- ranking/order。

我們也觀察 provider-call boundary：

- valid normal、empty、fully unindexed search：各呼叫一次 query embedding；
- invalid auth/body、foreign deck、archived deck：provider call 為 0。

Empty/unindexed corpus 仍花費一次 query embedding，是下一輪可以改善的小型成本與可靠性問題。

## SQL 與 vector 各自負責什麼？

SQL 適合回答精確、結構化問題：

- authenticated owner；
- deck、language、tag；
- active/archive state；
- card ID；
- count；
- review due time 與 history；
- active model、ready state、matching content hash。

Vector 只負責在 SQL 已授權的候選 rows 中，依語意距離排序。

例如：

> 在我的 active Business English deck 中，找五張與「公司解雇員工時支付的費用」語意相近
> 的卡片。

正確順序是：

1. SQL 限制 authenticated owner、owned deck、English、active rows、current model/hash。
2. Vector 對這些合法 candidates 計算 cosine distance。
3. 排序後 `LIMIT 5`。

Vector ranking 不能授予資料存取權，也不能取代 owner filter。

## 最終決策

Issue #41 的決策是 **iterate**：

- 保留 semantic search MVP；
- 保留 `gemini-embedding-001` 與 canonical-v1；
- 保留 exact pgvector scan；
- 不加 HNSW；
- 不因單一 ambiguous miss 就更換模型；
- 暫不進入 grounded tutor。

Grounded tutor 前需要先完成：

- 使用 frozen positive／negative labels 設計 relevance/no-answer gate；
- 檢查 score distribution，而不是憑感覺挑 threshold；
- 加入更多 ambiguous word-sense cases；
- 確保 negative query 不會把五筆無關 Top-K 當成 grounded context；
- 考慮 empty/unindexed corpus 時先檢查 coverage，避免不必要的 provider call。

## What we learned

### 1. 正確的 evaluation fixture 和模型本身一樣重要

v1 最大的問題不是 model 排錯，而是 expected targets 根本不在 corpus。沒有 corpus presence
preflight，hit/miss 數字看起來完整，實際上卻無法回答產品問題。

### 2. 失敗的評估不必全部丟掉，但要拆分證據

v1 relevance grades 作廢，不代表同一次 workload 的 HTTP、coverage 與 latency 都作廢。
我們保留仍然有效的觀察，明確撤回無效的品質結論。

### 3. Top-K 非空不代表有答案

Vector search 永遠可以找出「最近」的 rows，但最近不一定相關。Negative control 的五筆結果
全是 0，證明 tutor 必須有 no-answer boundary，不能只檢查 `items.length > 0`。

### 4. 平均品質會隱藏 word-sense failure

8/9 hit@5 看起來不錯，但 ambiguous severance 揭露同一個詞的不同語意可能有完全不同的
retrieval outcome。Failure analysis 比單一 aggregate score 更能指出下一步。

### 5. Deterministic correctness 與 model quality 不能互相替代

好的 nDCG 不能證明 owner isolation；完整的 authorization tests 也不能證明結果對學習者有用。
一個可辯護的 retrieval system 必須同時具備兩種證據。

### 6. 小 corpus 不需要預先最佳化

596 candidates 的 exact Top-K sort 很小，沒有 temporary I/O。HNSW 會引入 approximate recall
與 filtered search 複雜度，目前沒有 measurement 支持這項成本。

### 7. 延遲數字必須帶著 workload 與限制

Provider、Cloud Run、Neon、網路與 cold compute 都可能影響 end-to-end time。單次 10 ms SQL、
1.8 秒 median API 與 10.8 秒 outlier 都是真的 observation，但沒有一個可以單獨被描述成 SLA。

### 8. 小流量下 token 成本很低，但可靠性仍然重要

10 queries 的估算 input cost 只有 `$0.0000126`，所以目前不需要 cache 或額外基礎設施。
不過 provider timeout、no-answer handling 與不必要的 empty-corpus call，仍會影響使用者體驗與
系統行為。

## 五分鐘口頭說明版本

我們先用 deterministic PostgreSQL tests 證明 vector ranking 只能看到 authenticated owner 的
active/current cards，並驗證 empty、partial、stale、archive、provider failure 與 cross-owner
行為。接著用 frozen synthetic set 評估 nDCG，再用 corpus-grounded、先確認 target 存在的 v2
fixture 評估 deployed Top-5。九個正向 queries 有八個命中，七個 rank 1，但 ambiguous
severance miss，而且 negative control 仍回傳五筆無關結果。30 次 deployed requests 的 p50
約 1.79 秒，10 次 query embeddings 共 84 tokens，估算成本約 `$0.0000126`。PostgreSQL 在 596
candidates 下沒有 HNSW 需求。最後決定保留搜尋，但 tutor 前必須先建立 evidence-backed
no-answer threshold 並擴充 ambiguous-sense evaluation。
