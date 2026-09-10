# Issue #23 學習筆記：Transactional Confirmed CSV Import

## 1. 這個 ticket 解決了什麼問題？

Issue #22 只做 read-only dry run：讀取私人 CSV、canonicalize 每一列、產生 hashes 與安全的
diagnostics，然後把核准依據存進 `import_runs` 與 `import_items`。它不會建立任何正式的
learning cards。

Issue #23 接續這個 boundary，把「已核准且沒有 rejected rows 的同一份 CSV snapshot」正式
匯入既有的 PostgreSQL deck，而且必須保證：

- CSV 從 dry run 到 apply 之間沒有被修改、刪除或替換；
- owner、deck、language、namespace、timestamp 與 validator version 完全相同；
- 每個 source row 只建立一張 card；
- cards、tags、associations、review states 與 mappings 要全部成功，或全部 rollback；
- 相同指令重跑時回傳已完成的結果，不建立 duplicate data；
- commit 後可以重新核對資料，且報告不洩漏私人學習內容。

這次 frontend 與 Google Apps Script 都沒有修改。匯入成功只代表 PostgreSQL 已成為
**verified migration candidate**，還不代表它已經成為 application runtime 的 source of truth。

## 2. 完整流程

```text
私人 CSV
   │
   ▼
Issue #22 dry run
   ├─ 重新整理與驗證 21 個欄位
   ├─ 產生 snapshot / identity / content hashes
   └─ 寫入 import_runs + import_items（不寫入 cards）
   │
   ▼ rejected_rows 必須等於 0，operator 核准 dry-run ID
Issue #23 confirmed import
   ├─ 再讀一次同一份私人 CSV
   ├─ 重算並比對全部 metadata 與 hashes
   ├─ 在一個 PostgreSQL transaction 建立產品資料與 mappings
   └─ commit
   │
   ▼
Post-commit reconciliation
   ├─ 比對 cards / mappings / tags / review states 等結果
   └─ 寫入不含私人內容的 reconciliation 結果
```

重要觀念：`import_items` 只有 hashes、row number、outcome 與安全 diagnostics。Confirmed
import 不會從它重建 term、meaning 或 examples；程式必須重新讀取私人 CSV，才能取得真正的
card content。

## 3. 四張 import tables 的分工

### `import_runs`（Issue #22）

代表一次 dry run，保存整份 snapshot 的核准資訊，例如：

- owner 與 target deck；
- source namespace 與 snapshot hash；
- validator version 與 target language；
- `snapshot_captured_at`；
- accepted、repaired、rejected rows 數量；
- bounded safe diagnostics。

`DRY_RUN_UUID` 就是 `import_runs.id`，而 CLI 的 `SNAPSHOT_TIMESTAMP` 對應
`import_runs.snapshot_captured_at`。

### `import_items`（Issue #22）

每一列 dry-run source row 的安全證據，包括：

- row number；
- source identity hash；
- canonical content hash；
- accepted、repaired 或 rejected outcome；
- safe diagnostic codes。

Issue #23 仍然需要這張 table。Confirmed importer 會將重新讀取 CSV 得到的每列結果，和
已核准的 `import_items` 逐列比較。因此 Issue #22 的 schema 與 validation logic 並沒有被取代。

### `confirmed_import_runs`（Issue #23）

代表一次已完成的 confirmed apply，保存 approved dry-run ID、owner/deck/namespace、各項安全
counts 與 reconciliation 狀態。

Unique constraints 讓同一個 approved dry run，以及同一個 owner/source namespace，都不能被
重複套用成另一批 cards。這張 table 也是 ambiguous client outcome 的 recovery anchor：如果
database 已 commit，但 CLI 還來不及寫 report 就中斷，retry 可以找到原本的 completed run。

### `confirmed_import_mappings`（Issue #23）

保存 source row 到正式 card 的 durable mapping：

```text
owner + source namespace + source identity hash + canonical content hash
                                ↓
                       learning_card.id
```

Composite foreign keys 和 unique constraints 會把 mapping 綁定到正確的 approved item、owner、
confirmed run 與 learning card，不能只靠 application code 的假設維持一致性。

## 4. Transaction 如何設定？

