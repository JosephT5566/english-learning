# Issue #27 backup and isolated restore

Status: synthetic local restore verified on 2026-09-18. Independent production
backup to GCS and restore of that backup remain unverified.

## Recovery boundary

Neon remains the live source of truth. A PostgreSQL custom-format dump is the
proposed independent backup artifact. Store real dumps only in a private GCS
bucket and a short-lived, access-restricted operator workspace. Never commit a
dump, connection string, passfile, private manifest, row sample, or content
hash. A successful `pg_dump` or upload alone is not recovery proof: restore
into an empty, isolated PostgreSQL 17 environment and reconcile it.

The dump includes this database's schema, table data, and sequence values; it
does not provision cluster-wide roles or external secrets. Restore uses
`--no-owner --no-acl`, so the target's roles and access policy must be set
separately. Use a PostgreSQL 17 client for the current PostgreSQL 17 database.
The official [pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html) and
[pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html) references
describe custom archives and restore options.

## Synthetic local proof

The source was a new disposable local database migrated to Alembic head and
loaded with the checked-in multilingual fixture. `pg_dump -Fc --no-owner
--no-acl` produced a 57,205-byte archive with 13 table-data entries. A first
restore into a separate empty local database succeeded. The stronger proof
restored the same archive into a disposable `postgres:17-alpine` container with
`--network none`, no published ports, and temporary database storage.

Both source and isolated target ran
[`restore-reconciliation.sql`](restore-reconciliation.sql) with `ON_ERROR_STOP`.
The outputs matched exactly:

| Check                                           | Source and isolated restore |
| ----------------------------------------------- | --------------------------: |
| Alembic head                                    |             `20260910_0005` |
| Public tables / columns / constraints / indexes |         13 / 148 / 138 / 43 |
| Users / decks / cards / tags / card-tag links   |           1 / 2 / 2 / 2 / 3 |
| Review states / batches / events                |                   2 / 1 / 2 |
| Dry-run and confirmed-import audit rows         |                           0 |
| Wrong deck/card owner relationships             |                           0 |
| Wrong confirmed-import mapping relationships    |                           0 |

Representative fixture checks found one English and one Japanese card with an
owned deck, review state, and review event. The English pronunciation and
Japanese reading/romanization predicates matched in both databases. The
isolated container reported `network=none ports={}`. `pg_dump`, `pg_restore`,
and server version were 17.11. The evidence was recorded at 2026-09-17
17:36 UTC from commit `b3aaa3c` plus the uncommitted reconciliation query.
The temporary archive, manifest files, databases, and container are removed
after verification. These are synthetic records only; this does not prove a
Neon or GCS backup.

## Production backup proposal awaiting execution

1. Create a dedicated Singapore GCS bucket with uniform bucket-level access,
   public access prevention, and narrow writer/restore-reader IAM. GCS encrypts
   objects at rest by default. Choose retention and a recurring schedule from
   the operator's recovery needs and measured archive size. The read-only
   project check on 2026-09-18 listed no existing buckets in
   `eng-learning-470909`; no bucket was created in this step. See Google's
   [bucket creation](https://cloud.google.com/storage/docs/creating-buckets),
   [uniform access](https://cloud.google.com/storage/docs/uniform-bucket-level-access),
   [public access prevention](https://cloud.google.com/storage/docs/using-public-access-prevention),
   and [encryption](https://cloud.google.com/storage/docs/encryption) guidance.
   The project has only `english-learning-neon-migration-url` and
   `english-learning-neon-runtime-url` secrets; there is no dedicated backup
   credential. The secret-name check did not read secret values. Provision a
   read-only backup role and its separately scoped secret before a production
   dump. Do not reuse the schema-owning migration secret for a recurring job.
2. Use a dedicated read-only direct Neon connection with required TLS and a
   private libpq service/passfile. Do not use the pooled runtime URL or expose
   credentials in arguments, logs, scripts, or CI variables. Take the dump to
   a mode-0600 file in a private temporary directory. Check `pg_dump` exit
   status and `pg_restore --list` before upload. Upload to a unique GCS object
   with `gcloud storage cp --if-generation-match=0`; record only object name,
   generation, size, checksum, time, and outcome in the private operator
   report. Do not make the object public.

   Example operator commands after the bucket, backup role, and private libpq
   service `neon_backup` exist (replace the object name with a unique timestamp
   and keep the local directory private):

   ```bash
   umask 077
   pg_dump --dbname="service=neon_backup" --format=custom \
     --no-owner --no-acl --file="$backup_file"
   pg_restore --list "$backup_file" >/dev/null
   gcloud storage cp --if-generation-match=0 "$backup_file" \
     "gs://BACKUP_BUCKET/manual/UNIQUE_BACKUP_NAME.dump"
   ```

   `backup_file` must point to a new file in a mode-0700 directory outside the
   repository. Abort on any command failure; do not upload a partial archive.

3. Download one actual stored object to a private temporary directory. Restore
   it into an empty PostgreSQL 17 instance or container with no route to the
   production database and `pg_restore --exit-on-error --no-owner --no-acl`.
   Run the reconciliation query, compare schema version and expected counts,
   and privately inspect representative owned English/Japanese records and
   review/import relationships. Record only aggregate checks and pass/fail in
   committed evidence; keep row-level comparison private.
4. If comparing live source counts to the restored dump, use the same exported
   PostgreSQL snapshot for the manifest and `pg_dump --snapshot`, or pause
   writes while capturing both. Independently timed live counts are not an
   exact comparison. PostgreSQL documents
   [exported snapshots](https://www.postgresql.org/docs/17/functions-admin.html)
   and the [dump snapshot option](https://www.postgresql.org/docs/17/app-pgdump.html).
5. If any restore or reconciliation check fails, retain the original backup
   object, do not write to production, and diagnose the missing schema/data or
   privilege before another recovery attempt. Keep application traffic and
   migration workflows separate from this exercise.

The real GCS/Neon run, recurring backup schedule, retention decision, and
restore evidence remain Issue #27 acceptance work. The initial Issue #26
local-to-Neon transfer reconciliation is a separate, still deferred check.
