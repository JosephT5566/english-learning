# Issue #22 學習筆記：唯讀 CSV 匯入驗證

## 1. Ticket 目標

這個 ticket 為 legacy Google Sheet CSV 到共用多語系 PostgreSQL model 的一次性遷移，建立安全的驗證邊界。

最重要的區別是：

```text
Dry run 驗證 != 正式匯入卡片
```

Issue #22 只負責驗證及解釋來源資料，不會建立學習卡片或複習歷史。後續 ticket 才會執行具備 transaction 保護的 confirmed import。

## 2. 這個 ticket 解決了哪些問題

### 2.1 不可信任的 CSV 資料不能直接成為 confirmed content

CSV 可能包含缺少欄位、重複 ID、錯誤日期、不支援的值、過時的排程資料或不一致的格式。若直接寫入 `learning_cards`，可能在沒有察覺的情況下建立錯誤的產品資料。

新的驗證邊界會把每個 cell 當成不可信任的文字，逐一驗證，並將每一列分類為：

- `accepted`：資料有效，不需要會改變語意的修復；
- `repaired`：經過有文件記錄、結果確定的轉換後有效；
- `rejected`：無法安全地成為 confirmed card。

### 2.2 全部 21 個 legacy fields 都有明確處理結果

| Legacy field | 目的欄位或明確處理方式 |
| --- | --- |
| `id` | Hash 過的 source identity；不會重用為 card UUID |
| `lessonDate` | 使用 `Asia/Taipei` 日期的 `learning_cards.learned_on` |
| `content` | 必填的 `learning_cards.term` |
| `type` | Canonical part of speech，或以 `other` 保存原始分類細節 |
| `phonics` | Nullable `learning_cards.pronunciation` |
| `chineseExplain` | 必填的 `learning_cards.meaning` |
| `engExplain` | Nullable `learning_cards.target_language_definition` |
| `synonyms` | 正規化且保留順序的 synonyms array |
| `antonyms` | 正規化且保留順序的 antonyms array |
| `tags` | 未來建立 owned tags 與 card/tag associations |
| `note` | Nullable `learning_cards.note` |
| `supplementary` | Nullable `learning_cards.supplementary_note` |
| `example` | Nullable `learning_cards.example_sentence` |
| `status` | Active 或 archived；空白時修復為 active |
| `reviewStage` | 驗證並產生診斷，之後重設 |
| `easeFactor` | 驗證並產生診斷，之後重設 |
| `intervalDays` | 驗證並產生診斷，之後重設 |
| `lastReview` | 驗證並產生診斷，之後重設 |
| `nextReview` | 驗證並產生診斷，之後重設 |
| `createdDate` | Card 建立時間；無效或空白時使用固定 snapshot 時間 |
| `overdueDays` | 只用於診斷；到期狀態仍由 backend 動態計算 |

### 2.3 穩定 identity 不再依賴 row position

CSV 和 Sheet 的 row number 不穩定，因為插入或排序資料後，row number 就會改變。因此穩定 identity 由以下資料產生：

```text
source namespace + 經過 trim 且大小寫敏感的 NFC legacy ID
```

結果會儲存成 SHA-256 hash。重新排序不會改變 source identity；但是兩列若使用相同的 legacy ID，兩列都會因 duplicate 而被拒絕。

### 2.4 Canonical hashing 能區分來源變更與 card content 變更

實作中使用兩種相關但用途不同的 hash：

- `source_snapshot_hash`：識別完整的 canonical import package，包含語言、固定 snapshot 時間、headers 與 rows。
- `content_hash`：識別未來會成為 card 與 fresh review state 的 canonical destination candidate。

這個區別很重要。修改一個不會匯入的 legacy scheduling value，會改變 snapshot audit，但不會改變 mapped card 的 `content_hash`。

### 2.5 重複執行 dry run 具備 idempotency

Replay identity 包含：

```text
owner + source namespace + snapshot hash + validator version
```

使用完全相同的資料再次執行 dry run 時，會回傳既有的 `import_runs`，而不會建立重複 audit run。來源內容改變時會建立新的 run；只要 legacy ID 沒有改變，該列的 source identity 仍會相同。

### 2.6 Ownership 必須由 backend 驗證

CLI 需要已存在的 `OWNER_ID` 與 `DECK_UUID`。PostgreSQL 和 import service 會驗證以下 composite ownership relationship：

```text
(deck_id, owner_id) -> learning_decks(id, owner_id)
```

即使 deck ID 本身有效，只要它屬於另一位 user，對目前的 owner 仍然是無效的。Deck language 也必須符合 import 指定的 target language。

### 2.7 Private learning content 不會出現在 diagnostics

私人 CSV 已明確加入 Git ignore。持久化及輸出的報告只包含：

