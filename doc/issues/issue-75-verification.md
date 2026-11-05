# Issue #75 verification

## Scope and status

2026-11-05: Part B continues Part A commit `ba4df01` on `issue-75-rls`.
Implementation is committed as `90e1a2b`; restricted-role tests as `60f5686`.
The maintainer supplied the approved issue mirror and Part A handoff. Live GitHub labels,
post-approval edits and overlapping PRs were not independently inspected because this task
explicitly excludes GitHub operations. No push, PR, production access or model API call was made.
Migration 0008 and workflows are unchanged from Part A.

The implementation uses transaction-local GUCs, keeps application owner predicates, preserves
consent locking and leaves document-provider calls outside transactions. See
[database.py:56](../../apps/api/app/database.py#L56),
[auth.py:190](../../apps/api/app/auth.py#L190), and
[embeddings.py:178](../../apps/api/app/embeddings.py#L178).

## Acceptance evidence

All test paths below are under `apps/api/tests/`. Results refer to the final local suites below.

| Acceptance criterion                                                       | Test and evidence                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | Result                                 |
| -------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| Enable all 11 tables, policies, upgrade/downgrade                          | [integration/test_migrations.py:152](../../apps/api/tests/integration/test_migrations.py#L152); Part A migration unchanged                                                                                                                                                                                                                                                                                                                                                              | Covered by full integration run        |
| Owned SELECT and cross-owner INSERT/UPDATE/DELETE on every table           | [integration/test_row_level_security.py:181](../../apps/api/tests/integration/test_row_level_security.py#L181)                                                                                                                                                                                                                                                                                                                                                                          | Covered by full integration run        |
| Missing, empty and nonexistent owner fail closed on all 11 tables          | [integration/test_row_level_security.py:215](../../apps/api/tests/integration/test_row_level_security.py#L215); [integration/test_database_rls_context.py:48](../../apps/api/tests/integration/test_database_rls_context.py#L48)                                                                                                                                                                                                                                                        | Covered by full integration run        |
| Transaction-local lifetime and physical connection reuse                   | [integration/test_database_rls_context.py:32](../../apps/api/tests/integration/test_database_rls_context.py#L32) checks backend PID, commit/rollback, second transaction and a new session/owner; factory clone has pool size 1/no overflow at [conftest.py:76](../../apps/api/tests/integration/conftest.py#L76)                                                                                                                                                                       | Covered by full integration run        |
| Existing HTTP routes and second transaction after commit                   | Default restricted engines at [integration/conftest.py:68](../../apps/api/tests/integration/conftest.py#L68); [integration/test_auth_and_authorization.py:675](../../apps/api/tests/integration/test_auth_and_authorization.py#L675) uses real HTTP with a test hook committing inside card creation, then re-reads the card and checks the owner GUC; both users are denied foreign read/edit/archive/review                                                                           | Covered by full integration run        |
| Retired import tables deny unbound runtime access                          | Same 11-table RLS tests above include all three import tables; [architecture](../architecture.md#transaction-local-row-level-security-2026-11-05) documents disabled tools and `import_items` gap                                                                                                                                                                                                                                                                                       | Covered by full integration run        |
| Embedding and backfill work under RLS and reject foreign cards             | Existing [integration/test_card_embeddings.py:64](../../apps/api/tests/integration/test_card_embeddings.py#L64), including retry, stale result, foreign-owner skip, keyset backfill and fake-provider write; [integration/test_genai_consent.py:124](../../apps/api/tests/integration/test_genai_consent.py#L124) covers HTTP background writes and withdrawal races. Their app factories now bind restricted engines                                                                   | Covered by full integration run        |
| Guest export has only public-deck context, no writes or other-table access | [integration/test_guest_export_transactions.py:75](../../apps/api/tests/integration/test_guest_export_transactions.py#L75) observes actual HTTP export GUCs and read-only mode; [same file:144](../../apps/api/tests/integration/test_guest_export_transactions.py#L144) checks timeout/failure cleanup on the same physical connection; [integration/test_row_level_security.py:246](../../apps/api/tests/integration/test_row_level_security.py#L246) checks public policy boundaries | Covered by full integration run        |
| Search quality unchanged and deliberate indexes retained                   | [eval/test_retrieval_eval.py:102](../../apps/api/tests/eval/test_retrieval_eval.py#L102) compares owner and restricted rankings on the exact same ten seeded cards and frozen vectors; nDCG@5 = 1.0, fixture SHA matches. [integration/test_query_plans.py:521](../../apps/api/tests/integration/test_query_plans.py#L521) EXPLAINs captured production coverage/ranking SQL under both roles                                                                                           | Eval passed; integration results below |
| Document fail-closed, bypass, limits and release order                     | [architecture](../architecture.md#transaction-local-row-level-security-2026-11-05), [API README](../../apps/api/README.md#row-level-security-and-release-order), [project memory](../project-memory.md#owner-isolation-through-rls-2026-11-05), [decision](../decisions.md#2026-11-05-bind-transaction-identities-before-enabling-fail-closed-rls)                                                                                                                                      | Implemented; formatting checked below  |

`owner_id` rejects booleans, strings, floats, zero, negatives and None through
[unit/test_database.py:216](../../apps/api/tests/unit/test_database.py#L216).
Owner and public contexts cannot coexist; the public helper accepts UUID because that is the
actual deck key type ([database.py:78](../../apps/api/app/database.py#L78)).
The owner-bypass comparison is explicit at
[integration/test_database_rls_context.py:38](../../apps/api/tests/integration/test_database_rls_context.py#L38).

## Session and transaction inventory

A source search for `database_session`, `database_transaction`, `session_factory(`, `factory(`,
`Session(`, `.connect(` and `.begin(` found these app paths. Import-only references are grouped
with their actual use. `public_content.py` is a projection, not another transaction entry.

| Path and line                                                                                                                                                                                                                                                                                              | Handling                                                                                                         |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| [main.py:43](../../apps/api/app/main.py#L43), [main.py:52](../../apps/api/app/main.py#L52)                                                                                                                                                                                                                 | Creates/stores the shared factory; no private query or owner at startup                                          |
| [database.py:43](../../apps/api/app/database.py#L43), [database.py:107](../../apps/api/app/database.py#L107)                                                                                                                                                                                               | Factory/request lifecycle; `current_user` binds request identity                                                 |
| [database.py:135](../../apps/api/app/database.py#L135), [database.py:157](../../apps/api/app/database.py#L157)                                                                                                                                                                                             | Optional keyword owner binds before caller queries; omission remains unbound                                     |
| [database.py:184](../../apps/api/app/database.py#L184)                                                                                                                                                                                                                                                     | Readiness uses `SELECT 1`; no protected table or identity needed                                                 |
| [auth.py:115](../../apps/api/app/auth.py#L115), [auth.py:190](../../apps/api/app/auth.py#L190)                                                                                                                                                                                                             | Resolves users in shared request session, then immediately binds owner to active/current and future transactions |
| [reads.py:110](../../apps/api/app/reads.py#L110)                                                                                                                                                                                                                                                           | Shared authenticated request session; no independent session/transaction                                         |
| [writes.py:41](../../apps/api/app/writes.py#L41), [writes.py:530](../../apps/api/app/writes.py#L530), [writes.py:704](../../apps/api/app/writes.py#L704), [writes.py:755](../../apps/api/app/writes.py#L755)                                                                                               | Same session; after_begin preserves identity across explicit commits                                             |
| [writes.py:319](../../apps/api/app/writes.py#L319)                                                                                                                                                                                                                                                         | Passes factory and owner to background `process_card`; no extra route transaction here                           |
| [reviews.py:21](../../apps/api/app/reviews.py#L21)                                                                                                                                                                                                                                                         | Same authenticated session; scheduling math unchanged                                                            |
| [semantic_search.py:22](../../apps/api/app/semantic_search.py#L22)                                                                                                                                                                                                                                         | Same authenticated session for coverage and ranking                                                              |
| [genai_consent.py:16](../../apps/api/app/genai_consent.py#L16)                                                                                                                                                                                                                                             | Same session, including embedding deletion; users locking unchanged                                              |
| [embeddings.py:178](../../apps/api/app/embeddings.py#L178), [embeddings.py:267](../../apps/api/app/embeddings.py#L267)                                                                                                                                                                                     | Both transactions receive owner explicitly; provider remains between them, outside transactions                  |
| [embedding_backfill.py:35](../../apps/api/app/embedding_backfill.py#L35), [embedding_backfill.py:44](../../apps/api/app/embedding_backfill.py#L44)                                                                                                                                                         | Each page uses `database_transaction(..., owner_id=owner_id)`; processor receives the same owner                 |
| [guest_export.py:105](../../apps/api/app/guest_export.py#L105), [guest_export.py:108](../../apps/api/app/guest_export.py#L108)                                                                                                                                                                             | Separate unowned transaction; read-only first, then public-deck binding only                                     |
| [public_content.py:29](../../apps/api/app/public_content.py#L29)                                                                                                                                                                                                                                           | Shared projection used by exporter; no engine/session creation                                                   |
| [imports.py:824](../../apps/api/app/imports.py#L824), [imports.py:826](../../apps/api/app/imports.py#L826)                                                                                                                                                                                                 | Unchanged/unbound; retired runtime import path intentionally disabled                                            |
| [confirmed_imports.py:619](../../apps/api/app/confirmed_imports.py#L619), [confirmed_imports.py:735](../../apps/api/app/confirmed_imports.py#L735), [confirmed_imports.py:1155](../../apps/api/app/confirmed_imports.py#L1155), [confirmed_imports.py:1169](../../apps/api/app/confirmed_imports.py#L1169) | Unchanged/unbound; retired apply/reconcile CLI paths intentionally disabled under runtime role                   |

## CI default and owner exceptions

Yes: ordinary CI app integration sessions use the restricted role by default. There is no new
switch. Existing CI already sets `RUN_POSTGRES_INTEGRATION_TESTS=1` and runs `uv run pytest -q`
([ci.yml:99](../../.github/workflows/ci.yml#L99), [ci.yml:125](../../.github/workflows/ci.yml#L125)).
The migrated fixture installs restricted runtime engines for main/backfill and redirects app
sessionmaker binds from owner engines to separate restricted engines
([conftest.py:73](../../apps/api/tests/integration/conftest.py#L73)).
The test-only connect event commits `SET ROLE app_rls_test` before application transactions start
([rls.py:86](../../apps/api/tests/integration/rls.py#L86)); it does not set either identity.
This also preserves the export's read-only-first ordering.

Seed data, schema/catalog assertions, constraint tests and owner-baseline reads still use owner
connections. Retired import tests explicitly use `owner_session_factory`, including their CLI
factory overrides ([conftest.py:90](../../apps/api/tests/integration/conftest.py#L90),
[rls.py:96](../../apps/api/tests/integration/rls.py#L96)). These exceptions preserve historical
maintenance tests and do not claim retired tools work under runtime RLS. New RLS tests continue
to deny their import tables. No existing test assertion was removed or relaxed.

## Query-plan observations

The automated semantic plan test seeds 100 owners, 2,000 decks, 40,000 cards and embeddings, then
captures the actual production coverage/ranking statements and parameters. No planner switches
force an index. `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` uses the existing helper
([test_query_plans.py:32](../../apps/api/tests/integration/test_query_plans.py#L32)).

- Owner coverage uses `ix_card_embeddings_owner_state_retry`.
- Restricted coverage instead uses `pk_card_embeddings` and
  `ix_learning_cards_owner_updated_id` after selecting owned cards.
- Ranking retains `ix_card_embeddings_owner_state_retry` for both roles; restricted ranking also
  uses `uq_learning_cards_id_owner_id`.

These precise assertions are at [test_query_plans.py:603](../../apps/api/tests/integration/test_query_plans.py#L603).
The existing nine access-pattern index assertions are unchanged. An initial new semantic-test
expectation that coverage and ranking would both use the retry index was disproved by the actual
plans. The new test was corrected to record the observed indexed coverage strategy and preserve
an explicit owner comparison; no product query, policy or existing index assertion was changed.
This is local plan evidence, not production-scale latency or recall evidence.

## 驗證證據

All Python checks ran from `apps/api`, using `UV_CACHE_DIR=/tmp/codex-75/uv-cache` because the
sandbox cannot read the default uv cache. PostgreSQL tests required an approved sandbox network
escalation for the already-running localhost:5432 disposable service. No new database service or
port was started; fixtures create/drop isolated databases in that service.

### Red-first

With test fixture restriction installed but the unchanged Part A app:

`RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest tests/integration/test_auth_and_authorization.py tests/integration/test_card_embeddings.py tests/integration/test_guest_export_transactions.py -q`

Exit 1: 22 failed, 7 passed. App writes/search/embedding/export fail without transaction identity.
Log: `/tmp/codex-75/red-b-valid.log`.

The new identity tests plus unit tests initially returned 11 failed, 9 passed, exit 1
(`/tmp/codex-75/red-context-valid-b.log`). A final red-first replay temporarily restored all five
app files byte-for-byte from Part A and restored Part B in `finally`:

`RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest tests/integration/test_database_rls_context.py tests/unit/test_database.py tests/integration/test_auth_and_authorization.py::test_http_identity_rebinds_after_commit_and_isolates_both_users tests/integration/test_query_plans.py::test_semantic_queries_keep_owner_indexes_under_rls -q`

Exit 1: 13 failed, 9 passed. Missing binding functions/owner argument and HTTP foreign-context
failures establish the missing behavior; the plan test fails at its missing bind_owner import.
Log: `/tmp/codex-75/red-final-b.log`.

### Final checks

| Working directory | Command (uv cache prefix as above)                                    | Exit | Observed result                                                                            |
| ----------------- | --------------------------------------------------------------------- | ---- | ------------------------------------------------------------------------------------------ |
| apps/api          | `uv run ruff check .`                                                 | 0    | All checks passed                                                                          |
| apps/api          | `uv run ruff format --check .`                                        | 0    | 89 files already formatted                                                                 |
| apps/api          | `uv run pytest tests/unit -q`                                         | 0    | 205 passed, 1 existing Starlette deprecation warning                                       |
| apps/api          | `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest tests/integration -q` | 0    | 272 passed, 51 warnings, no skipped tests                                                  |
| apps/api          | `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest tests/eval -q`        | 0    | 10 passed; same-data owner/restricted ranking equality and nDCG@5 1.0; fixture SHA matches |
| root              | `npm run lint:changed -- origin/main`                                 | 0    | Changed-file Prettier/ESLint passed                                                        |
| root              | `git diff --check`                                                    | 0    | No whitespace errors                                                                       |

Local logs: `/tmp/codex-75/unit-b.log`, `integration-b.log`, `eval-b.log`.
The 51 integration warnings are one existing Starlette deprecation and 50 pgvector type-reflection
SAWarnings. No test was skipped. The evaluation's ignored `apps/api/retrieval-eval-report/report.md` reports score/SHA status.
No API models/generated artifacts changed, so `api:check` was not required. Frontend/build/browser
and container checks were not run because this change only binds backend database transaction
context and does not change HTTP contracts, frontend behavior or runtime lifecycle.

### Intermediate failures and corrections

- Default uv cache access failed with `Operation not permitted`, exit 2; a task-local cache was used.
- The first sandboxed PostgreSQL attempt had 29 setup errors, exit 1; only the network-enabled run
  above counts as behavioral red-first evidence.
- An initial command used repository-relative paths from `apps/api`, producing missing-file errors
  and pytest exit 4; corrected to the proper working directory.
- Running Ruff from the repository root selected different import grouping and changed unrelated
  test imports. Those incidental edits were restored; final checks used `apps/api`.
- The first combined unit/integration run had 6 failed, 469 passed, exit 1. Existing hash-test
  setup/inspection used `app.state.database_engine`, which is now restricted. Moved only those
  seed/readback operations to the owner fixture; kept runtime query observation and every assertion.
- A targeted run returned 1 failed, 38 passed, exit 1 because the new coverage-index expectation
  was wrong. Owner/restricted EXPLAIN observation confirmed the plan difference described above.
  Log: `/tmp/codex-75/plan-observation-b.log`.

## Limits and operator reports

Operator report, 2026-11-05, not programmatically verified: production runtime is
`app_runtime_limited`, `rolsuper` and `rolbypassrls` are false, and all 11 table owners are
`neondb_owner`. This implementation did not access production.

Unverified: Neon pooled transaction mode and production connection reuse; production rollout,
rollback and current runtime health; added set_config latency; production-scale vector recall and
planner behavior; live provider integration; current GitHub label/approval/overlapping PR state;
concurrent role creation from a nonexistent role under load. These are not established by local
synthetic PostgreSQL/fake-provider tests. `import_items` remains an accepted RLS gap.

The docs specify code-before-RLS rollout and RLS-disable-before-old-code rollback. Existing release
automation still migrates before deploying the candidate; it was intentionally not edited and
must not be followed unchanged for 0008. No claim of production deployment readiness is made.
