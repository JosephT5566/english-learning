# english-learning：尚未完成的 e2e 測試

跨 issue 的清單。每項標來源 issue 與證據位置；完成後移到「已完成」並附 PR。

## 待完成

| #   | 應補的 e2e 測試                                                                                                           | 目前替代做法                                     | 來源            | 證據                                                                                                                |
| --- | ------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ | --------------- | ------------------------------------------------------------------------------------------------------------------- |
| 1   | 助理串流：前端接真後端（HTTP 路由 + Postgres + RLS）的完整 SSE 流程，含 `parts.v1` 的 `part` 事件                         | Playwright 用假的 SSE fixture                    | #87 / #91 / #95 | `tests/browser/assistant-flow.spec.ts:186`                                                                          |
| 2   | SSE 心跳：規劃期間經真實 HTTP 路由送出 `: ping`，前端照常顯示回覆                                                         | HeartbeatHarness 直接驅動串流程式                | #91             | `apps/api/tests/integration/test_assistant_sse_http.py:461`（分支 issue-91-sse-heartbeat）                          |
| 3   | 慢客戶端（背壓）情境下心跳不越過 deadline，走真實 HTTP 層                                                                 | harness 變體測試                                 | #91             | 同檔 `:707`                                                                                                         |
| 4   | 部署到 Cloud Run 後，經真實 proxy 的長時間規劃串流不斷線，且 25 秒 deadline 先於 30 秒上限結束                            | 無（只有本機測試）                               | #91             | `deploy/cloud-run/release.sh:99`、`apps/api/app/config.py:141`                                                      |
| 5   | 大型 `part` frame 經 Cloud Run / proxy 不被緩衝，且先於第一個 `delta` 到達                                                | 無（只有本機 ASGI/HTTP 測試）                    | #95             | `apps/api/tests/unit/test_assistant_card_parts.py:128`、`apps/api/tests/integration/test_assistant_sse_http.py:738` |
| 6   | 真實 Vertex 執行在工具成功後送出 `card_list` part                                                                         | 所有測試都使用 scripted provider                 | #95             | `apps/api/tests/unit/test_assistant_card_parts.py:36`、`apps/api/tests/integration/test_assistant_sse_http.py:738`  |
| 7   | 部署順序：新前端送 `capabilities` 到舊 API 會得到 422（推論：`extra="forbid"`）；驗證 fallback 或後端先部署，影響 #96/#98 | 由舊版嚴格模型推論，尚未驗證跨版本部署           | #95             | `apps/api/app/assistant/routes.py:42`、`apps/api/tests/unit/test_assistant_card_parts.py:240`                       |
| 8   | 頁面實際呈現 `card_list`，延至 #98                                                                                        | 只有 parser callback 測試，頁面未啟用 capability | #95             | `tests/frontend/assistant-stream-client.test.ts:121`、`src/routes/assistant/+page.svelte:206`                       |

## 已完成

（尚無）

## Issue #91 middleware regression coverage, 2026-11-10

`apps/api/tests/unit/test_assistant_transport_deadline.py` now drives `create_app()`
with the real request-ID, CORS and error-handler stack, a synthetic SSE endpoint,
fake preparation and a gated outer ASGI send. It checks a blocked planning heartbeat,
a heartbeat-disabled control and a blocked non-heartbeat delta. Each case requires
exactly one terminal event and final `more_body: False` within the deadline plus
terminal grace and scheduling slack. This partly covers items 2 and 3 above.

These tests do not exercise real uvicorn sockets, the authenticated PostgreSQL/RLS
assistant route, browser rendering, Cloud Run or proxies. Items 1 through 4 remain
open; this is ASGI middleware coverage, not end-to-end HTTP deployment evidence.
