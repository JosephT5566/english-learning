# english-learning：尚未完成的 e2e 測試

跨 issue 的清單。每項標來源 issue 與證據位置；完成後移到「已完成」並附 PR。

## 待完成

| #   | 應補的 e2e 測試                                                                                | 目前替代做法                      | 來源      | 證據                                                                                       |
| --- | ---------------------------------------------------------------------------------------------- | --------------------------------- | --------- | ------------------------------------------------------------------------------------------ |
| 1   | 助理串流：前端接真後端（HTTP 路由 + Postgres + RLS）的完整 SSE 流程                            | Playwright 用假的 SSE fixture     | #87 / #91 | `tests/browser/assistant-flow.spec.ts`                                                     |
| 2   | SSE 心跳：規劃期間經真實 HTTP 路由送出 `: ping`，前端照常顯示回覆                              | HeartbeatHarness 直接驅動串流程式 | #91       | `apps/api/tests/integration/test_assistant_sse_http.py:461`（分支 issue-91-sse-heartbeat） |
| 3   | 慢客戶端（背壓）情境下心跳不越過 deadline，走真實 HTTP 層                                      | harness 變體測試                  | #91       | 同檔 `:707`                                                                                |
| 4   | 部署到 Cloud Run 後，經真實 proxy 的長時間規劃串流不斷線，且 25 秒 deadline 先於 30 秒上限結束 | 無（只有本機測試）                | #91       | `deploy/cloud-run/release.sh:99`、`apps/api/app/config.py:141`                             |

## 已完成

（尚無）