- row number；
- source identity hash；
- content hash；
- field name；
- diagnostic code 與 severity；
- counts 與 truncation state。

報告不包含 term、meaning、definition、tags、notes、examples、rejected values、tokens、credentials 或 database URLs。未知 header names 只會以 aggregate diagnostic 回報，不會直接顯示原始名稱。

## 3. 為什麼需要 `import_runs` 和 `import_items`

這兩張表是 migration audit tables，不是日常產品功能使用的 tables。

### `import_runs`

一筆資料代表一個 canonical CSV dry run，記錄：

- owner 與 destination deck；
- source namespace；
- snapshot 與 validator versions；
- target language；
- accepted、repaired 與 rejected counts；
- 安全的 run-level diagnostics；
- replay 與完成資訊。

### `import_items`

一筆資料代表某次 import run 裡的一個 CSV data row，記錄：

- CSV row number；
- stable source identity hash；
- canonical content hash；
- accepted、repaired 或 rejected outcome；
- 有數量上限且安全的 diagnostics。

`import_items` 沒有足夠的內容可以建立 learning card。Confirmed importer 必須重新讀取私人 CSV、重新產生完全相同的 canonical candidates，並拿結果與通過 dry run 的 hashes 比對。

目前的 relationships：

```text
users
  └── learning_decks
        └── import_runs
              └── import_items
```

目前刻意沒有 `import_items -> learning_cards` relationship。下一個 ticket 必須為 apply phase 增加具有 unique constraint 的 source-identity-to-card mapping。

## 4. Fresh scheduling policy

之後正式匯入的 cards 都會從 backend 標準的 fresh review state 開始。Legacy Sheet 的 scheduling fields 仍會被解析和診斷，但不會成為 authoritative state。

原因包括：

- legacy browser 負責計算 state transitions；
- 部分 scheduling fields 已經過時或屬於 derived values；
- legacy update flow 沒有一致地更新所有 scheduling fields；
- 可以接受重新複習全部 cards。

因此 dry run 不會建立 `review_states`、`review_batches` 或 `review_events`。Confirmed-import ticket 會在建立每張 card 的同一個 transaction 裡，同時建立一筆 fresh `review_state`。

## 5. Unicode 與 collection 決策

### Display 與 content values

使用 trim 後的 Unicode NFC。NFC 會合併等價的 Unicode sequences，但不會執行範圍更廣、可能改變學習內容語意的 compatibility transformations。

### Source IDs

使用 trim 後、大小寫敏感的 NFC。只在英文字母大小寫不同的 IDs，不會被系統自動視為同一筆 legacy record。

### Tags 與 related-word comparison

Comparison keys 使用 NFKC 加 Unicode case-folding，display text 則保留 NFC。這能讓大小寫或字元寬度不同但邏輯上等價的值，共用相同 identity。

### Bounded input

Validator 接受 UTF-8 與帶有 BOM 的 UTF-8，並限制 file size、row count、cell length、collection length、item length 與 diagnostic count。

## 6. 完成的實作

- 在 `apps/api/app/imports.py` 建立本地一次性 CSV validator 與 CLI。
- 建立 Alembic revision `20260909_0004`，新增 `import_runs` 與 `import_items`。
- 建立 deterministic、sanitized English 與 Japanese fixtures。
- Unit tests 覆蓋全部 field mappings、headers、required values、languages、dates、ranges、duplicates、Unicode、arrays/tags、schedule reset、hashing 與 private-content exclusion。
- PostgreSQL tests 覆蓋 ownership/language conflicts、unchanged replay、changed snapshots、persisted diagnostics 與 zero learning-data mutations。
- 建立可提交的 sanitized dry-run report。
- 更新 architecture、decisions、project memory、evidence 與 weekly log。

## 7. 驗證結果

完成並持久化的私人 dry run 結果：

```text
596 total rows
11 accepted
585 repaired
0 rejected
```

Database 檢查結果：

```text
learning_cards = 0
review_states  = 0
review_events  = 0
review_batches = 0
```

這是 Issue #22 預期的結果：validation 與 audit persistence 已成功，但 confirmed learning data 尚未建立。

Verification evidence：

- complete backend suite：187 tests passed；
- Ruff lint passed；
- Ruff formatting passed；
- uv lock check passed；
- PostgreSQL migration upgrade、downgrade 與 re-upgrade passed；
- whitespace check passed；
- 仍有一個原本就存在的 upstream FastAPI `TestClient` warning。

## 8. 使用過的 commands 與用途

### Git branch commands

```bash
git switch -c issue-22-csv-dry-run
```

建立新 branch 並切換過去。`-c` 代表 create。

```bash
git branch --show-current
git status --short --branch
```

顯示目前 branch，以及簡短的 working-tree status。