Confirmed importer 使用同一個 SQLAlchemy session 與 PostgreSQL transaction 完成 bounded
596-row apply。在 commit 前依序：

1. lock approved `import_runs` 與 target deck；
2. 驗證 dry run、deck、CSV metadata 與每列 hashes；
3. 建立 learning cards；
4. reuse 或建立 normalized owned tags；
5. 建立 card/tag associations；
6. 每張 card 建立一筆 fresh review state；
7. 建立 `confirmed_import_runs` 與所有 source mappings；
8. 全部成功後才 commit。

任何 exception 只要發生在 commit 之前，就會 rollback 這次 attempt 建立的所有 product 與
import records，不會留下「只匯入前 200 rows」之類的 partial completion。

Reconciliation 是 commit 後的另一個 bounded transaction。這是刻意的設計：產品資料 commit
後即使 CLI 或 report write 中斷，下一次執行仍能從 persisted apply record 找到結果、避免重複
寫入，再完成或重建 reconciliation。

## 5. Fresh review state

Legacy Sheet 的 scheduling values 只用來做 validation diagnostics，不會直接帶進新的 backend
scheduler。每張 imported card 都從同一個 deterministic fresh state 開始：

```text
review_stage = 1
ease_factor = 2.50
interval_days = 0
last_reviewed_at = NULL
next_review_at = approved snapshot timestamp
version = 1
```

如此可避免把舊 frontend 可修改、規則可能不同的 scheduling state 當成可信任的 backend state。

## 6. 我原本較不熟悉的部分

### Dry run 是什麼？

Dry run 是「驗證並留下可核准證據」，不是正式匯入。它讓 operator 在 product writes 發生前先
看 rejected rows、repairs 與安全 counts。只有 `rejected_rows = 0` 的 dry run 才能被 confirmed
import 使用。

### 為什麼 confirmed import 還需要 `import_runs` 和 `import_items`？

因為它們是 approved snapshot 的 immutable comparison boundary。Issue #23 不是相信 CLI 傳入的
CSV，而是重新 canonicalize CSV，再與 Issue #22 持久化的 metadata 和 row hashes 比對。少了這兩
張 tables，就無法證明 apply 的仍是 operator 核准的版本。

### `OWNER_ID`、`DECK_UUID` 與 `DRY_RUN_UUID` 是什麼？

- `OWNER_ID`：`users.id`，backend 內部的 owner primary key；
- `DECK_UUID`：既有 `learning_decks.id`；
- `DRY_RUN_UUID`：已核准且零 rejected rows 的 `import_runs.id`。

Owner 和 deck 必須在 database 中已存在，而且 deck 必須屬於同一個 owner、尚未 archived，並且
`target_language` 相符。Importer 不會自動建立另一個 deck。

### `SNAPSHOT_TIMESTAMP` 是哪個欄位？

它是 `import_runs.snapshot_captured_at`，代表這份 frozen CSV snapshot 的擷取時間，不是 CLI 的
執行時間，也不是 `created_at` 或 `completed_at`。Confirmed command 必須傳入與 dry run 完全相同
的 timestamp。

### Exact replay 和 duplicate prevention 有什麼不同？

Exact replay 是 application behavior：相同 approved dry run 再執行時，程式找到 completed run
並回傳既有結果，不更新 timestamps 或 versions。

Database unique constraints 則是最後一道防線：即使同時啟動兩個 process，也不能建立兩組
mappings 或 cards。兩者一起處理正常 retry 與 concurrency race。

### 為什麼 commit 成功後還可能看到 CLI failure？

Database commit 和本地 JSON report write 不是同一個 atomic operation。可能發生 database 已
成功 commit，但 process 在輸出 report 前中斷。對 client 而言結果不明確，但 database 裡的
`confirmed_import_runs` 已留下 completed record；使用完全相同的 command retry，即可安全恢復，
不會重新建立 cards。

### Reconciliation report 裡的 `"archived": true` 是什麼意思？

在 sample 的 `fields` 裡，boolean 表示「這個欄位的 comparison passed」。因此
`"archived": true` 不是說該 card 已 archived；實際 archived card 數量要看
`actual_counts.archived_cards`，本次結果是 `0`。

