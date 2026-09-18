# Issue #27 學習筆記：從請求日誌到可執行的告警

這份筆記解釋 #27 的設計與實作。它是學習文件，不代表整張 ticket 的所有驗收條件都已完成。截至 2026-09-18，PR #43 已合併；操作人回報完成 candidate 與切換流量後的 smoke test，唯讀 Cloud Run 查詢確認新版 revision 承接 100% 流量。正式 5xx 告警已啟用，但尚未觀察到符合條件的事件或驗證該告警的郵件送達。正式資料庫獨立備份則依專案成本考量延後。

## Chapter 1. 這張 ticket 要解決什麼

以前 API 已會在錯誤回應提供 `X-Request-ID`，但單靠這個 ID，操作人員仍無法在後端找到對應的操作與失敗類型。#27 的第一個目標是讓「使用者回報某個失敗」可以被追查，同時避免把 token、私人卡片內容或資料庫連線字串寫進日誌。

後續工作包含 review/import 結果訊號、告警與 runbook、還原演練及事故演練。這些是不同的驗證邊界：一筆 401 測試郵件成功，不等於 5xx 告警已觸發；合成資料還原成功，也不等於正式 Neon 資料有獨立備份。總覽見 [Issue #27 記錄](README.md)。

## Chapter 2. Structured log 的資料流

```text
HTTP request
  -> FastAPI request middleware 建立伺服器端 UUID
  -> endpoint / error handler 處理請求
  -> response: X-Request-ID（錯誤 body 也含相同 ID）
  -> stdout: 一行 JSON 的 http_request_completed
  -> Cloud Run / Cloud Logging 解析為 jsonPayload
  -> Cloud Monitoring LogMatch 政策比對
  -> 符合條件時開 incident 並通知 Email Channel
```

核心程式在 [request_context.py](../../../../apps/api/app/request_context.py)。每個經過這個 middleware 的請求，由伺服器產生新的 UUID；不把客戶端送來的 `X-Request-ID` 當成可信的追蹤 ID。完成時輸出一行 JSON，讓 Cloud Logging 能按欄位查詢，而不必解析自由格式文字。CORS preflight 會先由外層 middleware 回答，因此不在這種完成事件內。

錯誤回應也帶同一個 ID，見 [errors.py](../../../../apps/api/app/errors.py)。查詢時用 `jsonPayload.request_id` 找對應的後端事件。這是**關聯 ID**，不是使用者身份或授權憑證；真正的 AuthN/AuthZ 仍由後端執行。

這裡有兩種要分開看的日誌：我們的 JSON **application event** 與 Cloud Run 自動產生的 **platform request log**。關閉 Uvicorn access log 只減少應用程式自己的原始 URL 輸出，不會停止 Cloud Run platform log。候選版本的 platform log 仍有 `httpRequest.requestUrl` 欄位；目前尚未套用排除規則。證據見 [candidate-verification.md](candidate-verification.md)。

## Chapter 3. 為什麼選這些欄位

`http_request_completed` 只包含固定、可預期的欄位：

| 欄位          | 用途                     | 取值邊界                                                     |
| ------------- | ------------------------ | ------------------------------------------------------------ |
| `event`       | 區分事件種類             | 固定為 `http_request_completed`                              |
| `request_id`  | 對照回應與日誌           | 伺服器產生的 UUID；不拿它當 metric label                     |
| `method`      | 知道操作的 HTTP 類別     | 限定方法清單，其他為 `OTHER`                                 |
| `route`       | 定位 API 操作            | 路由模板，例如 `/v1/cards/{card_id}`；未匹配時為 `unmatched` |
| `status_code` | 判斷 HTTP 結果           | 整數狀態碼                                                   |
| `duration_ms` | 初步觀察單次耗時         | 單調時鐘計算並四捨五入為毫秒；不是延遲 SLO                   |
| `outcome`     | 按失敗類別查詢           | 固定詞彙，例如 `authentication`、`database`、`unexpected`    |
| `error_code`  | 指向安全、穩定的錯誤原因 | 只有已設定的錯誤才出現，例如 `database_unavailable`          |

`route` 使用模板而不是實際路徑，避免 card ID 等資料混進日誌，也避免每個不同 ID 變成新的統計維度。事件不放 query string、request/response body、bearer token、idempotency key、Google subject/email、私人卡片文字、SQL 或原始 exception。這是**允許清單策略**：只寫明確需要的欄位，而不是先記錄所有內容再嘗試遮蔽。

分類邏輯在 `_failure_class()`：成功為 `success`；已知登入錯誤為 `authentication`；`database_unavailable` 為 `database`；409 為 `conflict`；422 或 `invalid_request` 為 `validation`；其餘 5xx 為 `unexpected`；其他 4xx 為 `client_error`。分類也看 `error_code`，不只看狀態碼。例如 identity provider 不可用即使回 503，仍會歸到 `authentication`，不會觸發目前只匹配 `database`／`unexpected` 的第一個告警。這是告警範圍的取捨，後續應依觀察結果決定是否另設 Auth 服務故障訊號。

範例（合成資料）：

```json
{
  "event": "http_request_completed",
  "request_id": "00000000-0000-4000-8000-000000000001",
  "method": "GET",
  "route": "/health/ready",
  "status_code": 503,
  "duration_ms": 12,
  "outcome": "database",
  "error_code": "database_unavailable"
}
```

## Chapter 4. Codebase 中的重要改動

| 位置                                                                                                                                                                                    | #27 的改動與原因                                                                                                                                                                                           |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [request_context.py](../../../../apps/api/app/request_context.py)                                                                                                                       | 加入 allowlist JSON 完成事件、失敗分類、review 結果事件；未預期的 endpoint exception 轉成安全 `internal_error` 回應，避免原始 exception 內容出現在伺服器錯誤路徑。日誌輸出失敗不會把已完成的請求改成失敗。 |
| [errors.py](../../../../apps/api/app/errors.py)                                                                                                                                         | 建立安全錯誤回應時把穩定 `error_code` 放到 request state，供完成事件使用。既有回應與 header 仍有相同 request ID。                                                                                          |
| [health.py](../../../../apps/api/app/health.py)                                                                                                                                         | `/health/ready` 資料庫檢查失敗時標記 `database_unavailable`，讓 503 事件歸到 `database`。`/health/live` 與 readiness 可協助區分程序存活與依賴故障。                                                        |
| [serve.py](../../../../apps/api/app/serve.py)                                                                                                                                           | 停用 Uvicorn access log，避免另外輸出原始 URL；Cloud Run platform request log 仍要獨立管理。                                                                                                               |
| [database.py](../../../../apps/api/app/database.py)、[reviews.py](../../../../apps/api/app/reviews.py)                                                                                  | review endpoint 先標記 `committed` 或 `replayed`，交易 `commit()` 成功後才輸出 `review_submission_completed`。失敗或 rollback 不會記成成功。                                                               |
| [auth.py](../../../../apps/api/app/auth.py)、[reads.py](../../../../apps/api/app/reads.py)、[writes.py](../../../../apps/api/app/writes.py)                                             | 資料庫 session dependency 改為 function scope，讓 commit 在回應送出前完成；避免客戶端先看到 200、之後 commit 才失敗。                                                                                      |
| [import_events.py](../../../../apps/api/app/import_events.py)、[imports.py](../../../../apps/api/app/imports.py)、[confirmed_imports.py](../../../../apps/api/app/confirmed_imports.py) | 本機匯入命令完成時輸出固定欄位事件，區分驗證、DB apply、reconciliation、報表寫入與 replay。這是 CLI 訊號，不會自動出現在 Cloud Run HTTP request log。                                                      |

review 事件只記 `event`、`request_id`、`outcome`、`item_count`。即使 route 已計算完結果，仍要等 transaction commit 才能稱為 `committed`；如果只是相同 idempotency key 的精確重播，就標為 `replayed`。這個區分可避免操作人員把重播當成新的寫入。[PostgreSQL integration tests](../../../../apps/api/tests/integration/test_review_submission_transactions.py) 覆蓋成功、重播、commit 失敗及 rollback 後不產生假成功事件。

import CLI 事件則記 `operation`、`outcome`、`phase`、`database_committed`、`reports_written`、`replayed`。最重要的是：**DB commit 成功後，報表仍可能失敗**。這時 `database_committed=true`，不能因為命令最後回錯就重新匯入一次；要先對照持久化紀錄並使用既有 replay/reconciliation 流程。事件不含來源路徑、owner ID、卡片內容或 hash。[單元測試](../../../../apps/api/tests/unit/test_import_events.py) 驗證了這些邊界。

## Chapter 5. 告警如何選條件

第一個正式政策是 **log-based alert**，而不是以 metric 數值超過某個比例觸發。因為目前流量小且沒有可靠的生產基線，先用「一筆值得調查的安全 5xx 事件」作為暫定條件，避免捏造錯誤率或 SLO。要計算一段時間內的事件數量，才需要額外的 log-based metric 或其他指標。參考 [Google 的 log alert 說明](https://cloud.google.com/logging/docs/alerting/log-based-alerts)。

正式 filter：

```text
resource.type="cloud_run_revision"
resource.labels.service_name="english-learning-api"
log_id("run.googleapis.com/stdout")
jsonPayload.event="http_request_completed"
jsonPayload.status_code>=500
jsonPayload.outcome=("database" OR "unexpected")
```

政策已啟用並連到操作人的 Email Channel，暫定兩次通知至少間隔 30 分鐘，告警內容附有 [runbook](failure-alert.md)。401、404、409、422 或單純打錯 API 路徑不會觸發它。先前用**另一個暫時的 401 政策**驗證過「新 log → incident → email」路徑；操作人回報收到郵件並能找到 alert，測試政策已刪除。正式 5xx 政策的條件及郵件送達仍未用符合條件的事件驗證。詳見 [notification-test.md](notification-test.md) 與 [failure-alert.md](failure-alert.md)。

告警的意義是「請檢查」，不是「自動判定根因」。runbook 會先看 request ID、route、穩定錯誤碼，再比對 `/health/live`、`/health/ready`、Cloud Run revision 與 Neon。若 review 寫入結果不明，必須用原 idempotency key 和完全相同的 payload 重試，不能產生新 key。

## Chapter 6. 較大型專案常見的開發習慣

以下是從這個小型專案抽出的通用做法，**不表示本專案已有大型流量或完整 observability 平台**。

1. **先定義事件契約，再做 dashboard。** 固定事件名稱、欄位與分類，讓後續查詢與告警有穩定語意。新增欄位要考慮隱私、基數與相容性。
2. **將追蹤與授權分開。** Request ID 幫助定位操作，但資料讀寫仍須經身分驗證、owner 過濾與交易約束；不能拿「找得到日誌」當作授權證明。
3. **把成功訊號放在真正的成功邊界後面。** 資料庫 commit、外部報表寫入與通知送達是不同階段。各自記錄結果，避免「HTTP 200 但交易失敗」或「DB 已寫入但 CLI 報錯」造成錯誤判斷。
4. **把不同失敗類別分開處理。** 401 可能是普通未登入使用者，409 可能是預期的並發衝突，DB 503 或未預期 500 才是這個第一告警要通知的事件。日後要按實際流量調整，而不是靠猜測設定門檻。
5. **先做最小可回復的發佈。** 先讓 CI、候選 revision、健康檢查、人工 smoke、流量切換與回滾各有可觀察的界線；不要把「部署成功」等同「正式流量已安全切換」。
6. **用分層驗證與證據等級。** 單元測試證明分類與遮蔽；PostgreSQL integration test 證明交易；候選版日誌查詢證明部署解析；操作人回報郵件是通知收件證據。每一層都不能代替下一層。
7. **讓 runbook 跟告警一起維護。** 告警要有 owner、觸發條件、通知間隔與第一步排查動作。政策設定後要讀回確認；連結也要避免因分支刪除而失效。
8. **把資料最小化當成整條路徑的事。** 應用程式 JSON 安全，不代表 framework、平台與其他 sink 的日誌也安全。要分別檢查保留時間、URL、查詢字串與任何外部消費者。

## Chapter 7. 我們實際驗證了什麼

| 邊界             | 已有證據                                                                                                                                                                  | 仍不能宣稱                                                         |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| 本機 request log | [測試](../../../../apps/api/tests/unit/test_request_context.py)涵蓋 ID 相等、分類、路由模板、假 token/URL/exception 不洩漏，以及日誌輸出失敗不改變回應                    | 所有框架與平台日誌都已去識別                                       |
| review 與 import | PostgreSQL integration test 驗證 review commit/replay/rollback；import 單元測試驗證 commit 後報表失敗的事件語意                                                           | CLI 事件是 Cloud Run HTTP metric，或實際操作人 import 已被遠端觀察 |
| 發布與流量       | 第一個 candidate 的 401 回應 ID 對到唯一 JSON 事件；操作人回報新 candidate 與流量切換後的 smoke test；唯讀查詢確認新版 revision 承接 100% 流量並產生 parsed request event | 操作人 smoke 的精確請求、回應 ID 與私有路徑結果已獨立檢查          |
| email 路徑       | 操作人回報收到暫時 401 告警郵件，並能查到 incident；暫時政策已刪除                                                                                                        | 正式 5xx 政策已寄出郵件                                            |
| 第一個 5xx 告警  | 政策已啟用；讀回確認 filter、Email Channel、間隔與 runbook；查詢時近一小時沒有匹配事件                                                                                    | 實際故障一定會按預期觸發、準時通知                                 |
| 事故演練         | [本機模擬](incident-exercise.md)顯示 readiness 503、liveness 200、request ID 關聯與恢復                                                                                   | 真實 Neon 故障、Cloud Run 中斷或正式事故恢復                       |
| 備份還原         | [合成資料](backup-restore.md)從 `pg_dump` 還原到隔離 PostgreSQL 17，schema、數量及代表性紀錄相符                                                                          | 正式 Neon 資料已有獨立 GCS 備份或定期排程                          |

操作人回報完成 candidate 與切換後的 smoke test，但未提供結果細節與 request 證據；筆記不據此推論具體 endpoint 或成功率。流量切換由 Cloud Run 唯讀查詢獨立確認。詳見 [發布驗證記錄](candidate-verification.md)。

## Chapter 8. 現在的限制與下一步

- 正式 revision 已輸出這版 JSON 事件；仍可用一筆操作人回報的 production 回應 ID 查詢 stdout，完成回應與日誌的直接對照。
- 正式 5xx 條件還需要一筆明確標記的安全測試事件，或等待自然發生的匹配事件來驗證通知；不要為了測試而讓 Neon 或正式 API 故障。
- Cloud Run platform request log 仍有 raw URL；先確認正式新版 application event 可查，再評估只排除該服務 platform request log 的狹窄規則。既有 `_Default` 保留資料不會因新排除規則自動消失。
- Request event 可供查詢狀態與單次耗時，但本 ticket 尚未建立完整 dashboard、可靠的流量基線或 DB pool 使用率告警。review/import 事件目前也尚未經正式操作流量觀察。
- 使用者選擇因成本暫緩 Neon-to-GCS 獨立備份與排程。隔離還原演練使用合成資料，原本的正式資料可還原驗收條件因此仍是明確例外。

## What we learned

1. **可診斷性從資料契約開始。** 一筆小而固定的 JSON 事件，加上回應中的相同 request ID，比大量自由格式文字更容易安全追查。
2. **觀測事件必須反映已發生的事。** `committed` 只能在 commit 成功後輸出；`database_committed=true` 不應被後續報表失敗抹掉。
3. **測試要說明自己證明的邊界。** 401 郵件證明通知路徑可用；它不會證明 5xx filter 正確觸發。本機 readiness 演練也不是正式事故。
4. **隱私需要跨層檢查。** 我們控制 application log 的欄位，但 Cloud Run platform log 仍包含 URL。不能因為其中一層安全就認為整條日誌管線安全。
5. **低流量服務也需要可執行的第一個告警。** 先用暫定的單筆 5xx 事件與操作人 runbook，日後根據真實事件量調整；不要編造 SLO 或預先建一整套複雜平台。
6. **營運文件要寫出未完成的部分。** 流量已切換，但 5xx 郵件驗證、platform log 保留決策和獨立正式備份仍有明確的下一步或例外，不能因為政策已建立就把 #27 標為全部完成。