### PostgreSQL container

```bash
docker compose up -d --wait postgres
```

在背景啟動 PostgreSQL service，並等待 health check 通過。

```bash
docker compose ps
```

顯示 service、image、status 與 exposed port。

### Python dependencies

以下 commands 從 `apps/api/` 執行：

```bash
uv sync --locked
```

根據已 commit 的 lockfile 建立或更新 Python environment。`--locked` 會拒絕在沒有明確更新 lockfile 的情況下改變 dependency resolution。

### Alembic migrations

```bash
uv run alembic upgrade head
```

將所有尚未套用的 migrations 執行到最新 revision。

```bash
uv run alembic current
```

顯示 database 目前套用的 migration revision。

```bash
uv run alembic downgrade -1
uv run alembic upgrade head
```

先回復一個 revision，再重新套用最新 migration。這組 commands 用來證明 Issue #22 的 schema change 在 local development 可以被還原並重新套用。

### 啟動 FastAPI

```bash
uv run uvicorn app.main:create_app --factory
```

啟動 local API。`--factory` 告訴 Uvicorn 呼叫 `create_app()`，而不是把它當成已經建立完成的 application object。

### 取得 Google ID token

先透過 frontend 登入，再於 browser developer console 執行：

```javascript
copy(localStorage.getItem('gid_id_token'))
```

這會複製目前 frontend 的 ID token，但不把 token 顯示出來。

在 macOS 上，可將 clipboard 內容存入暫時的 shell variable：

```bash
GOOGLE_ID_TOKEN="$(pbpaste)"
```

在不顯示 token 的情況下檢查格式：

```bash
printf 'Token length: %d characters\n' "${#GOOGLE_ID_TOKEN}"
[[ "$GOOGLE_ID_TOKEN" == eyJ*.*.* ]] && echo "JWT format detected"
```

下面的 command 也能在不顯示輸入內容的情況下讀取 token，但它會等待使用者貼上資料並按下 Enter：

```bash
read -s "GOOGLE_ID_TOKEN?Paste Google ID token: "
echo
```

不要在空白 shell prompt 直接貼上 token，否則 zsh 會嘗試把它當成 command 執行。

### 取得真正的 owner

```bash
curl -s http://127.0.0.1:8000/v1/me \
  -H "Authorization: Bearer $GOOGLE_ID_TOKEN" |
  jq
```

`curl` 會發出 HTTP request。Authorization header 會提供 ID token。`/v1/me` 驗證 token、建立或重用 internal user，然後回傳 database `OWNER_ID`。

`OWNER_ID` 只在特定 database 裡有效。它不是 Google subject、email、OAuth client ID 或 ID token。

### 建立 target deck

```bash
curl -s -X POST http://127.0.0.1:8000/v1/decks \
  -H "Authorization: Bearer $GOOGLE_ID_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "English",
    "target_language": "en",
    "explanation_language": "zh-TW"
  }' |
  tee /tmp/english-deck.json |
  jq
```

- `-X POST`：選擇 HTTP method；
- `-H`：加入 HTTP header；
- `-d`：傳送 JSON request body；
- `tee`：保存 response，同時繼續傳給下一個 command；
- `jq`：格式化及查詢 JSON。

取得自動產生的 deck UUID：

```bash
jq -r '.id' /tmp/english-deck.json
```

`DECK_UUID` 用來識別 destination deck，而且必須屬於指定 owner。

### 執行 dry run

```bash
uv run python -m app.imports \
  --csv legacy-google-sheet-cutover-v1.csv \
  --source-namespace legacy-google-sheet-cutover-v1 \
  --owner-id OWNER_ID \
  --deck-id DECK_UUID \
  --target-language en \
  --snapshot-captured-at 'CSV_EXPORT_TIME+08:00' \
  --report /tmp/legacy-google-sheet-dry-run.json
```

- `python -m app.imports`：執行 module 的 CLI entry point；
- `--source-namespace`：為這個一次性 source 指定 durable name；
- `--snapshot-captured-at`：固定 time-dependent mapping 與 hashing；
- `--report`：將 private operational report 保留在 `/tmp`，避免被 commit。

這個 command 只會寫入 audit data，不會匯入 cards。

### 查看安全的 report

```bash
jq '{
  run_id,
  replayed,
  total_rows,
  accepted_rows,
  repaired_rows,
  rejected_rows,
  diagnostic_count
}' /tmp/legacy-google-sheet-dry-run.json
```

只顯示 rejected row locations 與安全 diagnostics：

```bash
jq '.items[]
  | select(.outcome == "rejected")
  | {row_number, source_identity_hash, diagnostics}' \
  /tmp/legacy-google-sheet-dry-run.json
```

### 安全地查看 PostgreSQL