## 7. 常用 commands 與意思

以下指令都從 `apps/api/` 執行。

### 啟動 PostgreSQL

```bash
docker compose up -d --wait postgres
```

- `docker compose`：使用 repository 的 Compose 設定；
- `up`：建立並啟動 service；
- `-d`：在背景執行；
- `--wait`：等到 health check 通過；
- `postgres`：只啟動 PostgreSQL service。

### 檢查 container 狀態

```bash
docker compose ps
```

### 執行 migrations

```bash
uv run alembic upgrade head
uv run alembic current
```

第一行把 schema 升級到最新 revision；第二行顯示 database 目前套用的 revision。Issue #23 的
revision 是 `20260910_0005`。

### 進入 PostgreSQL CLI

```bash
docker compose exec postgres \
  psql -U english_learning -d english_learning
```

意思是：在正在執行的 `postgres` container 裡啟動 `psql`，使用 database role
`english_learning` 連線到同名 database。

進入 `psql` 後可使用：

```sql
SELECT id FROM users ORDER BY id;

SELECT id, owner_id, title, target_language, archived_at
FROM learning_decks
ORDER BY created_at;

SELECT id, owner_id, deck_id, snapshot_captured_at, rejected_rows
FROM import_runs
ORDER BY created_at DESC;
```

離開 `psql`：

```text
\q
```

一般產品資料應優先透過 authenticated API 建立，讓 backend 執行 identity、ownership 與
validation。直接使用 `psql` 比較適合 local inspection、migration verification 或受控的
operational work，不應成為日常產品寫入方式。

### 執行 final dry run

```bash
uv run python -m app.imports \
  --csv legacy-google-sheet-cutover-v1.csv \
  --source-namespace legacy-google-sheet-cutover-v1 \
  --owner-id OWNER_ID \
  --deck-id DECK_UUID \
  --target-language en \
  --snapshot-captured-at SNAPSHOT_TIMESTAMP \
  --report /tmp/legacy-google-sheet-dry-run.json
```

檢查 report，確認 `rejected_rows` 為 `0`，再記下 report 中的 dry-run ID。

### 執行 confirmed import

```bash
uv run python -m app.confirmed_imports \
  --csv legacy-google-sheet-cutover-v1.csv \
  --approved-dry-run-id DRY_RUN_UUID \
  --owner-id OWNER_ID \
  --deck-id DECK_UUID \
  --source-namespace legacy-google-sheet-cutover-v1 \
  --target-language en \
  --snapshot-captured-at SNAPSHOT_TIMESTAMP \
  --validator-version csv-dry-run-v1 \
  --report /tmp/legacy-google-sheet-confirmed-import.json \
  --reconciliation-report /tmp/legacy-google-sheet-reconciliation.json
```

Exit codes：

- `0`：apply/replay 與 reconciliation 成功；
- `2`：validation、apply、database 或 report write 失敗；
- `3`：apply 已存在，但 reconciliation 發現 mismatch。

相同 command 可以用於 unchanged replay。不要拿修改後的 CSV 搭配舊的 dry-run ID。

