# Ticket 26：Cloud Run 與 Neon 部署筆記

最後更新：2026-09-14

這份筆記整理 Ticket 26 實作與部署時做出的選擇、已完成的操作，以及後續 release
應遵守的安全界線。Repository 內可以驗證的是 container、release script、GitHub Actions
與 runbook；Cloud Run、Neon 和資料搬移結果則是本次由操作者回報的實際部署紀錄。

## 我們如何選擇資料庫部署平台

目前正式環境選擇 **Cloud Run `asia-southeast1`（新加坡）搭配 Neon PostgreSQL AWS
Singapore**。Artifact Registry 則放在 `asia-east1`（台灣）；container registry 和執行服務
不必位於同一個 region，因此 release 設定將 `ARTIFACT_REGION` 與 `GCP_REGION` 分開管理。

這個 app 現階段是低流量的個人學習產品，希望每月基礎設施費用維持在 USD 10 以內。
Neon 的 serverless／scale-to-zero 模式較符合目前需求，也能保留標準 PostgreSQL、Alembic
和 SQLAlchemy 的使用方式。Cloud Run 同樣設定 `min instances = 0`、`max instances = 1`，用
冷啟動延遲交換較低的閒置成本。

我們沒有讓 Cloud SQL 與 Neon 同時成為正式資料來源。**Neon 是唯一可寫入的 production
source of truth**；backend 不需要加入 database provider switch，也不做 dual write 或持續同步
Cloud SQL replica。Cloud SQL 仍可在後續作為 GCP 的練習題，但若沒有明確的可用性、法規或
私有網路需求，不增加正式環境的雙資料庫複雜度。

這個選擇也有已接受的限制：Neon Free 與 scale-to-zero 可能有冷啟動、資源與還原時效限制，
初期也沒有私有網路或平台 SLA。獨立備份到 GCS、restore proof、監控與 incident drill 留到
Issue 27 處理。

## 我們新增或擴充了哪些 GitHub Actions

### CI：驗證應用程式與 container contract

`.github/workflows/ci.yml` 會在 pull request 與 `main` push 執行。Frontend job 會產生並核對
API contract、build SvelteKit、執行 frontend tests、type/Svelte checks 與重要 browser flow。
Backend job 則啟動 PostgreSQL 17 service，透過 `uv sync --locked` 安裝鎖定版本，執行 Ruff、
完整 PostgreSQL tests，接著 build production Docker image，最後執行
`apps/api/scripts/verify_container.sh`。

Container verification 不只檢查「能不能 build」，也會驗證非 root runtime、health endpoint、
image 不含 `.env` 或 build-only `uv`，以及 SIGTERM 時能正常完成 application shutdown。這讓同一個
image 在進入 Artifact Registry 前，先通過可重現的 runtime contract。

### Migrate production PostgreSQL：受保護的正式 migration

`.github/workflows/migrate-production.yml` 是手動觸發的 production workflow。操作者必須輸入完全
相符的 `migrate-production`，workflow 使用受保護的 GitHub `production` environment，並以
Workload Identity Federation（OIDC）換取短效 Google Cloud credential，不保存 GCP service
account key，也不直接取得 Neon connection string。

這個 workflow 會依序：

1. 驗證所有必要設定與人工 confirmation。
2. 根據所選 commit 的前 12 碼 SHA 找到不可變的 Artifact Registry image，並確認 image 已存在。
3. 建立或更新單一 task、parallelism 1、retry 0 的 Cloud Run migration job。
4. 由 migration job 的 service account 從 Secret Manager 讀取 direct database URL，執行
   `alembic upgrade head`。
5. 再執行一次 `alembic current --check-heads`，確認所有 Alembic heads 已套用。
6. 呼叫正式 API 的 `/health/ready`，確認 runtime role 仍可連線並執行 readiness query。

`concurrency` 會序列化 production migrations，避免兩個 schema upgrade 同時執行。任何一步失敗
都會停止流程。這個 Action **不會**執行 `pg_dump`、`pg_restore`、Alembic downgrade、部署 app
revision 或切換 traffic；資料搬移與應用程式發布仍是不同的操作邊界。

原本的 `.github/workflows/deploy.yml` 仍負責 SvelteKit frontend 的 GitHub Pages 發布；它不是
Cloud Run API deployment。現階段 API candidate deployment 由 `deploy/cloud-run/release.sh`
處理，production migration 則由上述手動 Action 處理，兩者刻意沒有混成一個無條件自動發布流程。

## 如何把 Docker image 發布到 Artifact Registry

本專案的 registry 是：

```text
asia-east1-docker.pkg.dev/eng-learning-470909/language-learning
```

從 repository root 登入 Google Cloud、選擇 project，並讓 Docker 取得該 registry host 的認證：

