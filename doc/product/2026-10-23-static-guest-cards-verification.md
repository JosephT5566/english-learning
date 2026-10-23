# Static guest cards verification

Historical record for PR #58. The later
[separate export verification](2026-10-23-separate-guest-export-verification.md) supersedes the
same-run export/Pages dependency and ignored-snapshot publication model described below.

Date: 2026-10-23 (Asia/Taipei). Worker verification and independent reviewer PASS.
Checkout: `/Users/joseph/Documents/Git/english-learning`, branch `codex/static-guest-cards`.
Review base: `80b57736ba3ba950d77f2cb9da02d077278ab853`.
Final local implementation commit: `1884a0e6772ce54800fa2426ea98ba5cb8a5a11d`.
The reviewer included the worker's documentation-only evidence follow-up in its review.
The parent added the final verdict below after source review; no application code changed.

## Implemented behavior

- Supporting backend release `34c7560` retains the old anonymous route while adding the protected
  exporter. The final target removes the anonymous route, settings and source admission code.
- Export verifies a dedicated Google service-account identity before database checkout and uses
  an explicit content projection, read-only transaction, statement timeout and one nonblocking permit.
  Missing/wrong-language decks fail; archived/empty decks produce intentional empty snapshots.
- Snapshots have version 1, an aware generation timestamp, at most 50 distinct English cards,
  and a 512 KiB limit. Generated schema and shared runtime validation reject private/extra fields.
- Downloader rejects non-HTTPS origins, redirects, bad/oversized data and timed-out streams;
  rejected bodies are cancelled, request cleanup aborts transport, and output replacement is atomic.
  Logs contain only counts/bytes or fixed safe errors. Tokens use environment input only.
- Pages/export workflow has only manual dispatch, trusted-main gating, protected environments,
  dedicated WIF impersonation and sanitized same-run artifact transfer. Build gets no Google token.
- Guest downloads the base-aware static asset once per mount and samples at most ten cards locally.
  Repeated rounds do not call the API. Existing guest deadline, private recovery and flip-first
  interactions remain covered by browser checks. No real card content is committed.

## Observed checks

| Command                                                                                                                         | Observed result                                                                                                   |
| ------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `apps/api/.venv/bin/python -m pytest apps/api/tests/unit/test_guest_export.py -q` before implementation                         | Initial settings/auth feature tests failed as expected                                                            |
| `node --test tests/frontend/export-guest-cards.test.mjs`                                                                        | 19 passed, including two cancellation tests observed failing before the cleanup fix                               |
| `npm run check`                                                                                                                 | 0 errors, 0 warnings                                                                                              |
| `npm run test:frontend`                                                                                                         | 42 Node tests and 116 Vitest tests passed                                                                         |
| From `apps/api`, `.venv/bin/ruff check .` and `.venv/bin/ruff format --check .`                                                 | Passed                                                                                                            |
| From `apps/api`, `.venv/bin/python -m pytest tests/unit -q`                                                                     | Final 181 passed                                                                                                  |
| From `apps/api`, `RUN_POSTGRES_INTEGRATION_TESTS=1 .venv/bin/python -m pytest tests/integration -q`                             | Supporting release 187 passed; final route-removal target 184 passed                                              |
| From `apps/api`, `RUN_POSTGRES_INTEGRATION_TESTS=1 .venv/bin/python -m pytest tests/integration/test_guest_export.py -q`        | 2 passed after adding valid maximum-length multibyte payload coverage                                             |
| `npm run test:browser -- tests/browser/guest-review-flow.spec.ts tests/browser/review-flow.spec.ts`                             | Root-hosted 36 passed                                                                                             |
| `BASE_PATH=/english-learning npm run test:browser -- tests/browser/guest-review-flow.spec.ts tests/browser/review-flow.spec.ts` | Subpath-hosted 36 passed                                                                                          |
| `npm run test:browser -- tests/browser/guest-review-flow.spec.ts` after resource-cleanup fix                                    | Root-hosted 17 passed                                                                                             |
| `BASE_PATH=/english-learning npm run test:browser -- tests/browser/guest-review-flow.spec.ts` after resource-cleanup fix        | Subpath-hosted 17 passed                                                                                          |
| Root/subpath `npm run build` inside Playwright webServer startup                                                                | Both static builds passed using synthetic fixtures                                                                |
| `docker build --tag english-learning-api:verify apps/api`                                                                       | Passed                                                                                                            |
| `bash apps/api/scripts/verify_container.sh english-learning-api:verify`                                                         | Passed; minimal non-root runtime, meaningful probes and graceful SIGTERM exit                                     |
| `npm run lint:changed -- 80b57736ba3ba950d77f2cb9da02d077278ab853`                                                              | Passed                                                                                                            |
| `git diff --check`                                                                                                              | Passed                                                                                                            |
| `bash -n deploy/cloud-run/release.sh`                                                                                           | Passed                                                                                                            |
| `UV_CACHE_DIR=/tmp/english-learning-uv-cache npm run api:check`                                                                 | Passed after final local commit; regeneration produced no OpenAPI, TypeScript, card-draft or snapshot-schema diff |

