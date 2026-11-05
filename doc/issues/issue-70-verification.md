# Issue 70 backend verification

Date: 2026-11-05. Base: `2759a8b` (`origin/main`). Branch: `issue-70-assistant-backend`.
Scope: issue Scope 1-6, 11-12 and backend/evaluation acceptance only. The supplied local
issue snapshot has ai-ready and checked approvals; GitHub was not queried or modified.
No model API, production service or online documentation was accessed. No frontend UI,
dependency, workflow, migration, auth/GIS contract, public environment handling, deployment
path or srs-v1 change is included. Generated TypeScript is the only `src/` change.

## Acceptance evidence

Paths below are repository-relative. Line numbers identify the implementation or test entry.
Tests use handwritten/scripted responses and local disposable PostgreSQL, not live models.

| Backend acceptance                                                                     | Evidence                                                                                                                                      | Observed result                                                                                                                                                            |
| -------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Endpoint, 401, consent 403 and zero provider calls                                     | `app/assistant/routes.py:34`; `tests/integration/test_assistant_http_boundaries.py:82`                                                        | Targeted HTTP suite: 26 passed. Gates assert zero calls; missing model is stable 503 generation_not_configured.                                                            |
| Exactly three registry names and exact schemas                                         | `app/assistant/tools.py:19`; `tests/unit/test_assistant_contracts.py:104`                                                                     | Exact schema/list equality passes; adding a name or schema field breaks the assertion.                                                                                     |
| No owner/user argument; unknown names, extras and invalid arguments do not execute     | `app/assistant/tools.py:78`; `tests/unit/test_assistant_contracts.py:230`, `:327`                                                             | Fixed invalid_tool_call responses, no execution; invalid summaries omit arguments.                                                                                         |
| Settings enforce steps, total deadline, output tokens and history limits               | `app/config.py:140`; `app/assistant/loop.py:85`; `tests/unit/test_assistant_contracts.py:174`, `:193`, `:248`, `:266`, `:304`                 | Three model calls maximum; last request disables tools; oversized batches execute zero calls; token cap sent and over-reported output rejected. Late results discarded.    |
| Final step without final text returns fixed max_steps                                  | `tests/unit/test_assistant_contracts.py:340`; `app/generation.py:174`                                                                         | Handwritten REST thoughts-only final NONE fixture reaches fallback; default parser still rejects it for extraction.                                                        |
| Tool role, extra fields, count/total characters return 422 before consent/provider     | `tests/integration/test_assistant_http_boundaries.py:113`, `:331`                                                                             | Default and custom limits tested; malformed unauthenticated request remains 401.                                                                                           |
| Foreign deck across all three tools under restricted role                              | `tests/integration/test_assistant_http_boundaries.py:141`                                                                                     | Request owner A uses B's fixture deck. Search/due sanitized unavailable, stats zero, embedding zero calls; runtime role asserted app_rls_test.                             |
| Owned-card injection attempts unknown tool and owner override; no writes               | `tests/integration/test_assistant_http_boundaries.py:184`                                                                                     | Malicious card reaches scripted provider; both attempts blocked. Counts of all public tables unchanged. Harness boundary only, not model resistance.                       |
| Due/statistics share condition and agree on same data                                  | `app/reads.py:458`; `app/assistant/tools.py:100`; `tests/integration/test_assistant_http_boundaries.py:212`, `:350`                           | Same snapshot tests equality, exact due boundary, future reviews, English/Japanese, archived card and archived deck.                                                       |
| Existing semantic-search and reviews/due assertions unchanged                          | `app/semantic_search.py:100`; `app/reads.py:463`; existing `tests/integration/test_semantic_search.py` and `test_read_apis.py`                | Full integration suite recorded below; no existing test file changed.                                                                                                      |
| Transaction/lock release with RLS rebinding                                            | `app/assistant/routes.py:66`; `app/assistant/tools.py:130`; `tests/integration/test_assistant_http_boundaries.py:212`, `:287`, `:413`, `:462` | Actual checked-out pool count zero during generation/embedding. Consent cancellation maps to timeout. Caller returns while blocked consent worker owns/cleans its session. |
| Every model step logs correlation, step, tool names, status, time, tokens without text | `app/assistant/loop.py:69`; `tests/unit/test_assistant_contracts.py:193`; `tests/integration/test_assistant_http_boundaries.py:212`           | Exact fields/step count asserted; user/card markers absent. Unknown names sanitized to unknown; arguments/signatures not logged.                                           |
| Regenerated OpenAPI and client artifacts                                               | `apps/api/openapi.json`; `src/lib/api/generated.ts`; generation/check logs below                                                              | api:generate and api:check exit 0. No handwritten frontend code.                                                                                                           |