```bash
gcloud auth login
gcloud config set project eng-learning-470909
gcloud auth configure-docker asia-east1-docker.pkg.dev
```

接著用 Git commit SHA 當作不可變的 release tag，build `apps/api` 的 Dockerfile 並推送：

```bash
IMAGE="asia-east1-docker.pkg.dev/eng-learning-470909/language-learning/api:$(git rev-parse --short=12 HEAD)"

docker buildx build \
  --platform linux/amd64 \
  --tag "$IMAGE" \
  --push \
  apps/api
```

`linux/amd64` 是 Cloud Run container 的目標架構。發布後可列出 image 與 tag：

```bash
gcloud artifacts docker images list \
  asia-east1-docker.pkg.dev/eng-learning-470909/language-learning/api \
  --include-tags
```

我們不以 `latest` 作為 release 身分。Cloud Run 部署時會把 tag 解析成當下的 image digest，之後即使
推送新的 `latest`，已存在的 revision 也不會自動更新。Commit tag 可以讓 source、image、migration
與 Cloud Run revision 互相追蹤，rollback 時也能明確知道回到哪一版。

Repository 另外提供 `deploy/cloud-run/release.sh`，它以 Cloud Build 推送相同的 commit-tagged
image，先跑 migration，再建立 zero-traffic candidate；完整 release 時應優先使用這個可重現流程。

## 如何透過 Console UI 部署到 Cloud Run

初次從 Console 建立資源時，先確認 image 已存在於 Artifact Registry，並已在 Secret Manager
建立兩個不同的 secret：runtime pooled URL 與 migration direct URL。兩者都以固定 secret
version 掛載，而不是把 connection string 當成一般環境變數或寫進 repository。

### 1. 建立 migration job

前往 **Google Cloud Console → Cloud Run → Jobs → Deploy container**，使用以下設定：

- Job name：`english-learning-api-migrate`
- Region：`asia-southeast1`
- Container image：上述 commit-tagged image
- Tasks：`1`
- Parallelism：`1`
- Retries：`0`
- Task timeout：`10 minutes`
- Service account：只具有 migration secret 存取權的 migration service account
- Command：`alembic`
- Arguments：`upgrade`, `head`
- Secret environment variable：`DATABASE_URL` → migration direct URL 的指定 secret version

一般環境變數設定為：

```text
APP_ENV=production
LOG_LEVEL=INFO
DATABASE_CONNECT_TIMEOUT_SECONDS=5
GOOGLE_OAUTH_CLIENT_ID=<Google Web OAuth client ID>
CORS_ALLOWED_ORIGINS=["https://josepht5566.github.io"]
```

建立後執行 job，確認 execution 成功。Migration job 使用 direct endpoint，避免 schema migration
經過 transaction pooler；web process 啟動時不會自行 migrate，因此多個 instance 不會互相競爭。

### 2. 建立 API service

前往 **Cloud Run → Services → Deploy container**，選擇同一個 image，並設定：

- Service name：`english-learning-api`
- Region：`asia-southeast1`
- Authentication：Allow unauthenticated invocations
- Ingress：All
- Container port：`8080`
- CPU：`1`
- Memory：`512 MiB`
- Concurrency：`20`
- Request timeout：`30 seconds`
- Minimum instances：`0`
- Maximum instances：`1`
- Service account：只具有 runtime secret 存取權的 runtime service account
- Secret environment variable：`DATABASE_URL` → runtime pooled URL 的指定 secret version
- Startup probe：HTTP GET `/health/live`
- Liveness probe：HTTP GET `/health/live`

一般環境變數與 migration job 相同。Cloud Run 層允許 public invocation，是因為 API 自己會驗證
Google ID token 並在 backend 強制執行 ownership authorization；這不代表需要登入的 endpoint 是
公開資料。`/health/live` 與 `/health/ready` 則刻意保持可供平台與部署流程檢查。

第一次直接用 UI 建立 service 時，新 revision 通常會立即承接 traffic。後續 release 應改用
`release.sh` 先建立 **zero-traffic candidate**，通過 health、登入、owner-scoped read 與受控 write
smoke tests 後才切換 traffic。

本次操作者已回報 Cloud Run 部署成功，且 `/health/ready` 回傳：

```json
{ "status": "ready", "checks": { "database": "ok" } }
```

這能證明 deployed API 可透過 runtime connection 執行資料庫 readiness query，但還不能單獨證明
登入、owner-scoped authorization、寫入、搬移資料完整性或 rollback 都正確。

## 如何部署 Neon schema 與資料

Neon Console 先建立 PostgreSQL project 與 database。Neon 提供的 connection string 是標準
PostgreSQL URL；本專案交給 SQLAlchemy/Alembic 時，driver scheme 要改成
`postgresql+psycopg://`，並保留 TLS 設定：

```text
postgresql+psycopg://<role>:<password>@<host>/<database>?sslmode=require&channel_binding=require
```

