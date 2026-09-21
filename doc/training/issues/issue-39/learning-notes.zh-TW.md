# Issue #39 學習筆記：把 embedding 當成可重建的衍生資料

這份筆記整理 Issue #39 的設計、權限設定、migration 與 backfill 操作，以及我們實際驗證過的邊界。完整實作與驗證摘要見 [Issue #39 記錄](README.md)。

## Chapter 1. 這個階段在解決什麼

使用者確認的單字卡是產品的主要資料；embedding 是根據卡片內容計算出的衍生資料。兩者的重要性不同：卡片寫入成功後，即使 Vertex AI 暫時逾時或故障，卡片仍必須存在、可以編輯，也可以繼續複習。缺少的 embedding 之後再補即可。

這個階段因此建立以下流程：

```text
建立或編輯已確認卡片
  -> 在原本的資料庫交易中保存卡片與 semantic_content_hash
  -> 交易 commit
  -> 呼叫 Vertex AI 產生 embedding
  -> 另一個短交易確認內容仍然相同
  -> 寫入 card_embeddings

Provider 失敗
  -> 卡片交易不受影響
  -> embedding 留在 retryable／exhausted 狀態
  -> 操作人員稍後執行 bounded backfill
```

這裡沒有新增 queue、scheduler、cache、獨立向量資料庫或 ANN index。現有資料量和操作需求還不需要這些基礎設施。

## Chapter 2. Canonical text、hash 與模型版本

[semantic_text.py](../../../../apps/api/app/semantic_text.py) 是唯一的 canonical semantic-text builder。它依固定順序選取語言、詞、意思、詞性、讀音、例句和同反義詞等語意欄位，做 Unicode NFC 正規化與前後空白清理，再產生 SHA-256 hash。

固定格式很重要。如果 create、edit 和 backfill 各自組合文字，即使畫面上看起來相同，也可能因欄位順序或空白不同而得到不同向量。現在所有路徑共用同一個 builder。

目前的模型 key 是：

```text
vertex-ai/gemini-embedding-001/512/retrieval-v1/canonical-v1
```

它同時表達 provider/model、512 維輸出、document retrieval task 與 canonical text 版本。不能只看「資料表中有向量」就判定它可用；還要確認：

- owner 相同
- model version 是目前版本
- embedding 的 content hash 與卡片目前 hash 相同
- state 是 `ready`
- 卡片與所屬 deck 都沒有封存

因此，舊模型或舊卡片內容產生的向量不會被當成目前結果。

## Chapter 3. 資料庫 schema 與交易邊界

Alembic revision `20260920_0006` 啟用 pgvector、在 `learning_cards` 加入可為空的 `semantic_content_hash`，並建立 `card_embeddings`。Migration 只改 schema，不呼叫 Vertex AI，也不自動掃描既有卡片，所以乾淨 migration 不依賴外部 provider 是否在線。

`card_embeddings` 以 card、owner 與 model version 識別一份衍生結果，並保存：

- 512 維向量
- 內容 hash
- `pending`、`retryable`、`exhausted` 或 `ready` 狀態
- 嘗試次數與下次可重試時間
- 安全的錯誤分類
- claim token

create 與 semantic edit 會先提交原本的卡片交易，之後才呼叫 provider。Review-only 變更不影響語意內容，所以不重新 embedding。Confirmed CSV import 在原本的 atomic transaction 寫入 hash，但由明確執行的 backfill 補向量。

這裡有兩類重試控制，不要混在一起：

| 機制 | 解決的問題 |
| --- | --- |
| HTTP idempotency key | 防止 client 重送 create request 時產生重複卡片或初始 review state |
| content hash + model version + claim token | 防止較舊或較慢的 provider 結果覆蓋新的卡片內容或新的 embedding 嘗試 |

例如，第一次 edit 的 Vertex 請求尚未完成時，使用者又完成第二次 edit。第一次結果回來後，程式會再次鎖定並讀取目前卡片；只要 hash 或 claim token 已改變，就回報 `stale`，不寫入舊向量。

## Chapter 4. 三組權限怎麼分工

