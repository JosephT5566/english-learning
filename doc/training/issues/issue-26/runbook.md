# Issue #26 Cloud Run and Neon release runbook

Last updated: 2026-09-17

The identity, IAM, variable, and secret relationships behind this runbook are indexed in
[`github-gcp-neon-maintenance.zh-TW.md`](github-gcp-neon-maintenance.zh-TW.md).

## Release contract

- Cloud Run runs the FastAPI container in `asia-southeast1`; Neon PostgreSQL runs in AWS Singapore.
- Artifact Registry is in `asia-east1`. Release configuration keeps its location separate from the
  Cloud Run region.
- Neon is the only production source of truth. There is no database switch, dual write, or Cloud SQL
  replica.
- The runtime uses a pooled Neon URL and a DML-only database role. The migration job uses a direct
  Neon URL and a separate schema-owning role. Both are injected under the existing `DATABASE_URL`
  setting, but from different version-pinned Secret Manager secrets.
- Production database URLs must use `sslmode=verify-ca` or `sslmode=verify-full`, or combine
  `sslmode=require` with `channel_binding=require`. Startup rejects weaker settings without printing
  the URL.
- Migrations run once in a single-task, zero-retry Cloud Run job before a tagged candidate revision
  is created. Web startup never migrates.
- A candidate receives zero production traffic until public health, authenticated ownership, and a
  controlled idempotent review write pass.
- Application rollback moves traffic to the recorded compatible Cloud Run revision. It never
  performs an automatic Alembic downgrade.

Accepted initial limits are Neon Free compute/storage quotas, scale-to-zero cold starts, a six-hour
provider restore window, no private network/IP allowlist, and no platform SLA. Issue #27 owns an
independent GCS backup, restore proof, monitoring, alerts, and an incident exercise.

## Optional one-time restored-data reconciliation (not executed)

The initial local PostgreSQL-to-Neon `pg_dump`/`pg_restore` transfer was not independently
reconciled. The operator chose to defer this check for the initial deployment. The local Issue #23
CSV import reconciliation and the live review idempotency replay test cover different boundaries;
neither proves that the database transfer preserved every row. Do not mark the restore as verified
without executing and recording the checks below. This is an operator-invoked, read-only check,
not a scheduled job. Issue #27's independent backup/restore proof is separate.

For a future transfer, record a source manifest during the dump's consistent snapshot, before
production writes resume. For this already-live transfer, use the preserved dump restored into an
isolated temporary database, or a source database known to be unchanged since the dump. If neither
exists, current source and Neon totals are not an exact transfer comparison. In particular, live
deck/card creation and review writes can legitimately increase the Neon totals and change review
states after cutover. Do not infer transfer completeness from matching only the 596-card private
import report.

Configure two local, untracked libpq service entries named `source_snapshot` and `neon_readonly`.
Use read-only database credentials and TLS; keep passwords in a private passfile, not in shell
arguments, documentation, or committed files. Open each database separately:

```bash
psql -X -v ON_ERROR_STOP=1 "service=source_snapshot"
psql -X -v ON_ERROR_STOP=1 "service=neon_readonly"
```

In each `psql` session, run the following read-only transaction. Record only table names and
counts in the evidence report. The transaction gives each session an internally consistent view;
it does **not** make two independently changing databases share a snapshot.

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT 'users' AS table_name, count(*) FROM users
UNION ALL SELECT 'learning_decks', count(*) FROM learning_decks
UNION ALL SELECT 'learning_cards', count(*) FROM learning_cards
UNION ALL SELECT 'tags', count(*) FROM tags
UNION ALL SELECT 'learning_card_tags', count(*) FROM learning_card_tags
UNION ALL SELECT 'review_states', count(*) FROM review_states
UNION ALL SELECT 'review_batches', count(*) FROM review_batches
UNION ALL SELECT 'review_events', count(*) FROM review_events
UNION ALL SELECT 'import_runs', count(*) FROM import_runs
UNION ALL SELECT 'import_items', count(*) FROM import_items
UNION ALL SELECT 'confirmed_import_runs', count(*) FROM confirmed_import_runs
UNION ALL SELECT 'confirmed_import_mappings', count(*) FROM confirmed_import_mappings
ORDER BY table_name;