Schema 是從本機 checkout 透過 SQLAlchemy/Psycopg 與 Alembic 套用。實際完成的主要 command 是：

```bash
cd apps/api
DATABASE_URL='<direct Neon SQLAlchemy URL>' uv run alembic upgrade head
```

Connection string 沒有寫入 repository。後續也可加上只讀驗證：

```bash
DATABASE_URL='<direct Neon SQLAlchemy URL>' uv run alembic current --check-heads
```

Schema 完成後，操作者再透過本機 Docker 內的 PostgreSQL tools 執行 `pg_dump`／`pg_restore`，將
既有資料上傳到 Neon。因為這次對話沒有保留逐字 command，以下只記錄安全的**示意模板，不是歷史
command 的逐字重建**：

```bash
# 從 local PostgreSQL container 匯出資料；schema 由 Alembic 管理。
docker exec <local-postgres-container> \
  pg_dump \
    --username=<local-user> \
    --dbname=<local-database> \
    --format=custom \
    --data-only \
    --no-owner \
    --no-privileges \
    --file=/tmp/english-learning-data.dump

docker cp \
  <local-postgres-container>:/tmp/english-learning-data.dump \
  /tmp/english-learning-data.dump

# 使用 PostgreSQL 17 client container，把資料寫入 Neon direct endpoint。
docker run --rm \
  --volume /tmp:/backup:ro \
  postgres:17-alpine \
  pg_restore \
    --dbname="$NEON_DIRECT_LIBPQ_URL" \
    --data-only \
    --no-owner \
    --no-privileges \
    --single-transaction \
    /backup/english-learning-data.dump
```

`$NEON_DIRECT_LIBPQ_URL` 應在執行環境中安全注入，不應寫進 Markdown 或 commit。這裡要注意：
SQLAlchemy/Alembic 使用 `postgresql+psycopg://`；PostgreSQL 原生工具 `pg_dump`／`pg_restore`
使用 `postgresql://`。資料 restore 應走 direct endpoint，不使用 hostname 帶有 `-pooler` 的 pooled
endpoint。

先以 Alembic 建 schema，再以 `--data-only` restore，可以維持「schema 由 migration 管理、資料由
明確搬移程序管理」的界線。完成後仍應核對重要資料表筆數、foreign key 關係、owner mapping 和一筆
實際讀寫；`/health/ready` 只執行連線檢查，不能代替資料 reconciliation。

`pg_dump`／`pg_restore` 是這次 bootstrap 或未來 recovery 的工具，不會成為每次 deployment 的
Action。日後正常開發只提交新的 Alembic revision，再由受保護的 migration Action upgrade schema。

## Neon roles 的差別與設定

Database role 解決的是 PostgreSQL 層的權限；產品中的 AuthN/AuthZ 仍由 FastAPI 驗證 Google ID
token、辨認 user，並對每個 query 強制 ownership。TLS 只能加密傳輸並驗證連線對象，不能代替
application authorization。這個專案目前也不依賴 PostgreSQL Row-Level Security；如果未來加入
RLS，它應是額外的 defense-in-depth，而不是取代 backend authorization。

目前需要區分兩種 connection：

| 用途                    | Role                  | Endpoint           | 權限                                                         |
| ----------------------- | --------------------- | ------------------ | ------------------------------------------------------------ |
| Cloud Run API runtime   | `app_user`            | pooled (`-pooler`) | 既有與未來 app tables 的 DML、sequence 使用權；不可改 schema |
| Cloud Run migration job | 目前為 `neondb_owner` | direct             | Alembic 建立／修改 schema 與其所擁有的 objects               |

`neondb_owner` 是 Neon project 的管理／owner role，目前既有 tables 由它擁有，因此仍需要用於
migration 或管理；但它**不應提供給 Cloud Run web service**。長期可建立專用 migration role，
但要同時規劃既有 objects 的 ownership transfer，不能只換 connection string 就假設它有權修改
舊 tables。

`app_user` 是 least-privilege runtime role。建立後先確認它沒有意外繼承 Neon 的高權限 role：

```sql
SELECT pg_has_role('app_user', 'neon_superuser', 'member');
```

若結果為 `true`，應在 owner/admin session 中移除該 membership，並再次確認：

```sql
REVOKE neon_superuser FROM app_user;
```

接著讓 runtime 可以連線與操作 application data，但不能建立 schema objects：

```sql
GRANT CONNECT ON DATABASE neondb TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;
REVOKE CREATE ON SCHEMA public FROM app_user;

GRANT SELECT, INSERT, UPDATE, DELETE
  ON ALL TABLES IN SCHEMA public
  TO app_user;

GRANT USAGE, SELECT
  ON ALL SEQUENCES IN SCHEMA public
  TO app_user;
```