這次涉及三組不同權限，彼此不能替代。

### 4.1 Neon migration role

`neondb_owner` 用於 Alembic migration。它需要建立 extension、table、constraint 和 index 的 DDL 權限。正式 migration 應透過受保護的 migration workflow／job 執行，不讓一般 API request 在啟動時自動改 schema。

### 4.2 Neon runtime role

`app_runtime_limited` 是 API 與 backfill 的資料庫 runtime role。它不需要 database 或 `public` schema 的 `CREATE` 權限，只需要本功能所需的最小 DML 權限：

- 對 `card_embeddings` 執行 `SELECT`、`INSERT`、`UPDATE`
- 更新 `learning_cards.semantic_content_hash`
- 既有 card/deck read/write 所需權限

我們在隔離 Neon branch 分別檢查每一個 privilege。PostgreSQL 的 `has_table_privilege(..., 'SELECT,INSERT,UPDATE')` 在其中任一權限成立時就可能回傳 true，因此不能用一個合併檢查取代三個獨立檢查。

### 4.3 Google Cloud IAM 與本機 impersonation

Cloud Run 使用的 service account 是 Vertex AI 的呼叫身分。它在 project 上需要：

```text
roles/aiplatform.user
```

這個 role 的方向是「service account 可以呼叫 Vertex AI」。它不會讓個人帳號自動變成該 service account。

本機 backfill 透過 ADC（Application Default Credentials）取得憑證。為了讓個人帳號在本機模擬 Cloud Run service account，我們在**該 service account 資源上**暫時授予個人帳號：

```text
roles/iam.serviceAccountTokenCreator
```

接著執行：

```bash
gcloud auth application-default login \
  --impersonate-service-account=SERVICE_ACCOUNT_EMAIL
```

ADC 檔案記錄應用程式要模擬哪個 service account；每次短期 token 需要建立或刷新時，IAM 仍會檢查個人帳號是否有 Token Creator。兩者缺一不可。

```text
個人 Google 帳號
  -> Token Creator 允許 impersonation
  -> ADC 取得短期 service-account token
  -> Python google.auth.default()
  -> Vertex AI
```

Token Creator 應只授予在這一個 service account 上，不授予整個 project。Backfill 結束後應移除個人帳號的 Token Creator。Cloud Run 本身使用附加的 service account 與 metadata server，不需要保留個人帳號的這項權限，也不需要下載長期 service-account key。

## Chapter 5. 安全的 migration 與 provider 驗證流程

操作順序的重點是逐步增加影響範圍，每一層成功後才進下一層。

### Step 1：建立隔離資料庫 branch

從預期基底建立 Neon branch，確認 endpoint host，避免誤連 production。連線字串只放在 git-ignored `.env` 或 shell 的 silent prompt，不貼到對話、log 或文件。

### Step 2：執行 migration cycle

使用 migration role 執行：

```text
upgrade head -> downgrade -1 -> upgrade head
```

接著確認 Alembic revision、`vector(512)` 欄位、card/review counts 與 runtime grants。Downgrade 是隔離環境的 migration rehearsal，不代表 production 發生問題時一定採用 schema downgrade。

### Step 3：先測合成文字

先以 service account 身分傳送一段不含私人資料的合成文字，驗證模型名稱、region、IAM、512 維、finite/nonzero values 與 `truncated=false`。這一步成功只證明 provider contract；還沒有證明 backfill 的資料庫寫入。

### Step 4：dry run

Backfill 的 `--dry-run` 只列出 eligible counts 和 resume cursor，不呼叫 provider、不寫 hash 或向量。先確認 owner、卡片數量與 cursor resume 行為。

### Step 5：逐步 backfill

在資料處理獲得同意後，以 1 張開始，再增加到 25、100 張。每一批只保留安全的 counts、cursor 和是否達到時間上限：

```bash
VERTEX_PROJECT_ID=PROJECT_ID \
uv run python -m app.embedding_backfill \
  --owner-id OWNER_ID \
  --limit 100 \
  --cursor PREVIOUS_CURSOR
```

