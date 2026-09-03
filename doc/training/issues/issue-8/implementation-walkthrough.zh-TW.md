# Issue #8 多語學習 Domain Schema 實作詳解

- 日期：2026-09-03
- Alembic revision：`20260902_0002`
- 驗證資料庫：PostgreSQL 17
- 狀態：schema、migration、constraints、fixtures 與代表性 query plans 已在本機驗證

## 1. 這個 ticket 解決什麼問題

Issue #8 的目標不是只建立幾張 table，而是建立一個由 PostgreSQL 協助維護資料完整性的
多語學習核心。English 與 Japanese 共用同一套資料模型，同時讓資料庫拒絕下列錯誤：

- deck 沒有 owner，或使用不支援的語言；
- confirmed card 沒有有效的 term 或 meaning；
- card、tag、review state 或 review event 跨越 user ownership boundary；
- 同一張 card 同時存在多筆 current review state；
- review scheduling 數值超出允許範圍；
- retry 產生重複的 review batch；
- 同一個 batch 對同一張 card 產生兩筆 event；
- 刪除 parent 後留下失去來源的 learning data 或 review history。

這次實作的核心原則是：backend 仍然負責 business logic，但能由靜態 relational constraint
表達的重要 invariant，也必須由 PostgreSQL 再防守一次。這樣即使未來 backend validation
有 bug、transaction 寫錯，或有人直接執行 SQL，也不會輕易寫入結構上不合法的資料。

## 2. 實作範圍與非範圍

本 ticket 建立八張 domain tables：

1. `users`
2. `learning_decks`
3. `learning_cards`
4. `tags`
5. `learning_card_tags`
6. `review_states`
7. `review_batches`
8. `review_events`

同時完成：

- reversible Alembic migration；
- foreign keys、composite foreign keys、unique constraints 與 check constraints；
- timestamp、version 與 archive rules；
- 明確的 delete behavior；
- English/Japanese 共用 schema 的 SQL fixture；
- PostgreSQL migration 與 constraint integration tests；
- ER diagram；
- 由實際 access patterns 推導的 indexes；
- `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` query-plan tests。

刻意不包含：

- AI draft tables；
- Google Sheets import tables；
- authentication implementation；
- ORM models 與 API routes；
- review service 的 transaction、locking 與 replay response logic。

## 3. 最終 relationship 概觀

```text
users
├── learning_decks
│   └── learning_cards
│       ├── learning_card_tags ── tags
│       ├── review_states        (每張 card 最多一筆 current state)
│       └── review_events
└── review_batches
    └── review_events
```

重要的是，上圖只是 cardinality 的簡化表示。ownership integrity 並不是單靠
`card_id -> learning_cards.id` 這類單欄 FK，而是透過 `(resource_id, owner_id)` composite FK
確認 child 與 parent 的 owner 是同一個 user。