上面的 `GRANT ... ON ALL` 只處理**現在已存在**的 objects。未來由 `neondb_owner` migration 建出的
tables 與 sequences，需透過 default privileges 自動授權：

```sql
ALTER DEFAULT PRIVILEGES FOR ROLE neondb_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;

ALTER DEFAULT PRIVILEGES FOR ROLE neondb_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO app_user;
```

因此 Secret Manager 應保存兩份不同的 URL：

```text
# Cloud Run API service：runtime secret
postgresql+psycopg://app_user:<password>@<pooled-host>/neondb?sslmode=require&channel_binding=require

# Cloud Run migration job：migration secret
postgresql+psycopg://neondb_owner:<password>@<direct-host>/neondb?sslmode=require&channel_binding=require
```

兩個 Cloud Run service accounts 各自只能讀到自己的 secret，並固定指定 secret version。GitHub
Action 只取得更新／執行 migration job 的 GCP 權限；真正讀取 Neon URL 的是 Cloud Run job
identity，因此 connection string 不會進入 GitHub runner。

## 日後 migration Action 如何確保資料庫正確

日常開發中，每一次 schema 改動都要產生並 review Alembic revision，CI 會先在乾淨 PostgreSQL 17
環境跑完整 tests。正式 release 選定 commit 後，必須先把該 commit-tagged image 推到 Artifact
Registry，再人工觸發 production migration Action。

Action 的安全性來自多層 gate：protected environment reviewer、精確 confirmation、OIDC 短效身分、
不可變 image、single task、zero retry、migration concurrency serialization、`upgrade head` 後的
`current --check-heads`，以及 runtime `/health/ready`。Migration 失敗時不應建立或推廣新的 serving
revision；成功後仍要對 zero-traffic candidate 執行 authenticated smoke tests，再人工 promotion。

Migration Action 驗證的是 schema 已到預期 Alembic head，且 runtime role 仍可連線。它不會自動
證明所有 business data 正確，也不會執行 destructive downgrade。涉及 backfill、資料轉換或 constraint
變更時，仍需為該 migration 加入專門的 count、relationship、ownership 或 invariant checks，並以
backward-compatible migration 維持舊 revision 的 rollback window。

## 我們學到什麼

部署 PostgreSQL 不是把一個 local database process 原封不動搬上雲端。實際上需要先 provision
受管 database，再分別處理 **schema migration** 與 **data transfer**。Alembic revision 是可以重複
review、測試與部署的 schema 歷史；`pg_dump`／`pg_restore` 則是一次性 bootstrap 或 recovery
工具，兩者不應混成每次啟動自動執行的步驟。

Pooled 與 direct connection 的差別是 workload，不是 Python driver。FastAPI runtime 與 Alembic
都透過 SQLAlchemy/Psycopg，但 runtime 適合 pooled endpoint，migration 與 PostgreSQL maintenance
tools 應走 direct endpoint。兩者都必須使用 TLS；然而 TLS 只保護傳輸，真正的使用者身分與資料
ownership 仍必須在 backend 強制執行。

Least privilege 不只是「多建立一個帳號」。我們需要理解 object ownership、既有 object grants、
`ALTER DEFAULT PRIVILEGES` 對未來 objects 的作用，以及 sequence 權限。Owner connection 可以保留
給 migration/admin，但不應暴露給處理 public HTTP requests 的 runtime。

安全 release 的順序也很重要：**固定 source → build immutable image → migrate → verify schema →
部署 zero-traffic candidate → smoke test → promotion**。Rollback 是把 traffic 指回仍與現有 schema
相容的 app revision，而不是自動執行 Alembic downgrade。Console UI 很適合第一次理解與建立資源，
但 script 與 Actions 才能提供日後需要的可重現性、review gate 與稽核紀錄。

最後，`/health/ready` 成功是重要里程碑，但它只回答「API 現在能否查詢 database」。完成 Ticket 26
前仍要驗證 authenticated `/v1/me`、owner-scoped reads、受控且可 idempotent replay 的 write、restore
後資料 reconciliation、frontend API/CORS cutover，以及一次 schema-compatible rollback rehearsal。

## 相關檔案

- [`README.md`](README.md)：Ticket 26 狀態與驗收邊界
- [`runbook.md`](runbook.md)：正式 release、smoke、promotion 與 rollback 操作手冊
- [`../../../../apps/api/Dockerfile`](../../../../apps/api/Dockerfile)：production API image
- [`../../../../.github/workflows/ci.yml`](../../../../.github/workflows/ci.yml)：CI 與 container verification
- [`../../../../.github/workflows/migrate-production.yml`](../../../../.github/workflows/migrate-production.yml)：
  production migration workflow
- [`../../../../deploy/cloud-run/release.sh`](../../../../deploy/cloud-run/release.sh)：candidate release script
