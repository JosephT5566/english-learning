# Issue #74 verification

## Scope and status

Work is committed as `1d3ca15` on branch `issue-74-genai-consent` and opened as PR #81.
Commands in the log were observed before that commit; entries saying "uncommitted" describe
the state at the time.

`gh` is unavailable, so the user-supplied
issue mirror and JosephT5566 approval record are the implementation source. Live issue labels,
approval boxes, and post-approval edits could not be independently inspected.
The supplied approval includes the new migration and backend ownership boundary.
No workflow, public environment handling, static-path behavior, scheduling, or deployment changes
were made. No staging, commit, push, merge, label change, Vertex call, or model API call was made.

Backend implementation and its original verification record below are preserved.
The 2026-11-05 continuation implements the selected inline frontend; see the continuation
verification section for fresh frontend results and remaining limits.

## Backend contract

- GET/PUT/DELETE `/v1/me/genai-consent` address only the authenticated user. Each returns
  `genai_consent_at`, either NULL or an ISO timestamp. Grant is idempotent.
- Migration `20261105_0007` follows `20260920_0006`, defaults new and existing users to NULL,
  and removes the column on downgrade.
- Semantic search checks consent first, returning `403 genai_consent_required` before coverage,
  provider configuration, or provider calls. Existing deck/configuration behavior is preserved
  for consented owners.
- Card writes succeed without consent. Background processing skips before claiming or calling
  the provider. Claim and final-write transactions share-lock the owner row before card locks;
  withdrawal updates that row and deletes all owned embedding versions in the same transaction.
- Provider document calls stay outside transactions. A withdrawal during a call deletes the claim;
  the final consent check and guarded UPDATE cannot restore it, even after regrant.
- Backfill scans only consented owners. `process_card` independently rechecks consent.
- Granting consent does not automatically backfill existing cards. The operator repair tool remains
  the existing mechanism. Withdrawal cannot recall already transmitted content.

## UI decision log

2026-11-05: The maintainer selected option A by chat and explicitly authorized continuing in
this worktree. Use inline consent in `src/routes/search/+page.svelte`, with an inline
confirmation before withdrawal. Do not add a dialog, an AccountMenu entry, or public config.
This selection is recorded locally; no GitHub issue edit or label change was made.

The implementation reuses the search route's notice/form treatment and component-local CSS,
with Study Blue, translucent paper, and a wrapping action row that stacks at narrow widths.
The desktop search column remains 46rem. Review flip-before-answer, shared English/Japanese
screens, `resolve()` links, and existing management collapse behavior are unchanged.
The previously considered dialog/account-menu option was not selected.

Consent is loaded when entering meaning search. A missing grant shows the content/provider
explanation and blocks semantic submission, including programmatic form submission.
Grant enables the Search button; it does not automatically submit the preserved query.
Withdrawal requires a second inline action, warns about deleting existing embeddings and
already-transmitted content, and clears displayed semantic results after success.
Keyword search remains available without AI consent because it does not use Vertex.
The generated artifact contains types, not an executable client; the existing authenticated
API client now wraps GET/PUT/DELETE using its generated `GenAIConsentResponse` type and
runtime response validation. Cached consent and search results reset when the account changes;
responses from earlier sessions cannot restore them. A 403 `genai_consent_required` returns to the consent prompt.

## 驗證證據

### Original backend-session record

The following records commands observed in the prior backend session, not fresh reruns.
The shared dependency limitations below describe that session only.

All commands below use existing dependencies without synchronizing or installing into the shared
symlinks. Python commands use `UV_NO_SYNC=1 UV_CACHE_DIR=/tmp/issue74-uv
PYTHONDONTWRITEBYTECODE=1`. Frontend commands use the CI's synthetic public variable values,
not a local `.env`. No `.env` file exists at the frontend or API root; no secrets were read.

A disposable `pgvector/pgvector:0.8.6-pg17-bookworm` container supplies only synthetic PostgreSQL
fixtures. Initial sandbox database access was denied; the same tests ran with local database
access after sandbox escalation. No SQLite substitution was used.

### Red-first on unchanged application code

Repository root:

`RUN_POSTGRES_INTEGRATION_TESTS=1 uv run --project apps/api pytest apps/api/tests/integration/test_genai_consent.py -q`

Exit 1: 10 failed. Expected observed failures included missing consent endpoints (404 vs 200),
semantic search returning 200 vs 403, two document provider calls vs zero on unconsented create/edit,
processor returning ready vs skipped, and the missing `genai_consent_at` column.
An earlier sandboxed attempt exited 1 with 10 connection setup errors; that attempt alone was not
counted as red-first behavior evidence.