Implementation/test paths beginning `app/` and `tests/` in this table are under `apps/api/`.

| Evaluation acceptance                                                                                                      | Evidence                                                                                                                      | Observed result                                                                                                                                                    |
| -------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Synthetic proposed case set with tools/key arguments                                                                       | `doc/training/issues/70/cases.json:1`; `README.md:1`                                                                          | Eight original cases. Every reviewed_by/reviewed_on is null. AI drafted, pending individual maintainer review; not approved ground truth.                          |
| Repeatable evaluator outputs selection/argument accuracy, steps, per-case latency/tokens, security outcomes and model/date | `doc/training/issues/70/evaluate.py:108`, `:182`, `:208`; `tests/unit/test_assistant_evaluation_scoring.py:21`, `:68`, `:107` | Offline replay executed; provisional true. Failure/timeout cannot score success; vacuous empty foreign result cannot pass security. No live quality score claimed. |
| Real-model scripts/assets outside pytest and explicit manual opt-in                                                        | `doc/training/issues/70/evaluate.py:218`, `:242`; `tests/unit/test_assistant_evaluation_scoring.py:92`                        | True mode requires --vertex plus ENABLE_ISSUE70_VERTEX_EVAL=1 and explicit model/project/date. No workflow/CI env changed. True mode not executed.                 |

Task scores require exact ordered permitted tool names and exact expected argument-key values.
Denied attempts are excluded from task-selection scores but preserved in actual/security results.
Semantic query paraphrases can score poorly; these rules are not a semantic quality oracle.
True mode also uses synthetic tools and does not measure real semantic retrieval. Replay token
counts are handwritten constants and latency is local replay latency. See the evaluation README.

## Red-first evidence

All uv commands below use `UV_CACHE_DIR=/tmp/codex-70/uv-cache`.

1. Before assistant product code existed, from `apps/api`:
   `uv run pytest tests/unit/test_assistant_contracts.py -q` failed collection with
   `ModuleNotFoundError: No module named 'app.assistant'` (pytest exit 2).
   Log `/tmp/codex-70/red-unit.log`. Final baseline copy run also failed collection;
   `/tmp/codex-70/red-unit-final.log`.
2. The first HTTP attempt was blocked by sandbox TCP permission, not behavioral proof.
   Exported untouched base `2759a8b` using git archive to `/tmp/codex-70/baseline` and copied
   only new tests there. From root, with local database access:
   `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run --project apps/api pytest /tmp/codex-70/baseline/apps/api/tests/integration/test_assistant_http_boundaries.py --override-ini pythonpath=/tmp/codex-70/baseline/apps/api -q`.
   Exit 1, all 23 then-current tests failed against the absent endpoint/services/function-call
   adapter. Log `/tmp/codex-70/red-http-baseline-final.log`. Initial 20-test run also failed all 20.
3. Before evaluator existed, from root:
   `uv run --project apps/api pytest apps/api/tests/unit/test_assistant_evaluation_scoring.py -q`.
   Exit 1, 3 failed with missing evaluate.py; `/tmp/codex-70/red-eval.log`.
4. Independent review exposed scoring/deadline gaps. New failure-case scoring test on the
   implementation before correction: exit 1, 2 failed, 3 passed;
   `/tmp/codex-70/red-review-scoring.log`. New blocked initial-consent HTTP test: exit 1,
   1 failed, observed HTTP 500 after its four-second test blocker, not timeout;
   `/tmp/codex-70/red-review-deadline.log`.
5. New initial/repeated consent SQLSTATE 57014 tests before correction: exit 1, 2 failed,
   observed 503 database_unavailable instead of timeout;
   `/tmp/codex-70/red-consent-cancel.log`.