不要輸出卡片文字、向量、token、provider response 或 database URL。若 counts 出現 timeout、rate limit、retryable 或 exhausted，先停止擴大批次，確認失敗類別與 retry window。

## Chapter 6. Backfill、cursor 與 retry state

Backfill 是「替既有或遺漏資料補建衍生結果」，不是 schema migration。它會找出以下卡片：

- hash 尚未建立
- 目前模型沒有 embedding row
- embedding hash 已過期
- retryable 且已到下次重試時間
- pending claim 已超過兩分鐘
- 操作人明確要求重試 exhausted row

命令以 owner 為邊界，依 UUID keyset 分頁。單次最多處理 500 張或 30 分鐘，每個 database page 最多 100 張。`next_cursor` 非空時，用它繼續向後掃描；為空表示這輪已到 eligible keyspace 尾端。

Cursor 只描述掃描位置，不表示 cursor 前面的每張卡都成功。如果某張發生 provider failure，這一輪仍可能繼續向後走。到尾端後，需要在 retry delay 到期時從沒有 cursor 的新一輪開始，讓查詢重新找到前面已變成 retryable 的項目。達三次失敗會進入 `exhausted`，只有明確的 `--retry-exhausted` 才會再嘗試。

這次隔離 branch 的實際流程是 1 張、25 張，再以 100 張批次續跑。最後聚合結果為 597 個 `ready`、597 個 card hashes、597 張 cards、597 個 review states、沒有其他 state，且 hash mismatch 為 0。最後再從頭執行一次，得到空 counts 與 null cursor，證明 unchanged current content 不會再次呼叫 provider。

## Chapter 7. 驗證層次與安全界線

| 驗證層次 | 證明了什麼 | 尚未證明什麼 |
| --- | --- | --- |
| Unit tests | canonical text、hash、向量驗證與 provider error mapping | PostgreSQL transaction 與真實 provider |
| PostgreSQL integration tests | migration cycle、失敗重試、stale write、concurrency、owner/archive boundary | Neon permissions 與真實 Vertex IAM |
| 合成 Vertex request | impersonated identity 可呼叫指定模型並取得有效 512 維結果 | 私人卡 backfill 與 Cloud Run path |
| 隔離 Neon backfill | ADC、provider、runtime DB 權限、cursor resume、597 張完整寫入與 replay | production deployment、Cloud Run metadata identity、搜尋品質 |
| Production Cloud Run Job | runtime service identity、Secret Manager、Vertex、production Neon、完整 backfill 與 replay 串接成功 | 已切換 production traffic 或搜尋結果品質 |

CI 也必須使用含 pgvector extension 的 PostgreSQL image。一般 `postgres:17-alpine` 沒有 `vector.control`，所以 migration 會在 `CREATE EXTENSION vector` 失敗。CI 與 local Compose 現在一致使用 `pgvector/pgvector:0.8.6-pg17-bookworm`。這提醒我們：資料庫 major version 相同，不代表 extension 環境相同。

## Chapter 8. Production 操作前後

隔離 branch 全部成功後，production 仍應保持下列順序：

1. Review 並 merge code。
2. 發布與 commit 對應的 immutable API image。
3. 透過 protected migration workflow 執行 Alembic migration。
4. 部署 zero-traffic candidate，設定 `VERTEX_PROJECT_ID` 與 `VERTEX_LOCATION`。
5. 使用真正的 Cloud Run workload identity 驗證 candidate。
6. 通過 smoke checks 後才切換流量。
7. 最後由操作人員明確啟動 owner-bounded production backfill。

Migration 不應自動開始 backfill。這讓 schema 問題、candidate 問題與 provider/backfill 問題有各自清楚的停止點，也避免 migration 因外部服務失敗而卡住。

Backfill 完成後應驗證 state counts、hash coverage、hash mismatch、card/review counts，以及空 replay。最後移除個人帳號的 Token Creator 權限；service account 的 `roles/aiplatform.user` 則是 Cloud Run runtime 功能需要的權限，是否保留由正式功能是否啟用決定。

## Chapter 9. Production Cloud Run Job 實際操作與修正