### Checks after implementation

| Working directory | Command                                                                                                                 | Exit | Observed result                                                                                                                                 |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------- | ---- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| root              | `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run --project apps/api pytest apps/api/tests/integration/test_genai_consent.py -q` | 0    | 10 passed; includes two-owner isolation, withdrawal during provider work with/without regrant, and upgrade/downgrade/upgrade round trip         |
| `apps/api`        | `uv run ruff check .`                                                                                                   | 0    | All checks passed                                                                                                                               |
| `apps/api`        | `uv run ruff format --check .`                                                                                          | 0    | 80 files already formatted; initial exit 1 for two fixture-formatting changes was corrected                                                     |
| root              | `npm run api:generate`                                                                                                  | 0    | OpenAPI export and TypeScript generation succeeded                                                                                              |
| root              | `npm run api:check`                                                                                                     | 1    | Its Git comparison sees the intended uncommitted new endpoints/types; staging and commits are prohibited                                        |
| root              | Regenerate and compare SHA-256 of all four generated artifacts                                                          | 0    | All four artifacts byte-for-byte unchanged after regeneration                                                                                   |
| `apps/api`        | `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest -q`                                                                     | 0    | 412 passed, 1 existing Starlette deprecation warning; includes PostgreSQL integration and migration tests                                       |
| root              | `npm run check`                                                                                                         | 1    | Svelte check could not load Vite config: EPERM writing shared `node_modules/.vite-temp`; 15 errors and 1 warning reported, not a typecheck pass |
| root              | `npm run test:frontend`                                                                                                 | 1    | Node suite: 55 passed; Vitest startup blocked by the same shared-directory write                                                                |
| root              | `BASE_PATH=/english-learning npm run build`                                                                             | 1    | Vite config startup blocked by the same shared-directory write                                                                                  |
| root              | `npm run test:browser -- tests/browser/semantic-search-flow.spec.ts`                                                    | 1    | Web-server build cannot start due to the same EPERM; no browser assertions ran                                                                  |
| root              | `npm run test:browser -- tests/browser/search.spec.ts`                                                                  | 1    | Initial incorrect filename attempt also stopped at web-server build; not counted as browser coverage                                            |

Frontend commands were not escalated because writing the shared `node_modules` is explicitly
prohibited. Consent prompt/interaction tests are not implemented because the visible UI design
is gated. Container build/runtime checks are not required for this change by the verification
matrix: no API image or runtime lifecycle files changed. Production migration/deployment and live
provider verification were not run and are outside authorization.

`npm run lint:changed -- HEAD` from root exited 0. Changed Markdown passed Prettier and
changed files passed the configured lint checks. `git diff --check` from root exited 0.
The full backend run reported one existing Starlette/httpx deprecation warning.
No test assertions were loosened. Existing embedding fixtures now explicitly grant consent;
the existing migration lifecycle test expects the new exact head revision.

## Changed files

- Backend: `apps/api/app/genai_consent.py`, `apps/api/app/embeddings.py`,
  `apps/api/app/embedding_backfill.py`, `apps/api/app/semantic_search.py`, `apps/api/app/main.py`.
- Migration: `apps/api/migrations/versions/20261105_0007_add_genai_consent.py`.
- Tests: `apps/api/tests/integration/test_genai_consent.py`, `test_card_embeddings.py`,
  `test_semantic_search.py`, `test_auth_and_authorization.py`, `test_migrations.py` in the same directory.
- Generated contracts: `apps/api/openapi.json`, `src/lib/api/generated.ts`.
- Frontend continuation: `src/lib/api/client.ts`, `src/routes/search/+page.svelte`,
  `tests/frontend/SearchPage.test.ts`, `tests/browser/semantic-search-flow.spec.ts`.
- Documentation: `apps/api/README.md`, `doc/architecture.md`, `doc/decisions.md`, and this file.

## Continuation verification (2026-11-05)

The worktree now has its own installed `node_modules`. No backend implementation, migration,
auth, workflow, or public configuration was edited in this continuation. No staging, commit,
push, merge, label change, external model call, or secret-file inspection was performed.

All commands below ran from the repository root. Output was captured in temporary files
under `/tmp/issue74-*.log`; synthetic test identities and API origins were used.