SELECT count(*) AS cards_with_wrong_deck_owner
FROM learning_cards AS c
LEFT JOIN learning_decks AS d ON d.id = c.deck_id
WHERE d.id IS NULL OR d.owner_id <> c.owner_id;

SELECT count(*) AS states_with_wrong_card_owner
FROM review_states AS s
LEFT JOIN learning_cards AS c ON c.id = s.card_id
WHERE c.id IS NULL OR c.owner_id <> s.owner_id;

SELECT count(*) AS mappings_with_wrong_owner_or_deck
FROM confirmed_import_mappings AS m
LEFT JOIN confirmed_import_runs AS r ON r.id = m.confirmed_import_run_id
LEFT JOIN learning_cards AS c ON c.id = m.learning_card_id
WHERE r.id IS NULL OR c.id IS NULL
   OR r.owner_id <> m.owner_id OR c.owner_id <> m.owner_id
   OR c.deck_id <> r.deck_id;

COMMIT;
```

All three mismatch counts should be zero. Compare same-snapshot table counts and the approved
import-run metadata, then perform an authenticated owned read against Neon. An all-zero mismatch
result proves these relationships only; it does not prove that every content field survived.
For stronger transfer proof, compare deterministic per-row digests in a private operator workspace
against the same snapshot, never commit raw rows or low-entropy content hashes. Record the source
snapshot identity, transfer time, checked revision, safe expected/actual counts, mismatch counts,
and any unresolved differences. If a check fails, stop claiming transfer verification and diagnose
before any repair; do not auto-write to production.

## One-time provisioning

1. Create a PostgreSQL 17 Neon project in AWS Singapore. Do not import the private CSV or local
   development database.
2. Create `english_learning_migration` and `english_learning_runtime` login roles with distinct
   generated passwords. Do not use the Neon project owner for the web service.
3. As the project owner, grant the migration role `CONNECT` on the database plus `USAGE, CREATE` on
   schema `public`. Grant the runtime role `CONNECT` plus `USAGE` only.
4. Configure default privileges for objects created by the migration role:

   ```sql
   ALTER DEFAULT PRIVILEGES FOR ROLE english_learning_migration IN SCHEMA public
     GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO english_learning_runtime;
   ALTER DEFAULT PRIVILEGES FOR ROLE english_learning_migration IN SCHEMA public
     GRANT USAGE, SELECT ON SEQUENCES TO english_learning_runtime;
   ```

   After the first migration, apply the equivalent grants to existing tables and sequences:

   ```sql
   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public
     TO english_learning_runtime;
   GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public
     TO english_learning_runtime;
   ```

5. Copy the pooled runtime URL and direct migration URL separately. Require TLS in both URLs. Prefer
   `sslmode=verify-full`; the Neon-compatible minimum is
   `sslmode=require&channel_binding=require`. Verify the chosen form from the production image.
6. Create two user-managed Cloud Run service accounts. Grant each account Secret Manager access to
   only its matching database secret. Do not grant either account project Editor.
7. Use the Artifact Registry Docker repository in `asia-east1` and create two Secret Manager
   secrets. Add the URLs as secret versions without writing them to a repository file or shell log.
8. Copy `deploy/cloud-run/release.env.example` to the ignored
   `deploy/cloud-run/release.env` and replace every placeholder. The file contains resource names
   and public configuration only; database URLs remain in Secret Manager.

The Google OAuth client ID is a public audience identifier, not a credential. CORS must contain the
exact GitHub Pages origin without its repository path.

## Candidate release

Review the pending migration for backward compatibility with the currently serving revision. Then
commit the release; the script refuses a dirty worktree.

```bash
set -a
source deploy/cloud-run/release.env
set +a
deploy/cloud-run/release.sh
```

The script performs these ordered operations:

1. Build and push an image tagged with the Git commit.
2. Create or update a one-task, zero-retry Alembic job using the direct migration secret.
3. Execute `alembic upgrade head` and stop on failure.
4. Deploy a public tagged `candidate` revision with zero production traffic, a maximum of one
   instance, a version-pinned runtime secret, and startup/liveness probes. Cloud Run does not expose
   a readiness-probe setting, so the candidate smoke gate checks `/health/ready` before promotion.

On the first release only, apply the existing-object grants from provisioning step 4 after the
migration job succeeds and before candidate verification. Later objects inherit the default
privileges automatically.

For a repeated deployment of the same commit, set a new lowercase `RELEASE_ID`; never overwrite an
existing image tag to disguise different source.

## Protected GitHub image publishing workflow

`.github/workflows/publish-api-image.yml` replaces the local `gcloud` and Docker publishing steps
when an operator intentionally selects a release ref. It uses the protected `production` GitHub
environment and WIF, requires the exact confirmation `publish-api-image`, and tags the image with
the selected commit's first 12 SHA characters.

Create a dedicated `github-production-publish` service account. Allow the same WIF provider's
restricted production-environment subject to impersonate it, and grant it `Artifact Registry
Writer` only on the `language-learning` repository. Do not grant this identity Cloud Run, Service
Account User, or Secret Manager access. Add its email as this non-secret GitHub `production`
environment variable:

```text
GCP_GITHUB_PUBLISH_SERVICE_ACCOUNT=github-production-publish@eng-learning-470909.iam.gserviceaccount.com
```

In the Actions UI, select **Publish API container**, choose the exact branch or tag to publish,
enter `publish-api-image`, and approve the `production` environment. The workflow resolves that
ref to its commit and then:

1. Authenticates through GitHub OIDC without a service-account key.
2. Resolves the immutable image tag from `GITHUB_SHA`.
3. Refuses to overwrite the tag if it already exists.
4. Builds `apps/api` for `linux/amd64` and pushes it to Artifact Registry.
5. Verifies the published image and records a safe workflow summary.

It does not run Alembic, read either database secret, deploy a Cloud Run service or job, or change
traffic. After it succeeds, use the same selected ref when starting the migration workflow.

## Protected GitHub migration workflow

Future production schema upgrades can use `.github/workflows/migrate-production.yml`. The workflow
does not receive a Neon connection string or a Google service-account key. GitHub exchanges its OIDC
token for a short-lived Google credential, configures the existing Cloud Run migration job, and the
job identity reads the direct database URL from Secret Manager.

Before the first run:

1. Create and protect a GitHub environment named `production`. Add a required reviewer before the
   workflow is used; merely referencing an environment does not create review protection.
2. Configure a Google Workload Identity Pool/provider restricted to this repository and the
   `production` environment subject. Create dedicated GitHub publisher and migration deployer
   service accounts.
3. Grant the publisher Artifact Registry Writer only on the image repository. Grant the release
   deployer Artifact Registry Reader, permission to manage the migration job and API service, and
   Service Account User on both `MIGRATION_SERVICE_ACCOUNT` and `RUNTIME_SERVICE_ACCOUNT`. Do not
   grant either GitHub identity Secret Manager access. Each Cloud Run identity retains access only
   to its matching database secret.
4. Add these non-secret values as GitHub `production` environment variables:

   ```text
   ARTIFACT_REGION=asia-east1
   ARTIFACT_REPOSITORY=language-learning
   API_IMAGE_NAME=api
   API_SERVICE=english-learning-api
   PUBLIC_API_BASE_URL=https://YOUR_CLOUD_RUN_SERVICE_URL
   GCP_PROJECT_ID=eng-learning-470909
   GCP_REGION=asia-southeast1
   GCP_WORKLOAD_IDENTITY_PROVIDER=projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/POOL/providers/PROVIDER
   GCP_GITHUB_PUBLISH_SERVICE_ACCOUNT=github-production-publish@eng-learning-470909.iam.gserviceaccount.com
   GCP_GITHUB_SERVICE_ACCOUNT=github-production-migration@eng-learning-470909.iam.gserviceaccount.com
   MIGRATION_JOB=english-learning-api-migrate
   MIGRATION_SERVICE_ACCOUNT=english-learning-migrate@eng-learning-470909.iam.gserviceaccount.com
   RUNTIME_SERVICE_ACCOUNT=english-learning-api@eng-learning-470909.iam.gserviceaccount.com
   RUNTIME_DATABASE_SECRET=english-learning-neon-runtime-url
   RUNTIME_DATABASE_SECRET_VERSION=1
   MIGRATION_DATABASE_SECRET=english-learning-neon-migration-url
   MIGRATION_DATABASE_SECRET_VERSION=1
   PUBLIC_GOOGLE_AUTH_CLIENT_ID=YOUR_GOOGLE_WEB_CLIENT_ID
   CORS_ALLOWED_ORIGINS=["https://josepht5566.github.io"]
   ```

   The workflow reuses the frontend's public API origin and OAuth client ID variables. It maps them
   to the workflow's internal `API_BASE_URL` and the backend's `GOOGLE_OAUTH_CLIENT_ID` process
   environment variable. The frontend and migration readiness check must target the same Cloud Run
   API origin, while the frontend and API must agree on the token audience.

To run it, first use **Publish API container** to build and push the selected GitHub commit as the
12-character commit tag. In the Actions UI, select **Migrate production PostgreSQL**, choose that
same ref, enter the exact confirmation `migrate-production`, and approve the `production`
environment. The workflow fails before mutation if the image does not exist, serializes production
migrations, runs `alembic upgrade head` once with zero retries, and then runs `alembic current
--check-heads` as a separate execution. It finally requires the deployed API's `/health/ready`
check to pass through the runtime database role.

This workflow never runs `pg_dump`, `pg_restore`, an Alembic downgrade, application deployment, or
traffic promotion. Those remain separate, explicit release or recovery operations.

The publish, migration, and candidate workflows share the `production-api-release` concurrency
group. Runs queue instead of cancelling one another, so two release steps cannot mutate production
at the same time. The operator must still select the same ref and run them in order.

## Protected GitHub candidate deployment workflow

After the publish and migration workflows succeed for the same ref, run
`.github/workflows/deploy-api-candidate.yml`. In the Actions UI, select **Deploy API candidate**,
choose that ref, enter the exact confirmation `deploy-api-candidate`, and approve the protected
`production` environment.

Before the first run, grant `GCP_GITHUB_SERVICE_ACCOUNT` Service Account User on
`RUNTIME_SERVICE_ACCOUNT`. The release deployer already needs Cloud Run Developer and Artifact
Registry Reader. It does not need Secret Manager access; the runtime service account reads only its
version-pinned runtime database secret.

The workflow:

1. Resolves the same commit-tagged image and deterministic Cloud Run revision name.
2. Requires the image and existing API service to exist, and refuses to overwrite an existing
   revision.
3. Records the current positive traffic allocations for rollback evidence.
4. Deploys the image with the checked-in runtime settings, `candidate` tag, and zero production
   traffic. It preserves the existing service invocation IAM policy rather than trying to grant or
   revoke public access.
5. Verifies that the candidate tag points to the expected revision and that the revision has no
   positive production traffic allocation.
6. Calls the candidate `/health/live` and `/health/ready` endpoints and records its URL, revision,
   image, and previous traffic in the job summary.

This is only the public candidate gate. Obtain a fresh Google ID token and run the authenticated
smoke script below before promotion. The workflow never promotes or rolls back traffic, reruns
Alembic, rebuilds the image, or reads a database secret.

Alternatively, run the protected **Smoke API candidate** workflow with a fresh allowlisted Google
ID token. It resolves the current zero-traffic `candidate` tag and runs the same script. Its optional
semantic-search input sends one fixed, bounded English query through Vertex and validates the
response contract, stable distance ordering, coverage counts, and absence of raw vectors. Its
optional review-write input changes one real due card and verifies exact replay. `workflow_dispatch`
inputs are not GitHub secrets; the workflow masks the token in runner logs, but the dispatch input
itself is still a short-lived credential and must not be reused or placed in committed files. Use
the existing `production` environment approval and inspect only the safe run summary.

## Candidate verification

Obtain the tagged candidate URL from the Cloud Run service and run public checks:

```bash
deploy/cloud-run/smoke.sh https://candidate---SERVICE_HASH.REGION.run.app
```

For authenticated checks, obtain a fresh Google ID token without saving it to a file or shell
history, export it in the current shell, and run:

```bash
GOOGLE_ID_TOKEN="$GOOGLE_ID_TOKEN" \
  deploy/cloud-run/smoke.sh https://candidate---SERVICE_HASH.REGION.run.app