6. New final-NONE thoughts-only REST test before correction: exit 1, 1 failed with
   invalid_response instead of fixed max_steps; `/tmp/codex-70/red-final-empty.log`.

The tests were not weakened or deleted after these failures. The blocked-consent test was
extended to await its worker's cleanup before dropping its disposable database, preserving
all response/deadline assertions.

## Checks actually run

All API commands run from `apps/api`, using the cache prefix above. PostgreSQL tests use
existing local pg72 and unchanged restricted-role fixture app_rls_test. No SQLite substitute.
Commands here are local evidence, not a substitute for CI or production verification.

| Working directory | Command                                                                                                    | Exit | Observed result                                     |
| ----------------- | ---------------------------------------------------------------------------------------------------------- | ---- | --------------------------------------------------- |
| apps/api          | `uv run ruff check .`                                                                                      | 0    | All checks passed                                   |
| apps/api          | `uv run ruff format --check .`                                                                             | 0    | 107 files already formatted                         |
| apps/api          | `uv run pytest tests/unit -q`                                                                              | 0    | 334 passed, 1 existing Starlette warning            |
| apps/api          | `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest tests/integration -q`                                      | 0    | 351 passed, 51 existing warnings                    |
| apps/api          | `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest tests/eval -q`                                             | 0    | 10 passed                                           |
| apps/api          | `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest tests/unit tests/integration tests/eval --collect-only -q` | 0    | 695 collected without import mismatch               |
| root              | `find apps/api/tests -name "test_*.py" \| xargs -n1 basename \| sort \| uniq -d`                           | 0    | Empty output, no duplicate test basenames           |
| root              | `npm run api:generate` then `npm run api:check`                                                            | 0    | Artifacts generated and committed; no drift         |
| root              | `npm run test:frontend`                                                                                    | 0    | Node tests 55 passed; Vitest 134 passed in 13 files |
| root              | `npm run check` with existing CI public placeholders                                                       | 0    | 0 errors, 0 warnings                                |
| root              | `npm run lint:changed -- origin/main`                                                                      | 0    | All matched files use Prettier code style           |
| root              | `git diff --check`                                                                                         | 0    | No whitespace errors                                |
| root              | `uv run --project apps/api python doc/training/issues/70/evaluate.py --output /tmp/codex-70/replay.json`   | 0    | Eight scripted cases; provisional true              |

Logs are `/tmp/codex-70/{ruff-check,ruff-format,unit-green,integration-green,eval-green,collect-final,api-generate-final,api-check,frontend,check-final,lint-changed,replay}.log`.
Targeted final HTTP log `/tmp/codex-70/assistant-http-green.log`: 26 passed, 1 warning.
Independent reviewer final verdict PASS, focused unit 28 passed; local report
`/tmp/codex-70/review-final.md`. This is a local review, not a GitHub approval.

Skipped: browser/UI/static build and container lifecycle checks, because no handwritten frontend,
route/base-path/build configuration, image or process lifecycle changed. True Vertex evaluation
was prohibited and not run. No production database or model API was contacted.

## Decision-log draft for maintainer confirmation

| Decision                | Chosen default/range                                                                              | Rationale/status                                                                                                |
| ----------------------- | ------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Response                | Non-streaming single response; no conversation storage                                            | Maintainer instruction confirms; no migration                                                                   |
| Model steps             | 3 / 1-3                                                                                           | Short bounded reasoning/tool loop; one step = one model call                                                    |
| Total budget            | 60 seconds / 1-120                                                                                | One deadline after auth/validation/auth commit covers consent, pool waits, tools and providers                  |
| Output tokens/call      | 2048 / 1-8192                                                                                     | Room for a concise grounded answer while limiting output                                                        |
| Input messages          | 20 / 1-100                                                                                        | Short client-carried history                                                                                    |
| Total input characters  | 12000 / 1-100000                                                                                  | Bound history by character count, independent of encoding                                                       |
| Calls/model step        | 3 / 1-10                                                                                          | Small batches; oversized batches execute nothing                                                                |
| Search/due result limit | Default 5, clamp 1..ASSISTANT_TOOL_LIMIT; cap default 10 / 1-20                                   | Avoid returning large card collections; stats has no limit                                                      |
| Final tool disabling    | Keep declarations and send functionCallingConfig mode NONE                                        | Explicit prohibition; unverified on Vertex, needs maintainer live confirmation                                  |
| Transaction strategy    | Worker-owned owner-bound session; short readonly queries; release before generation/embedding     | Avoid long shared consent locks. Caller timeout cannot close an active worker session. No auth contract change. |
| Timeout response        | Fixed reply and timeout. Outer watchdog has empty tool_calls/null usage                           | No concurrent reading of live worker state. Partial summaries/usage may be unavailable.                         |
| Dataset                 | 8 AI-drafted synthetic cases; null review metadata                                                | Small coverage set, not statistically representative; all cases await per-item maintainer approval              |
| Scoring                 | Exact ordered permitted names and expected key subsets; failed/incomplete execution never success | Reproducible but paraphrase-sensitive; denied calls retained separately                                         |

