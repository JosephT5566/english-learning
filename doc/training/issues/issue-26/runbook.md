# Issue #26 Cloud Run and Neon release runbook

Last updated: 2026-09-13

## Release contract

- Cloud Run runs the FastAPI container in `asia-southeast1`; Neon PostgreSQL runs in AWS Singapore.
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
7. Create an Artifact Registry Docker repository in `asia-southeast1` and two Secret Manager
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

The authenticated check calls `/v1/me` and one owner-scoped deck list. To deliberately mutate one
due English card and verify exact idempotent replay, opt in explicitly:

```bash
GOOGLE_ID_TOKEN="$GOOGLE_ID_TOKEN" CONFIRM_REVIEW_WRITE=yes \
  deploy/cloud-run/smoke.sh https://candidate---SERVICE_HASH.REGION.run.app
```

Record only response status, request IDs, safe counts, the release image/revision, migration
revision, and timestamps. Do not commit tokens, database URLs, user content, or raw responses.

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