The integration fixture creates and drops isolated `api_test_*` PostgreSQL databases with
pgvector. The first sandboxed TCP attempt was denied; the escalated local run succeeded.
Initial root browser verification found one assertion still watching the removed anonymous
URL; after migrating it to the static URL, all 36 tests passed. The first extra size fixture
exceeded a database meaning-length constraint; valid multibyte fields replaced it, and the
actual oversized export then returned a safe 422 without changing learning tables.

Existing test-tool warnings were Starlette's httpx deprecation and Playwright's color environment
warning. Ruff initially run from the repository root selected a different import configuration;
the required checks were rerun from `apps/api` and passed. No unrelated baseline files were changed.

## Evidence limits and rollout prerequisites

No live API export, real content inspection, IAM binding, cloud-resource modification, workflow
dispatch, publication, promotion, production migration, push or merge occurred. WIF claims,
protected-environment approvals/branch restrictions and actual service-account configuration must
be set and verified operationally before the first run. Local tests use mocked identity verification
at Google's external boundary; they do not prove live WIF token minting.

Deploy support `34c7560` first, manually publish/verify static Pages second, and deploy final
anonymous-route removal last. Failure retains previous deployed content. Old public snapshots
cannot be recalled from downloaders; edits/archive only affect the next successful publication.
The local support ref was created before anonymous-route retirement and has not been pushed.

Interactive reviewer startup and root/subpath URLs are in
[development.md](../development.md#local-verification-and-reviewer-setup). Worker Playwright checks
cover actual Chrome desktop/mobile flows. Independent DevTools inspection is recorded below.
The unrelated untracked `2026-10-21-guest-review-plan.md` was preserved.

## Independent reviewer verdict

PASS on 2026-10-23. Reviewed base `80b57736ba3ba950d77f2cb9da02d077278ab853` through
implementation `1884a0e6772ce54800fa2426ea98ba5cb8a5a11d`, including the assigned evidence
follow-up and excluding the unrelated proposal. No actionable defects or blocked local checks
remain. The comments and suppression review found no correctness-hiding suppression or
actionable comment finding. No source correction round was needed.

The reviewer independently reproduced the following results:

- `npm run check`: zero errors and warnings.
- `npm run test:frontend`: 42 Node tests and 116 Vitest tests passed.
- API Ruff check and formatting: passed. API unit suite: 181 passed.
- Full disposable PostgreSQL integration suite: 184 passed.
- Guest and private Playwright suites: 36 passed at root and 36 at `/english-learning`.
- Root and subpath static builds, `npm run api:check`, changed-file lint, `git diff --check`,
  release shell syntax, Docker build and container runtime verification: passed.

DevTools used a dedicated local page at `http://127.0.0.1:4173/english-learning/review`, with
desktop 1280 by 850 and mobile 390 by 850 viewports. Guest flip-before-answer, grading,
completion and Practice again worked. Each mount produced one static JSON download and zero
`/v1/` calls. Neither viewport had horizontal overflow. Synthetic private review fetched owned
cards and submitted successfully. There were no application console errors; Google emitted
the expected invalid-client-ID error for the synthetic sign-in configuration.

Reviewer logs remain local at `/tmp/reviewer-postgres.log`, `/tmp/reviewer-browser-root.log`,
`/tmp/reviewer-browser-subpath.log`, and `/tmp/reviewer-container.log`. Fixture servers were
stopped. The review did not change source, history, cloud resources, or production data.
Live WIF, IAM, environment restrictions, actual card export and publication remain unverified
operational prerequisites, as described above.

## CI collection correction

The first PR run exposed a collection failure missed by running the unit and integration
suites in separate processes. Both new modules were named `test_guest_export.py`, so pytest's
default import mode loaded the integration module under the unit module's expected basename.
Running `.venv/bin/python -m pytest --collect-only -q` reproduced the CI import mismatch locally.

Rename the integration module to `tests/integration/test_guest_export_transactions.py`.
Keep its unit-helper import and the existing pytest configuration unchanged. Combined collection
then found all 365 tests without errors. With the CI test environment and disposable PostgreSQL,
`uv run pytest -q` passed all 365 tests in one process. Ruff check, Ruff format check, and
`git diff --check` also passed. The existing Starlette/httpx deprecation warning is unrelated.
Full local output is retained at `/tmp/english-learning-ci-backend.log`; this correction changes
test discovery only, with no application or API behavior change.