```bash
docker compose exec postgres \
  psql -U english_learning -d english_learning \
  -c "SELECT owner_id, id AS deck_id, target_language FROM learning_decks;"
```

`docker compose exec` 會在 PostgreSQL container 內執行 command。`psql` 是 PostgreSQL command-line client，`-c` 代表執行一個 SQL statement。

### 執行 verification

```bash
uv run pytest tests/unit -q
RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest tests/integration -q
uv run ruff check .
uv run ruff format --check .
uv lock --check
```

- `pytest`：執行 tests；`-q` 使用簡短輸出；
- environment flag：啟用需要真實 PostgreSQL 的 tests；
- `ruff check`：執行 Python linting；
- `ruff format --check`：只驗證 formatting，不修改檔案；
- `uv lock --check`：驗證 dependency declarations 與 lockfile 是否一致。

### 清除敏感的 shell state

```bash
unset GOOGLE_ID_TOKEN
pbcopy </dev/null
```

`unset` 會移除暫時的 shell variable；`pbcopy </dev/null` 會清空 macOS clipboard。

## 9. 我們學到什麼

### Validation 是獨立的 product state

不可信任的 source rows 不等於 learning cards。Dry run 只建立「可能成為 cards 的資料」之驗證證據，而 confirmed import 是另一個需要明確授權的 state transition。

### Idempotency 同時需要 identity 與 content

Stable source identity 回答「這是哪一筆 legacy record？」；content hash 回答「它是不是仍然是同一個版本？」兩者缺一不可，才能區分 retry 與 edit。

### Row number 適合診斷，但不適合作為 identifier

Row number 能幫助人找到錯誤資料，但 sorting 或 inserting rows 都會改變它。Durable identity 必須來自 source namespace 與 legacy ID。

### Canonicalization 必須經過設計，不能依賴預設行為

Unicode normalization、whitespace trimming、case-folding、array splitting、duplicate removal、date timezone interpretation 與 fallback timestamps 都可能改變 hash 和 uniqueness。處理順序必須被明確記錄並測試。

### Database ownership 比 caller intent 更可靠

收到看似合理的 `owner_id` 或 `deck_id` 並不足夠。Backend 必須查詢 composite owned resource，或依賴 composite foreign key，防止不同 users 的 IDs 被組合使用。

### Audit tables 不應複製 private domain content

Hashes 與 allowlisted diagnostic codes 能提供 replay 和 debugging evidence，又不需要建立 term、definition、note 與 example 的第二份私人資料。

### Dry run 成功不代表 migration 已完成

Issue #22 完成時，dry run 只證明 CSV 可以被安全驗證，當時仍有 3 個 rejected rows，並不代表 `learning_cards` 已經建立。這些 source diagnostics 後來已修正，Issue #23 也已完成 596-row confirmed import 與 reconciliation；但 frontend 尚未 cut over，所以 PostgreSQL 目前仍只是 verified migration candidate，產品 runtime source of truth 尚未改變。

### Local-to-cloud transfer 需要乾淨的 boundary

如果匯入後的 local database 要成為 cloud PostgreSQL 的基礎，應使用專用且乾淨的 cutover database，而不是日常 development database。先執行 migrations、驗證 ownership 與 counts、排除 test fixtures，再透過經過審查的 PostgreSQL dump/restore 流程搬移。完成 reconciliation 後，才能讓 cloud database 成為 source of truth。

## 10. 下一個 ticket

Confirmed-import ticket 應該：

1. 再次讀取私人 CSV。
2. 重新產生已核准的 snapshot 與 canonical content hashes。
3. 要求 `rejected_rows = 0`。
4. 新增 unique `source_identity_hash -> learning_card.id` applied mapping。
5. 對這份有明確上限的 596-row dataset，在一個 transaction 裡建立 cards、reusable tags、associations 與 fresh review states。
6. Replay unchanged import 時不能建立 duplicate cards。
7. 拒絕未預期的 source changes，不可默默套用。
8. 任一 row 失敗時，必須 rollback 所有 mutations。
9. Commit 後核對 source、card、tag 與 review-state counts。
10. 記錄 rollback window，以及最終停用 CSV/import tooling 的方式。

> 2026-09-10 update: Issue #23 已實作上述 confirmed-import boundary。修正後的 final
> zero-rejection snapshot 已在 local database 匯入並通過 reconciliation：596 cards、596
> mappings、596 fresh review states、184 tags、885 associations，且沒有建立 review batches 或
> review events。私人 CSV 與 operational reports 仍保持 untracked；frontend cutover 尚未發生。

在 Issue #22 checkpoint 時，不應手動將 CSV rows 寫入 `learning_cards`；後續寫入必須經過
Issue #23 的 transaction、mapping 與 reconciliation boundary。