Numeric tuning, corpus expectations and live compatibility remain pending maintainer confirmation.
This draft was not posted to GitHub. A PR body draft is local only.

## Problems encountered and corrections

- uv initially could not spawn pytest; default sandbox dependency download hit DNS restrictions.
  Installed unchanged locked dependencies with permitted network access. Existing local installed
  packages were temporarily copied into the ignored venv during bootstrap; the locked sync
  completed, and the pytest launcher was corrected to this worktree's interpreter. No dependency
  or lockfile changed.
- Initial archive command ran from apps/api with a root-relative path and failed; corrected to root.
  An initial root-level pytest command used an apps/api-relative test path and failed discovery.
  Neither is behavioral evidence.
- Raw `npm run check` without public placeholders failed with two missing generated env exports
  in existing auth.ts. Re-ran with exactly the existing CI non-secret placeholders; no .env file
  or public environment handling was changed.
- Early Ruff checks found loop closure/import/formatting issues; corrected before final checks.
- Independent review found the deadline began after initial consent, failures could score as
  no-tool success, foreign security could pass vacuously, and an extra pool checkout was not
  proof of connection release with a pool of five. Added regression assertions and corrected
  the implementation. A blocked-consent test first hit database-in-use at teardown because its
  background worker had not closed yet; added explicit worker-completion synchronization.
- Scoped follow-up caught SQL cancellation classification and final thoughts-only wire/fake
  mismatch. Both received red-first regressions and narrow corrections.

## Differences and evidence limits

The issue's earlier single-request-transaction suggestion conflicts with avoiding transactions
across long external waits. Chosen conservative design creates one owner-bound orchestration
session and short transactions; after_begin reapplies RLS identity after each commit/rollback.
Auth and request validation, including committing their existing transaction, are preconditions
to the assistant budget. The outer response deadline can expire before a worker finishes cleanup.
Statement timeouts help bound SQL, but Python cannot cancel a running database checkout, ADC or
HTTP operation. A late worker must finish/abort its operation, observe the shared deadline and
close its session. It cannot begin another model/tool call after that check. This is a response
wait bound, not remote cancellation, billing cutoff or a deployment capacity guarantee.

Unverified items requiring operator/maintainer work:

- Function-calling REST contents/declarations/functionCall/functionResponse format on real Vertex.
- Gemini multi-turn thoughtSignature replay requirements and acceptance; preserved-byte tests use handwritten parts only.
- Tool parameter schema subset in Vertex; minimal keywords deliberately omit numeric/length/array constraints. Server validation remains strict.
- Final-step NONE behavior with the selected model; no guarantee the provider obeys it. Server executes no final-step tools.
- Real-model evaluation quality, latency, token/cost behavior, model availability/version and IAM.
- All eight case expectations await per-case review; no approved gold set or real-model score.
- Streaming and Neon pooled/transaction-mode effects on transaction-local set_config/app.user_id.
- Production restricted-role rollout, pool capacity under abandoned in-flight calls, concurrent load,
  remote cancellation, shutdown during timed-out workers and production retention/consent copy suitability.

Reviewers should focus on owner/session lifetime across the outer deadline, consent rechecks,
readonly ranking after embedding, strict fixed registry/schema drift, unchanged old query contracts,
parser allow_empty restricted to final tool-disabled requests, and evaluator failure denominators.