### Verification commands

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv lock --check
git diff --check
```

## 8. Docker volume、backup 與 source of truth

一般的 `docker compose stop` 或 `docker compose down` 不會刪除 named PostgreSQL volume，所以
下次啟動後資料通常仍在。以下操作可能刪除資料：

- `docker compose down -v`；
- 手動刪除 Docker volume；
- 執行會清除 volumes 的 Docker prune；
- 重設或移除 Docker／OrbStack 儲存空間。

因此「volume 還在」不等於「已有安全 backup」。在 rollback window 內，應把 PostgreSQL dump
存放在 repository 外的受限位置，並驗證 restore 流程。私人 CSV、operational reports 與 dump
都不應 commit。

目前各階段的 authority：

| 階段 | Authoritative system |
| --- | --- |
| freeze 前 | Legacy Google Sheet |
| dry run 到 verified import | Frozen CSV 是 migration evidence；Sheet 仍是 runtime source |
| import 成功但 frontend 尚未 cut over | PostgreSQL 只是 verified migration candidate |
| 未來明確完成 frontend cutover 後 | PostgreSQL |

不要建立長期 dual writes，也不要在 confirmed import 後繼續用 CSV 自動同步、刪除或 archive
PostgreSQL cards。Cutover 後的 edits 應走正常 product API。

## 9. 本次驗證結果

修正 Issue #22 的三個 source diagnostics 後，final dry run 達到零 rejected rows，接著成功套用
596-row private snapshot。Sanitized reconciliation 結果為：

- 596 eligible rows；
- 596 cards；
- 596 source mappings；
- 596 fresh review states；
- 184 tags；
- 885 card/tag associations；
- 0 archived cards；
- 0 review batches；
- 0 review events；
- expected 與 actual counts 全部一致；
- 所有 comparison checks 都是 `true`；
- diagnostic codes 為空。

完整 backend suite 也通過 220 tests；Ruff lint/format、`uv lock --check`、migration cycle 與
whitespace checks 通過。這些是 local correctness evidence，不代表 production reliability、
performance、remote CI 或 frontend cutover 已完成。

目前仍未記錄 real private snapshot 的 unchanged replay，以及 backup/restore drill 的 operator
evidence。

## 10. What we've learned

### 1. Idempotency 不是只有「先查詢是否存在」

安全的 exactly-once effect 需要 application replay logic、transaction locking、database unique
constraints 與 durable result record 一起工作。只做 `SELECT` 再 `INSERT` 仍可能在 concurrency
下產生 race condition。

### 2. Transaction boundary 應該對應 business invariant

這次 invariant 不是「一張 card 建立成功」，而是「596 rows 對應的 cards、tags、states 與
mappings 必須成為同一個完整結果」。所以 transaction 應包住整個 bounded migration，而不是
每列各自 commit。

### 3. Dry run 與 confirmed import 是不同責任

Dry run 負責 validation 與 approval evidence；confirmed import 負責重新驗證同一 snapshot 後
產生正式資料。分開後，operator 可以先修正問題，也能避免 validation 還沒完成就寫入產品資料。

### 4. Hash 是 comparison evidence，不是 private content 的替代品

Hashes 可以證明 identity 與 content 是否改變，卻不能用來還原 card。因此 audit tables 可以保持
content-free，而真正的私人內容只在 importer process memory 與正式 product tables 中存在。

### 5. Database constraints 是重要的 security 與 consistency boundary

Composite foreign keys 可以保證 owner、deck、approved item、mapping 與 card 的關係真的一致。
這比只相信 caller 傳入的 IDs 或 application branch 更可靠。

### 6. Commit success 與 client success 不是同一件事

Process 可能在 database commit 後、report write 前失敗。設計 retry 時必須能辨認「已完成但
client 不知道」的狀態，否則 retry 可能產生 duplicates。

### 7. Reconciliation 是 migration 的必要步驟

CLI exit code `0` 不應只表示 SQL 沒丟 exception，還要驗證 counts、ownership、content hashes、
tags、fresh states、samples 與 absence of review history。Migration correctness 必須有可檢查的
post-commit evidence。

### 8. 資料已匯入不等於 source-of-truth 已切換

Source of truth 是 runtime traffic 與 operational policy 的決定，不只是 database 裡已經有資料。
在 frontend 明確改用 PostgreSQL-backed API 之前，不能宣稱 cutover 已完成。

## 11. 我現在應該能簡短說明的版本

> Issue #23 實作了一個 local confirmed-import CLI。它不信任 audit tables 能提供原始內容，而是
> 重新讀取私人 CSV，使用 Issue #22 的 canonicalization 重算 snapshot 與每列 hashes，再與已
> 核准且零 rejected rows 的 dry run 比對。驗證通過後，程式在一個 PostgreSQL transaction 中
> 建立 cards、normalized tags、associations、fresh review states 與 durable mappings，並透過
> locks、unique constraints 和 completed apply record 支援 exact replay 與 concurrency safety。
> Commit 後 reconciliation 再核對 counts、ownership、hashes、states、tags 與 samples。本次
> 596-row snapshot 已在 local database 成功匯入並通過 reconciliation，但 frontend 尚未
> cut over，因此 PostgreSQL 還不是 runtime source of truth。