Production 沒有把隔離 Neon branch 的 embeddings 搬回正式 branch。Branch 建立之後，正式資料仍可能新增或修改；直接搬資料需要處理衝突，也可能覆蓋較新的 card 或 review state。Embedding 本來就是可重建的資料，因此我們在 production migration 完成後，直接以 production cards 重新計算。

### 9.1 為什麼另建 backfill job

我們使用與 API candidate 相同的 immutable container image，但建立獨立的 Cloud Run Job。它沒有重用 migration job：

| Cloud Run resource | 身分與資料庫權限 | Command | 用途 |
| --- | --- | --- | --- |
| API Service | API runtime service account、runtime DB role | `python -m app.serve` | 處理 HTTP traffic 與單張 post-commit embedding |
| Migration Job | migration service account、schema owner | `alembic upgrade head` | 只改 schema |
| Backfill Job | API runtime service account、runtime DB role | `python -m app.embedding_backfill ...` | 補建既有或遺漏的 embeddings |

這樣 backfill 不需要 `neondb_owner`，也不會讓 migration identity 多拿 Vertex AI 權限。Job 使用 API runtime service account，所以 Cloud Run 透過 metadata identity 取得 Vertex token；不需要本機 ADC、不需要個人 Token Creator，也不需要 service-account key。

Job 使用一個 task、parallelism 1、Cloud Run retries 0。應用程式本身已管理 retryable、retry delay 和 exhausted；如果平台再自動重跑整個 execution，會混淆 attempt 與 cursor 的操作語意。Job timeout 設為 35 分鐘，略長於應用程式自己的 30 分鐘上限，讓程式有機會輸出安全 counts 與 resume cursor。

### 9.2 Image、secret 與環境變數

Job 使用與 candidate 相同的 digest-pinned image，而不是 `latest`。`DATABASE_URL` 由 Secret Manager 的固定 runtime secret version 注入；GitHub runner、Job 設定畫面和文件都不保存實際 URL。

一般環境變數包含：

```text
APP_ENV=production
LOG_LEVEL=INFO
DATABASE_CONNECT_TIMEOUT_SECONDS=5
VERTEX_PROJECT_ID=eng-learning-470909
VERTEX_LOCATION=us-central1
GOOGLE_OAUTH_CLIENT_ID=<與 API candidate 相同>
GOOGLE_ALLOWED_EMAILS=<與 API candidate 相同>
CORS_ALLOWED_ORIGINS=<與 API candidate 相同>
```

`VERTEX_PROJECT_ID` 和 `VERTEX_LOCATION` 是部署時注入的 runtime configuration，不會被打包進 container image。只在 GitHub environment 新增 variables 也不會修改已存在的 Cloud Run revision；必須部署新 revision 才會生效。

### 9.3 第一次 dry run 為什麼失敗

第一次 Job execution 的 Cloud Run audit event 只顯示：

```text
code: 10
reason: NonZeroExitCode
container exit code: 1
```

這是平台層的 execution 摘要，不是 PostgreSQL 或 Vertex 的根因。Container 已成功下載和啟動，真正的應用程式結果要看 `run.googleapis.com/stdout`／`stderr`。

當時 Job 設了 `APP_ENV=production`，卻只帶 database 與 Vertex 設定。Backfill CLI 共用完整的 `load_settings()`；production validation 也要求 `GOOGLE_OAUTH_CLIENT_ID` 與 `GOOGLE_ALLOWED_EMAILS`。即使 CLI 本身不處理登入，缺少這些欄位仍會在連資料庫前得到 `ConfigurationError`，最後只輸出安全的：

```json
{"status":"failed","error_code":"backfill_unavailable"}
```

這次是 dry run，設定載入又先失敗，因此沒有 provider call，也沒有資料寫入。我們把 API candidate 的 OAuth client ID、allowlist 與 CORS 設定加入 Job，並把 Cloud Run retries 從 3 修正為 0、timeout 從 10 分鐘調整為 35 分鐘。之後 dry run 成功。