```

The authenticated check calls `/v1/me` and one owner-scoped deck list.

To make exactly one provider-backed semantic request without printing its query results, opt in
explicitly:

```bash
GOOGLE_ID_TOKEN="$GOOGLE_ID_TOKEN" CONFIRM_SEMANTIC_SEARCH=yes \
  deploy/cloud-run/smoke.sh https://candidate---SERVICE_HASH.REGION.run.app
```

The safe summary contains only status, request ID, result count, index status, coverage counts, and
the single curl total-time observation. It does not establish p50/p95 or independently establish
retrieval quality. Inspect one expected Top-K result locally if a bounded quality observation is
required, but do not copy card content or IDs into logs or committed evidence.

To deliberately mutate one due English card and verify exact idempotent replay, opt in explicitly:

```bash
GOOGLE_ID_TOKEN="$GOOGLE_ID_TOKEN" CONFIRM_REVIEW_WRITE=yes \
  deploy/cloud-run/smoke.sh https://candidate---SERVICE_HASH.REGION.run.app
```

Record only response status, request IDs, safe counts, the release image/revision, migration
revision, single-request timing observations, and timestamps. Do not commit tokens, database URLs,
user content, card IDs, raw vectors, or raw responses.

Before promotion, verify:

- the migration job succeeded and `alembic current` reports the expected head;
- liveness and readiness return `200`;
- an invalid/missing bearer token is rejected;
- the authenticated user sees only owned data;
- the controlled write and identical replay return the same committed result;
- production logs contain no token, database URL, or learning content.

## Promotion and frontend cutover

Record the currently serving revision before changing traffic:

```bash
gcloud run revisions list \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --service "$API_SERVICE"
```

Promote only the verified candidate revision:

```bash
gcloud run services update-traffic "$API_SERVICE" \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --to-revisions CANDIDATE_REVISION=100
```

After the stable API URL passes the same smoke checks, set the GitHub Pages
`PUBLIC_API_BASE_URL` repository variable to that HTTPS origin and trigger the existing Pages
deployment. Verify sign-in, one owned read, one review write, English/Japanese management, and the
absence of Apps Script requests before declaring the frontend cutover live.

## Application rollback

Rollback is allowed only while the previous application revision remains compatible with the
current database schema. Move all traffic back to the recorded revision:

```bash
gcloud run services update-traffic "$API_SERVICE" \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --to-revisions PREVIOUS_COMPATIBLE_REVISION=100
```

Re-run health and authenticated read checks. If the frontend was cut over, restore its previously
recorded API origin/revision as needed. Do not point the application at a second writable database,
automatically downgrade the schema, or claim rollback success without a timed rehearsal.

If a migration itself is unsafe, stop the release before candidate traffic. Recovery then follows a
reviewed migration-specific forward fix or restore plan, not the application traffic command above.
