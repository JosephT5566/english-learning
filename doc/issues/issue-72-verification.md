# Issue #72 verification

Date: 2026-11-05. Comparison base: `50939111d2b10555e7dc2debb9a681ee8e33176a`
(`origin/main`). Branch: `issue-72-card-extraction`.

Scope is the supplied maintainer-approved `/tmp/codex-72/issue-72.md`, with the owner's task
instructions taking precedence: no online documentation lookup or model call, no GitHub mutation,
no dependency additions, no changes to protected deployment/auth/migration/scheduling areas.
The supplied issue has checked approval boxes and records JosephT5566's approval. Current GitHub
label/history was not queried, per the instruction not to contact GitHub.

## Acceptance evidence

All results below are local synthetic/fake-provider evidence. Live Vertex compatibility and
quality are unverified. Test names identify parametrized cases; links point to their definitions.

| Acceptance criterion                                                                                           | Implementation / repeatable evidence                                                                                                                                                                                                                                                                                                            | Observed result                                                                                                |
| -------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Endpoint; 401 anonymous, 404 foreign/missing, 409 archived, 403 consent; provider never called                 | [test_extraction_gates_never_call_provider:74](../../apps/api/tests/integration/test_card_extraction.py#L74) asserts statuses, codes and empty calls, including archive before consent                                                                                                                                                          | Covered in 40 passing extraction integration cases                                                             |
| Strict CardDrafts; reject extras, dependent example/POS fields, >20 cards, long fields, invalid/truncated JSON | [test_invalid_output_is_rejected_without_writes:148](../../apps/api/tests/integration/test_card_extraction.py#L148); [test_generation_failures_are_stable_and_redacted:195](../../apps/api/tests/integration/test_card_extraction.py#L195); [test_response_rejects_invalid_or_truncated:138](../../apps/api/tests/unit/test_generation.py#L138) | Stable 502 codes, no cards returned; no retry                                                                  |
| Paired drafts/instruction; invalid draft fields; configured input limits; zero calls                           | [test_invalid_extraction_requests_do_not_call_provider:124](../../apps/api/tests/integration/test_card_extraction.py#L124); [test_explicit_null_adjustment_is_not_a_valid_pair:254](../../apps/api/tests/unit/test_generation.py#L254)                                                                                                          | Covered; explicit null pairs rejected conservatively                                                           |
| Deck languages exclusively; reject client language overrides                                                   | Invalid-request test above; [test_valid_extraction_uses_deck_languages_and_releases_transaction:209](../../apps/api/tests/integration/test_card_extraction.py#L209) checks deck-derived English/Traditional Chinese prompt; [prompt test:225](../../apps/api/tests/unit/test_generation.py#L225) checks Japanese prompt                         | Covered; Japanese model quality not evaluated                                                                  |
| Material/instruction injection, invalid provider output and zero learning writes                               | [test_injection_material_and_instruction_cannot_write_or_add_fields:164](../../apps/api/tests/integration/test_card_extraction.py#L164) checks extra owner/deck fields blocked and learning_cards/review_states/review_events counts unchanged                                                                                                  | 2 parametrized cases pass; validates boundary, not live-model resistance                                       |
| Timeout, quota, 5xx, auth and invalid-response classification without provider details                         | [test_provider_classifies_without_disclosing_or_retrying:157](../../apps/api/tests/unit/test_generation.py#L157) injects private exceptions/HTTP responses; [HTTP error test:195](../../apps/api/tests/integration/test_card_extraction.py#L195) checks stable ApiError mapping                                                                 | Covered by unit/integration tests, one provider call at most                                                   |
| One extraction log per request with required fields and no text/drafts                                         | [test_extraction_emits_one_private_safe_log:245](../../apps/api/tests/integration/test_card_extraction.py#L245) tests success, invalid input, anonymous and provider failure; [request_context.py:111](../../apps/api/app/request_context.py#L111) emits bounded allowlisted data                                                               | 4 parametrized cases pass; existing generic HTTP completion event also remains                                 |
| Settings/defaults; generated OpenAPI committed; api:check                                                      | [defaults/environment:56](../../apps/api/tests/unit/test_generation.py#L56), [positive bounds:78](../../apps/api/tests/unit/test_generation.py#L78); [config.py:122](../../apps/api/app/config.py#L122); generated OpenAPI/TypeScript                                                                                                           | Defaults tested; final command evidence below                                                                  |
| Existing validate/bulk and frontend manual JSON flow unchanged                                                 | Existing [test_card_drafts.py:39](../../apps/api/tests/integration/test_card_drafts.py#L39), [frontend JSON tests:1](../../tests/frontend/json-cards.test.mjs#L1); no edits to existing tests or frontend authoring implementation                                                                                                              | Full suite results below                                                                                       |
| AI-drafted answer-set proposal, types/size/review status recorded                                              | [cases.json:1](../training/issues/72/cases.json#L1), [README:3](../training/issues/72/README.md#L3), [decision](../decisions.md#2026-11-05-add-stateless-card-extraction-with-provisional-evaluation)                                                                                                                                           | 8 synthetic cases; all reviewed_by/reviewed_on null; awaiting maintainer review, not approved standard answers |
| Repeatable schema/vocabulary/limit/fabrication/injection/preservation/latency/token metrics                    | [score_case:45](../training/issues/72/evaluate.py#L45), [run_replay:201](../training/issues/72/evaluate.py#L201); [scoring tests:24](../../apps/api/tests/unit/test_extraction_evaluation.py#L24)                                                                                                                                               | Offline replay executed; metrics apply only to handwritten fixtures                                            |
| README discloses missing semantic metrics, human sampling and annotation bias                                  | [README:3](../training/issues/72/README.md#L3), [human review:21](../training/issues/72/README.md#L21)                                                                                                                                                                                                                                          | Documented; human sampling not performed                                                                       |
| Real report model/version/query/execution dates; scripts outside collection, explicit opt-in                   | [make_report:168](../training/issues/72/evaluate.py#L168), [require_vertex_opt_in:211](../training/issues/72/evaluate.py#L211), [manual mode:68](../training/issues/72/README.md#L68)                                                                                                                                                           | Reporting/guard implemented; no real report or real API execution                                              |
| Deterministic scoring/replay/fake flow in CI collection                                                        | [test_replay_uses_fake_provider_and_reports_provisional_metadata:129](../../apps/api/tests/unit/test_extraction_evaluation.py#L129) imports by `__file__`-relative path with network forbidden; HTTP tests use [ScriptedProvider:31](../../apps/api/tests/integration/test_card_extraction.py#L31)                                              | 8 scoring tests included in unit suite; 40 HTTP integration cases                                              |

Additional contracts: [schema conversion test:83](../../apps/api/tests/unit/test_generation.py#L83)
checks ref expansion, removal of unsupported keywords and nullable conversion. Server rules omitted
from the provider subset remain enforced by strict `CardDrafts` validation.
[Prompt test:225](../../apps/api/tests/unit/test_generation.py#L225) compares shared frontend/server
rule sentences. [Provider lifecycle test:195](../../apps/api/tests/unit/test_generation.py#L195)
checks lazy ADC, credential reuse, timeout, transport close and closed-provider rejection.

## Transactions and privacy

[extraction.py:130](../../apps/api/app/extraction.py#L130) finishes the auth/deck/consent transaction
before generation. The consent helper briefly takes its existing shared user lock; explicit commit
releases both lock and connection. A provider callback test obtains a runtime connection and uses
a second owner transaction with a 500ms lock timeout to withdraw consent successfully. Generated
output is a validated preview only. Consent withdrawal/archive after the snapshot cannot recall
already-transmitted material; there is no final generated-data write or persistence claim.
Authentication retains its existing user metadata updates, so "no writes" means no new extraction
learning-data/draft writes, not removal of the existing auth identity upsert contract.

## 驗證證據

Commands use `UV_CACHE_DIR=/tmp/codex-72/uv-cache` where uv is involved. The default uv cache was
sandbox-inaccessible; locked dependencies were installed once from the existing offline cache
with approved local escalation. No lockfile or package manifest changed. PostgreSQL commands used
approved access to the already-running disposable localhost service, retaining #75's restricted
`app_rls_test` fixture; no second database service or port was started.

### Red-first proof

Before any implementation:

- From `apps/api`: `uv run pytest tests/unit/test_generation.py tests/integration/test_card_extraction.py -q`:
  exit 2, two collection errors, `ModuleNotFoundError: No module named 'app.generation'`.
  Log `/tmp/codex-72/red-generation.log`. These are missing-feature import failures, not executed
  HTTP assertion failures.
- From root: `uv run --project apps/api pytest apps/api/tests/unit/test_extraction_evaluation.py -q`:
  exit 1, 8 failed because `doc/training/issues/72/evaluate.py` did not exist.
  Log `/tmp/codex-72/red-evaluation.log`.
- Explicit-null pair regression before correction: root `uv run --project apps/api pytest apps/api/tests/unit/test_generation.py -q`:
  exit 1, 3 failed, 23 passed. Null-only fields did not raise validation errors.
  Log `/tmp/codex-72/red-null-pair.log`. The pair validator was corrected without weakening assertions.

### Final commands

| Working directory | Command                                                                 | Exit | Observed result                                                                |
| ----------------- | ----------------------------------------------------------------------- | ---- | ------------------------------------------------------------------------------ |
| apps/api          | `uv run ruff check .`                                                   | 0    | All checks passed                                                              |
| apps/api          | `uv run ruff format --check .`                                          | 0    | 94 files already formatted                                                     |
| apps/api          | `uv run pytest tests/unit -q`                                           | 0    | 239 passed, 1 existing Starlette warning                                       |
| apps/api          | `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest tests/integration -q`   | 0    | 312 passed, 51 existing warnings; no skips                                     |
| apps/api          | `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest tests/eval -q`          | 0    | 10 passed; no skips                                                            |
| root              | `npm run api:generate`                                                  | 0    | OpenAPI and TypeScript generated; shared draft/snapshot JSON schemas unchanged |
| root              | `npm run api:check`                                                     | 0    | Regeneration clean after committing generated artifacts                        |
| root              | `npm run test:frontend`                                                 | 0    | Node 55 passed; Vitest 134 passed across 13 files; no skips                    |
| root              | `npm run check`                                                         | 0    | 0 errors, 0 warnings with CI-only public placeholders                          |
| root              | `npm run build`                                                         | 0    | adapter-static wrote build with CI-only public placeholders                    |
| root              | `npm run lint:changed -- origin/main`                                   | 0    | Changed-file Prettier/ESLint passed                                            |
| root              | `git diff --check`                                                      | 0    | No whitespace errors                                                           |
| root              | `docker build --tag english-learning-api:verify apps/api`               | 0    | Verification image built                                                       |
| root              | `bash apps/api/scripts/verify_container.sh english-learning-api:verify` | 0    | Non-root runtime, live/ready probes, graceful SIGTERM exit verified            |

For `check` and `build`, the process environment used the three existing CI placeholder settings
PUBLIC_API_BASE_URL, PUBLIC_GOOGLE_AUTH_CLIENT_ID and PUBLIC_EMAIL_WHITE_LIST. No public config
handling changed. Browser tests were not run because no frontend behavior or browser interaction
changed. No true-model evaluation or production/deployment check was run, as explicitly forbidden.

Logs: `/tmp/codex-72/unit-first.log`, `integration.log`, `eval.log`, `ruff-check.log`,
`ruff-format.log`, `api-generate.log`, `api-check.log`, `frontend.log`, `check.log`, `build.log`,
`lint.log`, `docker-build.log`, `container.log`. PostgreSQL integration warnings are one existing
Starlette deprecation and 50 existing pgvector reflection SAWarnings. All requested final checks
ran successfully; no test was skipped.

### Offline replay, not model quality

Root `uv run --project apps/api python doc/training/issues/72/evaluate.py --output /tmp/codex-72/replay.json`
returned exit 0. The 8 handwritten fixtures report schema pass 0.875, vocabulary recall/precision
1.0, over-limit 0.0, fabrication 0.0, ordinary-adjustment preservation 1.0. These are deliberately
scripted pipeline checks, not real-model quality numbers. Fixture tokens (10/20/30) and latency
(0ms) are synthetic. The report includes `synthetic-replay-v1`, execution timestamp and null
model-query date. No replay report is committed as live-model evidence.

### Intermediate failures and corrections

- First pytest attempt before dependency setup failed to spawn pytest, exit 2. Default offline
  `uv sync` failed on cache permission, exit 2. Approved `uv sync --locked --offline` installed
  the existing locked packages; `npm ci --ignore-scripts --offline` passed without lock changes.
- Ruff was first invoked outside the API project and could not spawn, exit 2. A later command
  used an incorrect relative path for the documentation script, exit 2. Corrected to API cwd and
  `../../doc/training/issues/72/evaluate.py`; final Ruff checks below are the evidence.
- Initial `npm run check` lacked required public test values and returned exit 1 with two missing
  exports for PUBLIC_GOOGLE_AUTH_CLIENT_ID/PUBLIC_EMAIL_WHITE_LIST. Re-ran with CI-only placeholder
  values, without `.env`, secret access or environment-handling edits.
- Frontend tests passed but printed an initial missing `.svelte-kit/tsconfig.json` warning because
  this worktree had not yet run Svelte sync. `npm run check` subsequently synchronized it.

## Independent review

The repository reviewer inspected the complete assigned uncommitted implementation at base/HEAD
`50939111d2b10555e7dc2debb9a681ee8e33176a`, with no source edits. Verdict: PASS for offline code
correctness, no actionable defects. Independent focused unit checks: 34 passed; Ruff `app tests`
check passed; format check reported 83 formatted files. The reviewer inspected transaction/strict
validation/evaluation boundaries but did not repeat full PostgreSQL/frontend checks. No UI changed.
This verdict excludes true-provider compatibility and pending human dataset review.
A follow-up documentation/evidence review also returned PASS: local links resolve, saved logs
support the reported final counts/checks and the docs distinguish replay from real-model evidence.
Neither review edited source files.

## Decisions and unverified work

[Decision record](../decisions.md#2026-11-05-add-stateless-card-extraction-with-provisional-evaluation)
explains defaults, eight-case proportions and pending reviewer assignment. [generation.py:1](../../apps/api/app/generation.py#L1)
explicitly labels request/response/schema contracts unverified. Inputs are JSON data separate from
system rules; validation, not a promise of model compliance, is the server guarantee.

Unverified: Vertex generation REST path/request/response; accepted response-schema subset;
current model identifiers/availability and IAM/ADC permissions; real-model scores, latency and
cost; human correctness of meanings/examples; standard-answer per-case review and sampling;
Japanese extraction quality; production traffic/deployment, current GitHub state and merge CI.
No model/API documentation query, real model call, production connection, GitHub change, push,
PR, merge or deployment occurred. No new dependency or protected-area change was made.

The original issue asks for a current documentation lookup and a reviewed standard answer set.
The owner's task instructions instead prohibit that lookup and require null reviewer/date fields.
The conservative result is an unverified adapter and explicitly provisional set, with manual
maintainer steps documented rather than fabricated evidence.

## PR #85 review fixes

Review-fix comparison base: `71b66f7016297ecf8fe1af468ae266a2d9f6bc91`, 2026-11-05.
The maintainer supplied two code defects and reserved the other two blocking items (answer-set
review and real-model evaluation) for themselves. No GitHub query or mutation was performed.
The earlier local PASS verdicts above describe the original review scope and do not establish
that its handwritten response fixtures covered these newly reproduced cases.

### Defects and decisions

1. [generation.py:132](../../apps/api/app/generation.py#L132) now explicitly permits only text,
   thought and thoughtSignature keys in text parts. Metadata types are checked; thought=true
   summaries and signatures never enter the final answer. Every part, including excluded thoughts,
   must still be text-only under that allowlist. Unknown keys and mixed tool/media fields fail
   closed. This is based on the review-cited Vertex Content REST reference, which remains
   unverified because this task prohibits online documentation lookup or real model calls.
2. [generation.py:253](../../apps/api/app/generation.py#L253) now catches requests JSONDecodeError,
   ContentDecodingError and ChunkedEncodingError before generic RequestException handling. The
   endpoint maps invalid_response to non-retryable 502 generation_invalid_response. Ordinary
   connection errors and HTTPError status classification retain existing behavior.

Local installed requests 2.34.2 inspection established that Response.json() wraps JSON failures
in requests.JSONDecodeError, which inherits both RequestException and ValueError. Response
iter_content translates underlying decode/protocol errors into ContentDecodingError and
ChunkedEncodingError; Session.send consumes response.content by default before returning a
non-streamed response. The new handler covers these body errors whether raised during post or
while reading JSON. Other connection/read/SSL transport behavior was not broadened; the existing
connection-error tests remain in place. Audit: `/tmp/codex-72/fix-requests-audit.log`.
No actual malformed HTTP server, compression stream or live Vertex response was used.

### Red-first evidence

Before changing generation.py:

| Working directory | Command (with UV_CACHE_DIR=/tmp/codex-72/uv-cache)                                                     | Exit | Observed failure                                                                                                                                                                              |
| ----------------- | ------------------------------------------------------------------------------------------------------ | ---- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| root              | `uv run --project apps/api pytest apps/api/tests/unit/test_generation_response_parts.py -q`            | 1    | 6 failed, 27 passed: 3 valid metadata/final-text cases incorrectly raised invalid_response; real JSON decode and 2 body-read failures raised provider_unavailable instead of invalid_response |
| apps/api          | `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest tests/integration/test_generation_response_http.py -q` | 1    | 4 failed: signed final answer returned 502 instead of 200; malformed JSON/content/chunk bodies returned 503 instead of 502                                                                    |

Logs: `/tmp/codex-72/fix-red-unit.log` and `fix-red-http.log`. These are executed behavior
failures, not collection/setup failures. Existing assertions/tests were not changed or weakened.

### Green behavior evidence

- [test_final_text_accepts_review_documented_metadata:37](../../apps/api/tests/unit/test_generation_response_parts.py#L37)
  checks text plus signature with absent/false thought;
  [test_only_final_text_parts_are_combined_in_order:44](../../apps/api/tests/unit/test_generation_response_parts.py#L44)
  excludes interleaved thought summaries and preserves final answer order.
- [test_non_text_content_and_unknown_keys_are_rejected:76](../../apps/api/tests/unit/test_generation_response_parts.py#L76)
  covers functionCall, functionResponse, inlineData, fileData, executableCode,
  codeExecutionResult and unknown keys, both with and without text. Additional tests reject
  malformed metadata, thought-only output, empty/non-string text, mixed thought/tool content,
  multiple candidates and unsupported finish reasons. Existing MAX_TOKENS rejection is retained.
- [test_real_requests_json_decode_error_is_invalid_response:127](../../apps/api/tests/unit/test_generation_response_parts.py#L127)
  calls actual Response.json() on a synthetic HTTP 200 non-JSON body, asserts the actual exception
  inheritance and provider invalid_response without retry/message leakage. The prior general
  ValueError test remains unchanged in test_generation.py.
- [test_body_decoding_or_chunk_failure_is_invalid_response:155](../../apps/api/tests/unit/test_generation_response_parts.py#L155)
  uses real Response.json()/iter_content with synthetic raw.stream errors to exercise requests'
  actual decode/chunk exception translation. This is local exception-path evidence only.
- [test_signed_final_text_reaches_endpoint_as_valid_cards:44](../../apps/api/tests/integration/test_generation_response_http.py#L44)
  uses the real adapter/parser with fake HTTP and ADC, returns 200 with validated cards, excludes
  thought/signature values and preserves learning-data counts.
- [test_malformed_provider_body_is_502_nonretryable:89](../../apps/api/tests/integration/test_generation_response_http.py#L89)
  covers all three body failures, checks 502 generation_invalid_response, retryable=false, one
  call, no provider-body leakage and unchanged learning-data counts.

Focused green commands: root `uv run --project apps/api pytest apps/api/tests/unit/test_generation.py apps/api/tests/unit/test_generation_response_parts.py -q`
returned exit 0, 59 passed; API `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest tests/integration/test_generation_response_http.py -q`
returned exit 0, 4 passed. Both used the task uv cache; logs `fix-green-unit.log`, `fix-green-http.log`.

### Final review-fix verification

All commands below ran with `UV_CACHE_DIR=/tmp/codex-72/uv-cache` for uv; PostgreSQL checks
used the existing localhost disposable service and unchanged restricted-role fixture.

| Working directory | Command                                                               | Exit | Observed result                            |
| ----------------- | --------------------------------------------------------------------- | ---- | ------------------------------------------ |
| apps/api          | `uv run ruff check .`                                                 | 0    | All checks passed                          |
| apps/api          | `uv run ruff format --check .`                                        | 0    | 96 files already formatted                 |
| apps/api          | `uv run pytest tests/unit -q`                                         | 0    | 272 passed, 1 existing Starlette warning   |
| apps/api          | `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest tests/integration -q` | 0    | 316 passed, 51 existing warnings, no skips |
| apps/api          | `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest tests/eval -q`        | 0    | 10 passed, no skips                        |
| root              | `npm run lint:changed -- origin/main`                                 | 0    | Changed-file Prettier/ESLint passed        |
| root              | `git diff --check`                                                    | 0    | No whitespace errors                       |
| root              | `npm run api:check`                                                   | 0    | Internal regeneration produced no drift    |

Logs under `/tmp/codex-72/`: `fix-ruff-check.log`, `fix-ruff-format.log`, `fix-unit.log`,
`fix-integration.log`, `fix-eval.log`, `fix-lint.log`, `fix-diff-check.log`, `fix-api-check.log`.
Integration warnings are the existing Starlette deprecation and 50 pgvector reflection warnings.
A scoped independent reviewer returned PASS against the frozen three-file code/test change,
re-ran 59 focused unit tests, Ruff check/format and diff check successfully, and inspected both
red logs. This does not establish true-provider compatibility. No source edits followed that review.

An intermediate Ruff check returned exit 1 because an earlier root-cwd autofix sorted the two new
test imports differently from API-cwd rules. The chained full unit command did not run on that
attempt. Corrected only the new imports from apps/api and ran the successful checks above.
No frontend, route, public-model or runtime lifecycle change occurred, so frontend/build/browser/
container suites were not repeated. API check internally regenerates artifacts; no separate
api:generate invocation was necessary.

### Limits and maintainer-owned blockers

Vertex Content REST documentation, request/response/schema compatibility, model IDs/IAM and all
real-model quality/cost/latency remain unverified. No online lookup, model call or production
access occurred. Unknown metadata can still be rejected intentionally; extensions require review.
No request/response model changed. API check regenerates internally and confirmed no artifact drift.
The answer-set cases and all review fields are unchanged; per-case review and true-model evaluation
remain outstanding maintainer work. No dependency, workflow, migration, environment/auth/static-path
or scheduling change was made. No push, amend or rebase was performed.