這也暴露一個可以日後改善的設計：backfill CLI 目前依賴完整 web application settings。若其他 operator CLI 增加，可考慮拆出只驗證 database/provider 所需欄位的 command-specific settings；本 ticket 保留單一設定入口，並在 Job 中提供完整 production configuration。

### 9.4 從 dry run 到正式寫入

Production dry run 分兩頁完成：

```text
第一頁：eligible 100，回傳 next_cursor
第二頁：eligible 497，next_cursor = null
```

確認 597 張與預期 cardinality 相符後，才移除 `--dry-run`，從小批量開始並逐批傳入上一個 cursor。最後一個 execution 回報：

```json
{
  "counts": {"ready": 196},
  "next_cursor": null,
  "time_limit_reached": false
}
```

最後一批的 196 不能單獨證明總共有 597 張成功；因此我們另外執行 aggregate SQL。結果為 597 個 ready embeddings、597 個 card hashes、597 張 cards、597 個 review states、0 個 hash mismatch，以及 0 個 missing current embedding。

最後再用沒有 cursor、沒有 `--dry-run` 的命令從頭 replay。它回傳空 counts 與 null cursor，證明目前模型與內容 hash 都已 current，不會再次呼叫 provider。新版 zero-traffic candidate 也確認具有 Vertex project/location 設定並通過 environment smoke test。這些證據完成 production migration/backfill 邊界，但不表示 production traffic 已切換，也不證明語意搜尋結果品質。

## What we learned

1. **主要資料與衍生資料需要不同的成功邊界。** 卡片 commit 是產品寫入成功；embedding 可以晚一點完成，也可以安全重建。
2. **Idempotency 與 stale-write prevention 解決不同問題。** Idempotency key 防止 request replay 產生重複卡片；hash、model version 和 claim token 防止過時 provider 結果覆蓋新資料。
3. **ADC 不是一份永久 service-account credential。** ADC 可以記錄 impersonation 設定，但短期 token 的建立與刷新仍由 IAM 的 Token Creator 權限控制。
4. **權限要按角色與資源方向理解。** `roles/aiplatform.user` 讓 service account 呼叫 Vertex；`roles/iam.serviceAccountTokenCreator` 讓指定個人帳號暫時模擬該 service account；Neon 的 DDL 與 runtime DML 又是另一條權限邊界。
5. **Migration 不應依賴 provider。** Schema upgrade 要能在 Vertex AI 故障時完成；既有資料的向量補建由獨立、可暫停、可續跑的 backfill 負責。
6. **Cursor 到尾端不等於所有項目都成功。** 最後仍要查 aggregate states、hash mismatches，並從頭執行安全 replay，才能確認沒有遺漏的 retryable work。
7. **從一張開始能降低操作風險。** 合成請求、dry run、1、25、100 的漸進方式，讓 IAM、資料內容、provider contract 與 database write 各自有明確驗證點。
8. **CI 必須重現 extension contract。** PostgreSQL 版本正確仍不夠；使用 pgvector 的 migration，測試資料庫 image 也必須實際提供 pgvector。
9. **驗證結果要標明環境。** 隔離 Neon branch 的 597 張成功不等於 production 已部署，也不等於 Cloud Run workload path 或未來語意搜尋品質已驗證。
10. **平台錯誤碼通常只是外層摘要。** Cloud Run 的 `code: 10` 和 `NonZeroExitCode` 只告訴我們 process 失敗；根因要回到該 execution 的 container stdout/stderr，並只保留安全錯誤分類。
11. **CLI 共用設定會帶來隱性前置條件。** `APP_ENV=production` 讓 backfill 也必須提供 web auth 設定。建立 Job 時要對照程式實際載入的完整設定，不只列出命令表面上使用的欄位。
12. **平台 retry 與應用 retry 要有單一 owner。** Cloud Run retries 設為 0，由 embedding state machine 管理 retryable/exhausted，才能讓 attempt、cursor 與恢復流程保持可解釋。
13. **衍生資料應在目標環境重建。** Production embeddings 由 production cards 計算，不從 rehearsal branch 複製，避免覆蓋 branch 建立後的新資料或把測試狀態帶回正式環境。