| Command                                                                                                                                                    | Exit | Observed result                                                                                                                                                                                                                     |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `npm run test:frontend -- tests/frontend/SearchPage.test.ts`                                                                                               | 1    | Initial test-harness attempt could not import the public-env virtual module. No tests ran; not counted as red-first evidence.                                                                                                       |
| `npm run test:frontend -- tests/frontend/SearchPage.test.ts`                                                                                               | 1    | After fixing the test mock, unchanged application code: 55 Node tests passed; search component had 5 failures and 1 pass. New consent prompt, withdrawal confirmation, and stale-consent cases failed because the UI was absent.    |
| `npm run test:frontend -- tests/frontend/SearchPage.test.ts`                                                                                               | 0    | Initial implementation: 55 Node tests and all 6 search component tests passed.                                                                                                                                                      |
| `npm run test:browser -- tests/browser/semantic-search-flow.spec.ts`                                                                                       | 1    | Sandboxed attempt could not bind 127.0.0.1:4173, EPERM. No browser assertions ran.                                                                                                                                                  |
| `npm run test:browser -- tests/browser/semantic-search-flow.spec.ts`                                                                                       | 1    | Retried with loopback access, temporarily restoring only the search route from HEAD: original routing/results test passed, new consent test failed because the prompt was absent. Implemented route restored immediately afterward. |
| `UV_NO_SYNC=1 UV_CACHE_DIR=/tmp/issue74-uv PYTHONDONTWRITEBYTECODE=1 npm run api:check`                                                                    | 1    | Regeneration succeeded; Git comparison reported only the intended uncommitted GenAI consent endpoint/schema/type changes in OpenAPI and generated TypeScript.                                                                       |
| SHA-256 comparison using Python `hashlib` for the four generated artifacts before and after `api:check`                                                    | 0    | All four files were byte-for-byte unchanged by regeneration.                                                                                                                                                                        |
| `npx prettier --write src/lib/api/client.ts tests/frontend/SearchPage.test.ts tests/browser/semantic-search-flow.spec.ts`                                  | 0    | Client and test files formatted.                                                                                                                                                                                                    |
| `npx prettier --write src/routes/search/+page.svelte doc/decisions.md doc/issues/issue-74-verification.md`                                                 | 2    | No parser inferred for Svelte; Markdown formatted. Corrected by explicitly selecting the installed Svelte plugin below.                                                                                                             |
| `npx prettier --plugin prettier-plugin-svelte --write src/routes/search/+page.svelte`                                                                      | 0    | Svelte formatting succeeded.                                                                                                                                                                                                        |
| `npx prettier --plugin prettier-plugin-svelte --use-tabs --single-quote --trailing-comma none --print-width 100 --write src/routes/search/+page.svelte`    | 0    | Preserved the route's existing formatting conventions.                                                                                                                                                                              |
| `npm run test:frontend`                                                                                                                                    | 0    | Before adding account reset: 55 Node tests, 133 Vitest tests in 13 files passed.                                                                                                                                                    |
| `PUBLIC_API_BASE_URL=http://127.0.0.1:8000 PUBLIC_GOOGLE_AUTH_CLIENT_ID=ci-google-client-id PUBLIC_EMAIL_WHITE_LIST=ci-user@example.invalid npm run check` | 1    | Found 3 invalid Testing Library `exact` options in new tests. Removed those unsupported options; no production type errors.                                                                                                         |
| `npm run test:frontend -- tests/frontend/SearchPage.test.ts`                                                                                               | 1    | Account-change red-first run: 6 passed, new account-change case failed against the UI without account reset.                                                                                                                        |
| `npx prettier --write tests/frontend/SearchPage.test.ts`                                                                                                   | 0    | Formatted account-change case and corrected test queries.                                                                                                                                                                           |
| `PUBLIC_API_BASE_URL=http://127.0.0.1:8000 PUBLIC_GOOGLE_AUTH_CLIENT_ID=ci-google-client-id PUBLIC_EMAIL_WHITE_LIST=ci-user@example.invalid npm run check` | 0    | 0 errors, 0 warnings after account reset.                                                                                                                                                                                           |
| `npm run test:frontend`                                                                                                                                    | 1    | Account-reset edit initially omitted assigning the semantic result; existing fallback test failed, 133 passed. Corrected the missing assignment.                                                                                    |
| `npm run lint:changed -- HEAD`                                                                                                                             | 1    | Caught the same unused semantic result. Corrected before final reruns.                                                                                                                                                              |

Final verification results:

| Command                                                                                                                                                                                | Exit | Observed result                                                                                    |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---- | -------------------------------------------------------------------------------------------------- |
| `npm run test:frontend`                                                                                                                                                                | 0    | 55 Node tests and 134 Vitest tests across 13 files passed, including all 7 search component tests. |
| `PUBLIC_API_BASE_URL=http://127.0.0.1:8000 PUBLIC_GOOGLE_AUTH_CLIENT_ID=ci-google-client-id PUBLIC_EMAIL_WHITE_LIST=ci-user@example.invalid npm run check`                             | 0    | Final rerun: 0 errors and 0 warnings.                                                              |
| `PUBLIC_API_BASE_URL=http://127.0.0.1:8000 PUBLIC_GOOGLE_AUTH_CLIENT_ID=ci-google-client-id PUBLIC_EMAIL_WHITE_LIST=ci-user@example.invalid BASE_PATH=/english-learning npm run build` | 0    | Static adapter wrote the subpath build successfully.                                               |

The exact Python hash comparison command was run after saving the four pre-regeneration hashes
in `/tmp/issue74-contract-before.json` and after `api:check` regenerated them. It exited 0:

```sh
python3 - <<'PYHASH'
import hashlib,json
before=json.load(open('/tmp/issue74-contract-before.json'))
for p,sha in before.items():
    assert hashlib.sha256(open(p,'rb').read()).hexdigest()==sha, p
print('All four generated artifacts are byte-for-byte unchanged after api:check regeneration')
PYHASH
```

The snapshot contained `apps/api/openapi.json`, `src/lib/api/generated.ts`,
`src/lib/api/card-drafts.schema.json`, and `src/lib/api/guest-snapshot.schema.json`.

| Command                                                                                                                                                 | Exit | Observed result                                                                                                                                                                                                                                    |
| ------------------------------------------------------------------------------------------------------------------------------------------------------- | ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `npm run test:browser -- tests/browser/semantic-search-flow.spec.ts`                                                                                    | 0    | With loopback access: 2 passed. Covers existing routing/partial results and mobile inline consent, zero search requests before grant, grant/search, cancel withdrawal without DELETE, confirmed DELETE, cleared results, and return to the prompt. |
| `npx prettier --write doc/decisions.md doc/issues/issue-74-verification.md`                                                                             | 0    | Documentation formatted after adding the verification evidence.                                                                                                                                                                                    |
| `npx prettier --plugin prettier-plugin-svelte --use-tabs --single-quote --trailing-comma none --print-width 100 --check src/routes/search/+page.svelte` | 0    | Svelte formatting checked explicitly because the changed-file script uses ignore-unknown and does not infer a Svelte parser.                                                                                                                       |
| `npm run lint:changed -- HEAD`                                                                                                                          | 0    | Final changed-file formatting and ESLint passed.                                                                                                                                                                                                   |
| `git diff --check`                                                                                                                                      | 0    | Final whitespace check passed.                                                                                                                                                                                                                     |

No requested frontend check remained blocked after the loopback retry. Browser tests use the
existing synthetic API fixture plus intercepted consent responses, so they establish frontend
behavior, not live FastAPI/PostgreSQL integration or provider behavior. The full browser suite
was not run; the relevant semantic-search spec was run as required by the verification table.
Backend suites were not rerun in this frontend continuation; their prior observed evidence is
preserved above. No backend code was redone or weakened. Production migration, deployment,
external model calls, and live provider tests were not run, as requested/outside scope.

## Remaining limits and assumptions

The supplied issue mirror remains assumed to be the approved, ai-ready spec, as authorized by
the maintainer's continuation request. Live GitHub labels, approval boxes, and post-approval
edits were not independently verified; `gh` remains unavailable. The UI selection is now
resolved by the maintainer's 2026-11-05 chat instruction. Keyword search is assumed to remain
outside the AI consent gate. Granting consent enables an explicit search rather than silently
submitting a query. Production rollout and live provider behavior are outside this task.

## Review follow-up

- The review found a race window between claim commit and provider call start in
  `process_card` ([embeddings.py:179](../../apps/api/app/embeddings.py#L179),
  [embeddings.py:260](../../apps/api/app/embeddings.py#L260)). The maintainer accepted it as a
  known limit; the final write recheck
  ([embeddings.py:268](../../apps/api/app/embeddings.py#L268)) prevents storing the result.
  Holding a database lock across a network call was rejected.
- Updated the consent sections in [architecture](../architecture.md#L78) and the
  [API README](../../apps/api/README.md#L389) to describe the delivered inline prompt and
  withdrawal confirmation and record the known limit.
- Corrected the status above to record commit `1d3ca15` and PR #81 and explain that
  "uncommitted" entries describe the state when the logged commands ran. The historical log
  is otherwise unchanged.
- No code or tests changed in this follow-up.