完整圖可參考 [Issue #8 ER diagram](erd.md)。

## 4. 各 table 的設計與 constraints

### 4.1 `users`

`users` 提供系統內穩定的 owner identity。

- `id`：PostgreSQL generated `BIGINT` identity primary key。
- `google_subject`：required、nonblank、globally unique。
- `normalized_email`：required、nonblank，但不是 ownership key。
- `created_at`、`updated_at`：required，並限制 `updated_at >= created_at`。

Google email 可能改變，因此 durable external identity 使用 Google subject，而不是 email。
保留 learning data 的 user 不允許直接 physical delete；相關 FK 使用 `RESTRICT`。

### 4.2 `learning_decks`

每個 deck 必須有 owner，並定義 card 的語言 context。

- `id`：generated UUID primary key。
- `owner_id`：required FK 到 `users.id`。
- `title`：trim 後長度必須為 1-100。
- `target_language`：只允許 `en` 或 `ja`。
- `explanation_language`：只允許 `en`、`ja` 或 `zh-TW`。
- `version >= 1`。
- `archived_at` 若存在，不可早於 `created_at`。
- `updated_at >= created_at`。

除了 primary key，deck 還提供 unique `(id, owner_id)`。UUID `id` 自己其實已經能唯一辨識
deck，但 composite unique key 的目的是讓 child table 可以用 `(deck_id, owner_id)` 建立
composite FK，直接驗證「這個 deck 確實屬於這個 owner」。

Deck creation 的 retry metadata 是 optional pair：

- `creation_idempotency_key`
- `creation_request_hash`

兩者必須同時為 null 或同時有值；有 key 時，key 在同一個 owner 下必須唯一。hash 也不能是
blank。這讓未來 API 能辨別同一次 retry 與相同 key、不同 payload 的衝突。

### 4.3 `learning_cards`

`learning_cards` 只保存已確認的 learning content，不保存 incomplete AI output。

必要欄位：

- `id`：generated UUID primary key；
- `deck_id`：required；
- `owner_id`：required；
- `term`：trim 後長度 1-255；
- `meaning`：trim 後長度 1-2000；
- timestamps 與 positive version。

Ownership 使用：

```text
learning_cards(deck_id, owner_id)
    -> learning_decks(id, owner_id)
```

因此，即使 `deck_id` 和 `owner_id` 各自都存在，只要它們不是同一個 owned deck pair，
PostgreSQL 就會拒絕 insert/update。

English 與 Japanese 共用的 optional fields 包含：

- `reading`
- `pronunciation`
- `romanization`
- `target_language_definition`
- `part_of_speech`
- `part_of_speech_detail`
- `note`
- `supplementary_note`
- `learned_on`

Card 不重複保存 `target_language`。它從 required deck relationship 推導語言，避免 deck 與
card 的 language 欄位互相矛盾。普通 `CHECK` 無法查詢另一張 table，因此像「Japanese card
一定要有 reading」這種跨 table、language-aware 規則，未來仍由 backend 在讀取 deck 後驗證。

其他 card constraints：

- nullable text 欄位只要有值，trim 後就不能空白，且必須符合長度上限；
- `synonyms`、`antonyms` 預設為空 array，各最多 20 筆且不可包含 null element；
- `part_of_speech` 只允許定義好的 enum-like values；
- `part_of_speech = 'other'` 時必須提供 detail；
- creation idempotency key/hash 必須成對，key 在每位 owner 下唯一；
- archive time 與 update time 不可早於對應的基準時間。

### 4.4 為什麼沒有 `card_examples`

我們討論過三個方案：

1. 獨立的 `card_examples` table；
2. 在 card 使用 JSONB 保存多個 examples；
3. 在 `learning_cards` 直接保存一個 example。

最終選擇第三個方案：

- `example_sentence`
- `example_translation`
- `example_source`

目前產品只需要一個 example，而且 example 沒有獨立 endpoint、ordering、archive state、
version 或 lifecycle。因此拆成 child table 會先引入尚未需要的一對多關係與 join。

JSONB 雖然可以容納多筆 examples，但目前反而會降低 field-level relational constraints 的
清晰度。使用 columns 可以直接限制每個欄位的 nullability、blank content 與長度。

目前 constraint 規定 translation 或 source 出現時，必須同時有 nonblank sentence。接受的
tradeoff 是：如果未來真的需要多個 examples、獨立排序或來源 mapping，就要新增 migration
與 API contract；到那時 `card_examples` 才有充分理由。

### 4.5 `tags`

Tag 是 owner-scoped resource：

- `id`：generated UUID primary key；
- `owner_id`：required FK；
- `display_name`：trim 後長度 1-50；
- `normalized_name`：trim 後長度 1-100；
- `version >= 1`，timestamps 必須有正確順序。

Unique `(owner_id, normalized_name)` 代表：

- 不同 users 可以使用相同的 tag 名稱；
- 同一個 user 不可建立兩個 normalization 後相同的 tags。

Tags 也提供 unique `(id, owner_id)`，供 association composite FK 使用。

### 4.6 `learning_card_tags`

這張 association table 實作 cards 與 tags 的 many-to-many relationship。

- primary key `(card_id, tag_id)` 防止同一個 tag 重複 attach 到同一張 card；
- `(card_id, owner_id) -> learning_cards(id, owner_id)`；
- `(tag_id, owner_id) -> tags(id, owner_id)`。

兩個 composite FKs 共同保證 association 中的 owner 同時擁有 card 和 tag。只建立獨立的
`card_id` FK、`tag_id` FK、`owner_id` FK 並不足夠，因為三個 ID 都可能各自存在，但組合仍然
跨 user。

Delete behavior 是不對稱且刻意的：

- physical delete tag：`CASCADE` 刪除 association rows；
- 不會刪除 learning card；
- physical delete card：有 association 時使用 `RESTRICT`；正常產品流程應先 archive card。

「每張 card 最多 20 個 tags」沒有用普通 `CHECK` 實作，因為它需要計算多筆 rows，而且在
concurrency 下必須 lock card 後 count-and-insert。這是未來 service transaction 的責任。

### 4.7 `review_states`

`review_states` 表示每張 card 目前唯一的 scheduling state。

最重要的選擇是直接使用 `card_id` 作為 primary key，而不是新增沒有 domain 意義的
`review_state_id`。這同時表達：

- review state 的 identity 就是 card；
- 每張 card 最多只能有一筆 current state。

Ownership 使用 `(card_id, owner_id) -> learning_cards(id, owner_id)`，防止 cross-owner state。

下列 scheduling 欄位都是 `NOT NULL`，而且沒有 database defaults：

- `review_stage`
- `ease_factor`
- `interval_days`
- `next_review_at`
- `version`

這是刻意讓 backend 明確提供 scheduling algorithm 的結果，而不是 PostgreSQL 靜默猜一組
預設值。少一個欄位，insert 就會失敗。

範圍 constraints：

- `review_stage BETWEEN 1 AND 5`；
- `ease_factor BETWEEN 1.30 AND 2.50`；
- `interval_days >= 0`；
- `version >= 1`；
- `next_review_at` required；
- `last_reviewed_at` nullable；若有值，`next_review_at >= last_reviewed_at`。

新的 card 尚未複習過，所以 `last_reviewed_at = NULL` 是合理狀態。`next_review_at` 由 backend
clock 與 scheduling algorithm 建立，但資料庫仍檢查它存在且沒有違反基本時間順序。

### 4.8 `review_batches`

一個 review request 可以包含 1-10 個 card decisions，因此 retry identity 屬於整個 command，
不是單一 event。`review_batches` 保存：

- `id`：generated UUID；
- `owner_id`；
- required `idempotency_key`；
- required nonblank `request_hash`；
- backend authoritative `reviewed_at`；
- nonblank `algorithm_version`；
- `item_count BETWEEN 1 AND 10`；
- `created_at`。

Unique `(owner_id, idempotency_key)` 提供 per-user retry safety。相同 owner 重送同一個 key 時，
不能建立第二個 batch。未來 service 還需要比較 request hash：相同 key、相同 hash 回傳原結果；
相同 key、不同 hash 回 conflict。

Batch 也提供 unique `(id, owner_id)`，供 event 驗證 owned batch relationship。

### 4.9 `review_events`

`review_events` 是 retained history。每筆 event 同時引用 owned batch 與 owned card：

```text
review_events(batch_id, owner_id)
    -> review_batches(id, owner_id)

review_events(card_id, owner_id)
    -> learning_cards(id, owner_id)
```

這兩個 composite FKs 防止 event 使用另一個 user 的 batch 或 card。

每筆 event 保存完整的 transition snapshot：

- decision 與 mapped quality；
- previous/resulting stage；
- previous/resulting ease factor；
- previous/resulting interval；
- previous/resulting last-review time；
- previous/resulting next-review time；
- previous/resulting version；
- algorithm version；
- authoritative `reviewed_at`。

這樣做比只保存 resulting values 更容易回答：「當時從什麼狀態，經過哪個 algorithm version，
轉換成什麼狀態？」

Database checks 包含：

- decision 只允許 `no`、`no_a_bit`、`yes_a_bit`、`yes`；
- quality 只允許 `0`、`2`、`3`、`5`；
- decision 與 quality mapping 必須一致；
- before/after stage、ease、interval 都在有效範圍；
- `resulting_version = previous_version + 1`；
- previous schedule 與 resulting schedule 時間順序合法；
- review time 不可早於 previous last-review time；
- `resulting_last_reviewed_at = reviewed_at`。

Unique `(batch_id, card_id)` 防止同一個 batch 對同一張 card 建立兩個 events。History 使用
restrictive FK，避免 card 或 batch 被 physical delete 後留下無法解釋的 event。

## 5. 兩個 ID 都存在，為什麼還不夠

這是本 ticket 最重要的 ownership learning point。

假設資料庫中存在：

```text
owner 1 owns card A
owner 2 owns card B
```

如果 child row 只有兩個獨立 foreign keys：

```text
owner_id -> users.id
card_id  -> learning_cards.id
```

那麼 `(owner_id = 1, card_id = B)` 仍可能通過，因為 owner 1 存在、card B 也存在。資料庫只驗證
各欄值，不知道這個 combination 是否代表真實 owned relationship。

Composite FK：

```text
(card_id, owner_id) -> learning_cards(id, owner_id)
```

會一次驗證完整 pair。Parent 因此必須提供 matching primary key 或 unique constraint；這就是
為什麼 `learning_cards`、`learning_decks`、`tags`、`review_batches` 除了自己的 primary key，
還暴露 `(id, owner_id)` unique key。

這些看似重複的 `owner_id` 不是 accidental denormalization，而是可由 database enforce 的
ownership invariant。

## 6. Indexes 如何從 access patterns 推導

我們沒有先猜「可能有用」的 indexes，而是先命名 query，再設計 column order。

| Access pattern | Index | 為什麼這樣排序 |
| --- | --- | --- |
| 列出 deck 中 active cards，最新優先 | `(deck_id, created_at DESC, id DESC) WHERE archived_at IS NULL` | deck equality 放最前面；時間排序；ID 作穩定 tie-breaker；partial predicate 排除 archived rows |
| 依 owner 與語言列出 decks | `(owner_id, target_language, archived_at)` | 對應 owner、language 與 active filter |
| 依 tag 反查 cards | `(tag_id, card_id)` | association PK 從 `card_id` 開始，不能有效支援反方向查詢 |
| 取得 user 到期 cards | `(owner_id, next_review_at, card_id)` | owner equality、due-time range、stable card tie-breaker |
| user review history | `(owner_id, reviewed_at DESC, id DESC)` | owner-scoped reverse chronology |
| single-card review history | `(card_id, reviewed_at DESC, id DESC)` | card-scoped reverse chronology |
| 重建 batch response | `(batch_id, id)` | batch equality 與 deterministic event order |

Query-plan test 建立以下 deterministic dataset：

- 100 users；
- 2,000 decks；
- 40,000 cards；
- 100 tags 與 40,000 associations；
- 40,000 review states；
- 4,000 ten-item batches；
- 40,000 review events；選定的 card 有 10 筆 history。

接著執行 `ANALYZE`，再用：

```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
```

實際執行七種 query。Test 會遞迴讀取 JSON plan tree，確認 PostgreSQL 17 自然選到預期 index，
沒有關閉 sequential scan 或強迫 planner 使用某種方法。

這個結果只證明在此 PostgreSQL version 與資料分布下，indexes 能被 intended query 使用。
它不是 production latency、throughput 或未來 planner choice 的保證，因此沒有把 cost、time、
buffer count 或完整 node tree 寫成 brittle assertion。

## 7. Alembic `upgrade()` 與 `downgrade()`

Migration file 同時包含：

- `upgrade()`：從前一個 revision 前進到本 revision；
- `downgrade()`：從本 revision 回到它宣告的 previous revision。

本 ticket 的關係是：

```text
20260901_0001  --upgrade-->    20260902_0002
20260901_0001  <--downgrade--  20260902_0002
```

`upgrade()` 依 parent-to-child 順序建立 tables、constraints 與 indexes。`downgrade()` 則以相反的
dependency order 先移除 events、states、associations 等 children，最後才移除 cards、decks
與 users，避免 FK 阻擋。

如果 upgrade/downgrade logic 不匹配，可能發生：

- downgrade 忘記刪除 index、constraint 或 table；
- downgrade 順序錯誤，被 FK 阻擋；
- re-upgrade 因殘留 object 而失敗；
- revision marker 正確，但實際 schema 不正確；
- data transformation 無法還原或造成資料損失。

因此 integration test 實際執行：

```text
empty database
-> upgrade head
-> downgrade to 20260901_0001
-> upgrade head
-> downgrade base
-> upgrade head
```

但 migration cycle 成功仍不代表兩個 functions 是數學上的完全 inverse。測試只會發現它有
assert 的 properties。現在 previous revision 是 empty domain baseline，所以 downgrade 後只剩
`alembic_version` 是合理 assertion；未來 previous revision 若已有 tables 或 data，就需要逐一
驗證重要 columns、constraints、indexes、defaults 與 data transformations。

## 8. Development 時修改 migration 是否可以

這個 revision 尚未發布且 development database 沒有正式資料，所以開發期間可以持續修改同一個
migration file，再執行 downgrade/re-upgrade 驗證。這避免在 schema 尚未穩定時製造大量 correction
migrations。

如果 revision 已經被其他環境或正式資料庫套用，就不應任意改寫 migration history；應新增下一個
revision，讓所有環境能從共同歷史安全前進。

Development database 的常用命令，在 `apps/api/` 執行：

```bash
uv run alembic current
uv run alembic downgrade -1
uv run alembic upgrade head
```

執行前要先從 repository root 啟動 PostgreSQL：

```bash
docker compose up -d --wait postgres
```

Development migration 會修改 local development database；integration tests 使用的是另外建立的
temporary databases，兩者不要混淆。

## 9. PostgreSQL integration test 的 temporary database model

### 9.1 `temporary_database_url`

`apps/api/tests/integration/conftest.py` 中的 `temporary_database_url` fixture 會：

1. 產生唯一 database name，例如 `api_test_<random UUID>`；
2. 使用 admin connection 執行 `CREATE DATABASE`；
3. 把 temporary database URL yield 給 test；
4. test 結束後執行 `DROP DATABASE`。

它擁有的是 temporary database 的 lifecycle。

### 9.2 `migrated_database_engine`

`migrated_database_engine` 依賴 `temporary_database_url`，接著：

1. 設定 test environment 與 temporary `DATABASE_URL`；
2. 對該空 database 執行 `alembic upgrade head`；
3. 建立並 yield SQLAlchemy `Engine`；
4. test 結束時 dispose engine。

`Engine` 不是 database 本身，也不是一條永遠開著的 connection；它是建立 connections 與管理
connection pool 的 factory。Test 使用 `engine.begin()` 或 `engine.connect()` 取得短期 connection。

Fixtures 預設是 function-scoped，所以每個 test function 都得到自己的 isolated database。某個
test insert 的 user、deck 或 card 不會留到下一個 test。

### 9.3 為什麼 migration lifecycle test 不直接用 migrated engine

`test_migrations.py` 必須從完全 empty database 開始，並自己控制 upgrade 與 downgrade。因此它直接
使用 `temporary_database_url`，而不是取得已經 `upgrade head` 的 `migrated_database_engine`。

一般 constraint test 則想直接測試最新 schema，所以使用 `migrated_database_engine` 比較方便。

## 10. SQL fixture 是什麼，資料會去哪裡

`apps/api/tests/fixtures/multilingual_learning_domain.sql` 是 deterministic synthetic test data，
涵蓋所有八張 tables：

- 同一位 owner 的 English 與 Japanese decks/cards；
- 兩種語言共用 core card model；
- reusable tags；
- current review states；
- 一個包含兩張 cards 的 review batch；
- 與 current states 對應的 before/after review events。

Integration test 讀取 SQL file，並在 `migrated_database_engine` 指向的 temporary database transaction
中執行它。因此資料只存在於該 test database，test teardown 後整個 database 被刪除，不會寫入
local development database。

這裡的 fixture 是「為測試準備的固定資料」。它不是 production seed、Google Sheets importer，
也不是要由開發者手動匯入 development database 的初始化檔。

Test 也刻意載入第二次，確認 duplicate user identity 被 unique constraint 拒絕，而不是靜默覆蓋或
合併意外資料。

## 11. Pytest 如何找到並執行 tests

Pytest 預設會尋找：

- 符合 `test_*.py` 或 `*_test.py` 的 files；
- files 中名稱以 `test_` 開頭的 functions/methods。

例如 `test_query_plans.py` 中真正的 pytest entry 是：

```python
def test_named_access_patterns_use_their_deliberate_indexes(
    migrated_database_engine: Engine,
) -> None:
    ...
```

`seed_representative_dataset()`、`explain()`、`used_indexes()` 等不是 tests，因為名稱沒有以
`test_` 開頭；它們是由 test entry 呼叫的 helpers。

執行整個 query-plan file：

```bash
RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest \
  tests/integration/test_query_plans.py -q
```

只執行該 test function：

```bash
RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest \
  tests/integration/test_query_plans.py::test_named_access_patterns_use_their_deliberate_indexes -q
```

如果沒有設定 `RUN_POSTGRES_INTEGRATION_TESTS=1`，這些 opt-in PostgreSQL tests 會被 skip。

## 12. Migration tests 與 constraint tests 在測什麼

### Migration lifecycle

`test_migrations.py` 驗證：

- 空 PostgreSQL database 可以 upgrade 到 head；
- expected tables 存在；
- Alembic revision marker 正確；
- 可以 downgrade 到 baseline 與 base；
- 可以再次 upgrade。

### Users 與 decks

`test_users_and_learning_decks.py` 驗證：

- English/Japanese decks 使用同一張 table；
- owner required 且必須存在；
- supported languages；
- user identity、content、timestamps、versions；
- creation retry pairing 與 uniqueness；
- retained deck 阻擋 owner physical deletion。

### Cards

`test_learning_cards.py` 驗證：

- English/Japanese confirmed cards 使用同一張 table；
- owned deck composite relationship；
- required/nonblank term 與 meaning；
- optional multilingual fields 與 embedded example dependencies；
- arrays、part of speech、retry、versions、timestamps；
- retained card 阻擋 deck physical deletion；
- active-card index definition。

### Tags 與 associations

`test_tags.py` 驗證：

- tag uniqueness 是 per-owner，不是 global；
- tag content 與 owner constraints；
- card/tag 兩側的 cross-owner combinations 都被拒絕；
- duplicate attachment 被拒絕；
- tag delete 只 cascade association；
- tagged card 不可直接 physical delete；
- reverse tag index definition。

### Review state

`test_review_states.py` 驗證：

- scheduling fields 必須由 caller 明確提供；
- 每張 card 最多一筆 state；
- state owner 必須等於 card owner；
- stage、ease、interval、version ranges；
- last/next review ordering；
- current state 存在時不可直接 physical delete card；
- due-review index definition。

### Review history

`test_review_history.py` 驗證：

- valid batch/event transition；
- required command metadata；
- batch owner 必須存在；
- idempotency key per-owner uniqueness；
- invalid batch metadata；
- cross-owner batch/card event rejection；
- complete transition snapshot required；
- one event per batch/card；
- invalid transition ranges、mapping、versions 與 times；
- retained history 阻擋 batch/card physical deletion；
- history/reconstruction index definitions。

### Complete multilingual fixture

`test_multilingual_domain_fixture.py` 驗證：

- fixture 的 exact table counts；
- English/Japanese optional fields 共用 card model；
- tags 可跨 language decks 重複使用；
- batch membership；
- fixture 中 event resulting state 與 current state 一致；
- duplicate fixture load 被拒絕。

### Query plans

`test_query_plans.py` 驗證七個 named access patterns 在 representative dataset 上使用 intended
indexes。這比只查 `pg_indexes` 確認 index definition 更進一步，但仍不是 production benchmark。

## 13. Database 可以保證什麼，不能保證什麼

### 已由 PostgreSQL 保證

- required fields 與基本內容長度；
- supported language values；
- FK existence；
- composite ownership pairs；
- unique identities 與 duplicate prevention；
- one current state per card；
- scheduling range 與單 row 內的時間順序；
- event before/after snapshot 的局部一致性；
- explicit physical deletion behavior。

### 仍需未來 backend/service transaction 保證

- authentication token verification 與 API authorization；
- 根據 deck language 要求 Japanese-specific fields；
- 完整 scheduling algorithm transition 是否正確，而不只是數值範圍合法；
- lock current state、檢查 version、更新 state、寫入 event 的 atomicity；
- batch `item_count` 是否等於最後 event count；
- idempotency replay 時比較 request hash 並回傳相同 response；
- review events 的 application-level no-update/no-delete contract；
- 每張 card 最多 20 個 tags 的 concurrent-safe enforcement；
- array element 的 trimming、normalization 與 normalized uniqueness。

這個區分很重要：constraint 應處理 row-local、relational、可靜態表達的 invariant；需要讀取多筆
rows、計算演算法、處理 concurrency 或 authorization context 的規則，則放在 explicit backend
transaction。

## 14. 討論中的主要疑問與最後結論

### 「Incomplete card 是否可以為未來 AI draft 使用？」

不使用 confirmed card table 保存 incomplete AI content。AI output 是 untrusted、editable draft，
未來應放在獨立 `card_drafts` model。只有經 user confirmation 與 backend revalidation 後，才能建立
required term/meaning 的 `learning_cards` row。

### 「Owner ID 和 card ID 應該足以辨識 card？」

辨識 resource 時 `card_id` 足夠；驗證 ownership relationship 時，兩個獨立 IDs 不足夠。必須用
composite FK 一次檢查 `(card_id, owner_id)` 是否為 parent table 中的合法 pair。

### 「是否要為 review state 增加自己的 ID？」

不需要。Current state 與 card 是 one-to-zero-or-one，直接以 `card_id` 作 PK 最能表達 domain identity，
也自然防止同一張 card 有兩筆 current states。

### 「Scheduling fields 缺少任何一個都應被拒絕？」

是。Stage、ease、interval、next-review time 與 version 都是 required，且沒有 DB defaults。Backend
必須明確提供計算結果。`NOT NULL` 處理 missing，`CHECK` 處理 present-but-invalid。

### 「Last reviewed 可以是 null，next review 由 backend 建立？」

是。新 card 尚未 review，所以 last-review time nullable；next-review time required，由 backend 建立，
PostgreSQL 再檢查基本時間順序。

### 「Deck 為了 composite FK 也需要 ID 嗎？」

Deck 本來就有 UUID `id` primary key。為了讓 card 引用 owned pair，另外建立 unique `(id, owner_id)`。
Composite FK 的 parent columns 必須由 PK 或 unique constraint 保證唯一。

### 「可以用 `length(trim(content)) > 0` 防止 blank 嗎？」

可以，概念完全正確。實作使用 PostgreSQL 的 `char_length(btrim(content)) > 0` 或
`BETWEEN 1 AND max`。`NOT NULL` 只能拒絕 null，不能拒絕 `''` 或 `'   '`；trim 後長度 check 才能
拒絕 blank content。

### 「Card 的 `deck_id` 可以 nullable 嗎？」

這個想法在討論中出現過，但最終 schema 沒有採用。`learning_cards.deck_id` 是 `NOT NULL`，因為 card
需要從 deck 推導 target/explanation language，也需要明確 ownership。若允許 null，就必須另外決定
card language、ownership context 與未歸檔 card 的 list behavior，會破壞目前 invariant。

### 「同名 tags 是否允許？」

最後規則是：不同 owners 可以有相同 normalized name，同一 owner 不可以。`tags.id` 提供 resource
identity，unique `(owner_id, normalized_name)` 防止單一 user 產生語意上重複的 tag。

### 「刪除 tag 時 association 怎麼辦？」

Tag-side FK 使用 `ON DELETE CASCADE`，所以相關 `learning_card_tags` 自動刪除；card 不會被刪除。
Card-side FK 使用 `RESTRICT`，維持 archive-first learning data lifecycle。

### 「Idempotency key 應放在每個 event 嗎？」

不放。Retry 的單位是一次包含 1-10 個 decisions 的 review command，所以 key 放在
`review_batches`，並以 `(owner_id, idempotency_key)` 唯一。Events 透過 batch 被 grouped。

### 「Event 的 before/after values 能完全檢查 transition 嗎？」

資料庫可檢查 ranges、version +1、decision/quality mapping 與時間順序，但無法用普通 row check 證明
完整 scheduling algorithm。Backend 必須在 transaction 中 lock current state、驗證 expected version、
計算結果、update state 並 insert event；這些動作要一起 commit 或一起 rollback。

### 「Migration tests 應該在 migration 前還是後執行？」

不需要手動先替 test database migration。Test fixture 會先建立 empty database，再自動執行
`alembic upgrade head`，之後 test 才 insert prerequisite data 並驗證 schema。Migration lifecycle test
則自己控制 before/after revisions。

### 「Fixture SQL 是否會被寫入 local database？」

不會。Integration test 把它載入 temporary database，test 結束後 database 被 drop。若手動用其他
command 對 development URL 執行 SQL，才會影響 local database；測試本身沒有這樣做。

### 「可以用 UI 看 Docker 中的 PostgreSQL 嗎？」

可以。DBeaver、TablePlus、DataGrip、pgAdmin 等工具都能連到 Compose 暴露的 local PostgreSQL。
UI 看到的是你選擇連線的 database：development database 與 pytest 每次臨時建立的
`api_test_<...>` database 不同，而且 temporary database 只在 test 執行期間短暫存在。

### 「Pytest 執行哪一個 function？」

Pytest 依命名 convention discovery。File 符合 test filename pattern，而且真正的 test function 以
`test_` 開頭。其他不以 `test_` 開頭的 functions 是 helpers，不會被獨立收集。

## 15. 最終 acceptance criteria 對照

| Acceptance criterion | 最終結果與證據 |
| --- | --- |
| Deck always has owner and supported target language | required owner FK、language checks、deck integration tests |
| Confirmed card has required term and meaning | `NOT NULL` + trimmed length checks + card tests |
| At most one current review state per card | `review_states.card_id` primary key + duplicate-state test |
| Events cannot cross user/card ownership | owned batch/card composite FKs + cross-owner tests |
| Invalid scheduling values rejected | state/event range、version、time checks + parametrized tests |
| English/Japanese fixtures use same core model | complete multilingual SQL fixture + fixture integration test |
| Migration and constraint tests demonstrate invariants | reversible lifecycle test + focused PostgreSQL constraint suites |
| Indexes justified by named access patterns | seven documented query shapes + executed JSON plan assertions |

## 16. 驗證結果與 commands

在 `apps/api/` 執行完整 backend verification：

```bash
RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv lock --check
```

已驗證結果：

- `103 passed, 1 existing upstream warning`；
- Ruff lint passed；
- Ruff formatting passed；
- lockfile check passed；
- whitespace check passed；
- development database 與 temporary database 都完成 upgrade、baseline downgrade、re-upgrade。

唯一 warning 來自既有的 FastAPI/Starlette `TestClient` dependency deprecation，不是 Issue #8 schema
failure。

## 17. 面試或 learning checkpoint 可以如何說明

一個精簡但完整的說法是：

> 我為 English 與 Japanese 建立共用的 PostgreSQL learning domain，將共同的 ownership、card、tag
> 與 review behavior 正規化在同一套 tables，語言特有欄位則保持 nullable。重要 ownership
> relationship 使用 `(resource_id, owner_id)` composite foreign keys，避免兩個各自存在的 IDs 被
> 組成 cross-user row。Current review state 直接以 `card_id` 為 primary key；history 則保存完整
> before/after snapshot，retry identity 放在 command-level review batch。Database 負責 required、
> range、uniqueness、ownership 與時間順序等靜態 invariants；完整 scheduling algorithm、locking、
> replay response 與 atomic state/event update 保留給 backend transaction。Indexes 全部從七個命名
> access patterns 推導，並用 PostgreSQL 17 的 executed JSON plans 驗證 planner 確實選用。

被拒絕的 schema alternative 可以選擇說明：

- 分開 English/Japanese card tables：會重複 ownership、tags、review state/history 與 API behavior；
- 獨立 `card_examples`：目前只有一個且沒有獨立 lifecycle，現在拆表是 premature cardinality；
- 只用獨立 FKs：無法證明 owner/resource combination 合法；
- 額外 `review_state_id`：沒有 domain 意義，也不能像 `card_id` PK 一樣直接表達 one current state；
- 每個 event 重複 idempotency key：retry identity 實際屬於整個 review command/batch。

## 18. 主要檔案

- Migration：`apps/api/migrations/versions/20260902_0002_add_multilingual_learning_domain.py`
- Shared PostgreSQL fixtures：`apps/api/tests/integration/conftest.py`
- Complete SQL fixture：`apps/api/tests/fixtures/multilingual_learning_domain.sql`
- Migration lifecycle tests：`apps/api/tests/integration/test_migrations.py`
- Domain constraint tests：`apps/api/tests/integration/test_users_and_learning_decks.py`、
  `test_learning_cards.py`、`test_tags.py`、`test_review_states.py`、`test_review_history.py`
- Fixture test：`apps/api/tests/integration/test_multilingual_domain_fixture.py`
- Query-plan test：`apps/api/tests/integration/test_query_plans.py`
- ER diagram：[erd.md](erd.md)
- Query-plan report：[query-plans.md](query-plans.md)
- Implementation design：[design.md](design.md)

