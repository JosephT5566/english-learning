# Issue 100 local verification, 2026-11-13

All work is local on `issue-100-raise-step-cap`, based on
`a2228227bb324a55b09cc4affd30190b92856f52`. No commit, push, PR, GitHub write,
label change, reset or rebase was performed. Vertex was not run. No evaluator constructed a live Vertex
provider. Refusal tests replace constructors; existing adapter unit tests use
mocked auth/network dependencies and make no live model calls. Existing unit tests exercise
mocked routing gates, not standalone #71/#72 evaluation runs.

## Execution isolation

The worktree has no installed Python environment. Commands reused the existing
main-checkout dependency environment without syncing or modifying it. Every `uv`
verification/replay command used this prefix (the first formatting commands did
not need the Python guard, since ruff does not load application settings):

```bash
UV_PROJECT_ENVIRONMENT=/Users/joseph/Documents/Git/english-learning/apps/api/.venv UV_NO_SYNC=1 UV_CACHE_DIR=/tmp/codex-100/uv-cache PYTHONPATH=/tmp/codex-100/no-env
```

`/tmp/codex-100/no-env/sitecustomize.py` contains only:

```python
from pydantic_settings.sources import DotEnvSettingsSource
DotEnvSettingsSource._read_env_files = lambda self: {}
```

This prevents dotenv reads even for existing tests that call `load_settings()`.
Evaluator Settings construction also explicitly uses `_env_file=None`. No `.env`
was read, printed or changed. No live opt-in was exported and no evaluator command
used `--vertex`. The replay path uses handwritten providers only.

The worktree's ignored `node_modules` symlink points to the existing main-checkout
installation so local Prettier/ESLint can run offline. No install or lockfile change.

## Red-first evidence

These tests were run before changing config or evaluator implementation:

| Working directory | Command (with uv prefix above)                                                                                                          | Exit | Observed result                                                                                                                                                      |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------- | ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `apps/api`        | `uv run pytest tests/unit/test_assistant_contracts.py -q -k 'settings_have_bounds or four_step'`                                        | 1    | 2 failed, 9 passed, 27 deselected. Updated bounds test rejects legal 5 under old `le=3`; four-step cap-4 case rejects 4 under old `le=3`. Cap-3 case already passes. |
| repository root   | `uv run --project apps/api pytest apps/api/tests/unit/test_assistant_evaluation_scoring.py -q --tb=short`                               | 1    | 11 failed, 5 passed. Missing max-steps hooks, SSE replay, CLI options and comparison summary.                                                                        |
| repository root   | `uv run --project apps/api pytest apps/api/tests/unit/test_assistant_write_evaluation.py -q -k write_cap_comparison_summary --tb=short` | 1    | 1 failed, 16 deselected, missing `completed_count`.                                                                                                                  |

An initial contracts command was mistakenly run from the root without `--project`;
it exited 2 because pytest was not found. It was immediately rerun from `apps/api`
as recorded above. No application code ran in that failed invocation.

During implementation, the three targeted files initially produced 5 failures /
66 passes. Four failures exposed the stale evaluator's string-frame assumption;
`stream_events` now yields frame objects, and the evaluator was adapted within
scope. The fifth was a new test expectation that omitted the shipped plain-text
clarification prefix; the exact expected reply was corrected to include the
question plus final model text. No production invariant or existing assertion
was changed. The next targeted run passed all 71 tests.

## Final checks

| Working directory | Command (with uv prefix for uv commands)                                                                                                                                                                         | Exit | Result                                                                 |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---- | ---------------------------------------------------------------------- |
| repository root   | `uv run --project apps/api pytest apps/api/tests/unit/test_assistant_evaluation_scoring.py apps/api/tests/unit/test_assistant_contracts.py apps/api/tests/unit/test_assistant_write_evaluation.py -q --tb=short` | 0    | 71 passed in 1.75s                                                     |
| `apps/api`        | `uv run pytest tests/unit -q --tb=short`                                                                                                                                                                         | 0    | 537 passed in 17.56s; one existing Starlette/httpx deprecation warning |
| `apps/api`        | `uv run ruff check .`                                                                                                                                                                                            | 0    | All checks passed                                                      |
| `apps/api`        | `uv run ruff format --check .`                                                                                                                                                                                   | 0    | 127 files already formatted                                            |

The initial ruff format check exited 1 for two newly edited test files. Ran
`uv run --project apps/api ruff format apps/api/tests/unit/test_assistant_contracts.py apps/api/tests/unit/test_assistant_evaluation_scoring.py doc/training/issues/assistant_evaluation.py doc/training/issues/70/evaluate.py doc/training/issues/70/evaluate_sse.py doc/training/issues/99/evaluate.py`
from root (exit 0, four reformatted / two unchanged). The first separate evaluator
ruff check exited 1 for two import-order errors. Ran
`uv run --project apps/api ruff check --fix doc/training/issues/70/evaluate.py doc/training/issues/99/evaluate.py`
(exit 0, two errors fixed). Final checks cover the corrected files.

`npx --no-install prettier --check doc/decisions.md` initially exited 1 because
this worktree had no node_modules and npm attempted an unavailable registry lookup.
After linking the existing installation, the offline command
`npx --offline --no-install prettier --check doc/decisions.md` passed (exit 0).

## Formatting and preservation checks

All commands below ran from the repository root and exited 0:

```bash
uv run --project apps/api ruff check doc/training/issues/assistant_evaluation.py doc/training/issues/70/evaluate.py doc/training/issues/70/evaluate_sse.py doc/training/issues/99/evaluate.py
uv run --project apps/api ruff format --check doc/training/issues/assistant_evaluation.py doc/training/issues/70/evaluate.py doc/training/issues/70/evaluate_sse.py doc/training/issues/99/evaluate.py
npx --offline --no-install prettier --write apps/api/README.md doc/architecture.md doc/project-memory.md doc/decisions.md doc/training/issues/70/README.md doc/training/issues/99/README.md doc/training/issues/100/README.md doc/training/issues/100/verification.md doc/training/issues/100/results/*.json
npm run lint:changed -- a222822
git diff --check
git diff a222822 -- doc/decisions.md
python3 /tmp/codex-100/verify_artifacts.py
```

The uv commands use the isolation prefix above. Ruff reports all checks passed
and four evaluator/helper files already formatted. Changed-file lint reports all
matched files use Prettier style and ESLint exits successfully. Prettier changes
only the new #100 files' formatting; existing Markdown including decisions remains
otherwise as edited, with no historical reformatting. JSON formatting preserves
all report values.

The decisions diff contains one appended section and zero deletions. The artifact
check compares the original decision bytes as an exact prefix and asserts one new
section, no diffs in protected frontend/workflow/migration/deployment/assistant-loop/
#71/#72/case-tree/history/e2e/generated-OpenAPI paths, nine reports with matching
caps/date/model and expected completion counts, zero max-step stops/timeouts, and
per-case model calls within the cap. It passed. The first inline version had a
bytes/string typo after the prefix assertion; the corrected saved script above
passed in full.

## Replay commands and outcomes

Working directory: repository root. Every line below ran with the isolation prefix
above, exited 0, and wrote the named report. The command runner redirected ordinary
synthetic per-step logs to `/tmp/codex-100/`; the JSON reports retain case outcomes.
All nine use `scripted-v1`; configured location is `us-central1` only as metadata.

```bash
uv run --project apps/api python doc/training/issues/70/evaluate.py --max-steps 3 --output doc/training/issues/100/results/replay-70-json-cap3-2026-11-13-scripted-v1.json
uv run --project apps/api python doc/training/issues/70/evaluate_sse.py --max-steps 3 --output doc/training/issues/100/results/replay-70-sse-cap3-2026-11-13-scripted-v1.json
uv run --project apps/api python doc/training/issues/99/evaluate.py --max-steps 3 --output doc/training/issues/100/results/replay-99-json-cap3-2026-11-13-scripted-v1.json
uv run --project apps/api python doc/training/issues/70/evaluate.py --max-steps 4 --output doc/training/issues/100/results/replay-70-json-cap4-2026-11-13-scripted-v1.json
uv run --project apps/api python doc/training/issues/70/evaluate_sse.py --max-steps 4 --output doc/training/issues/100/results/replay-70-sse-cap4-2026-11-13-scripted-v1.json
uv run --project apps/api python doc/training/issues/99/evaluate.py --max-steps 4 --output doc/training/issues/100/results/replay-99-json-cap4-2026-11-13-scripted-v1.json
uv run --project apps/api python doc/training/issues/70/evaluate.py --max-steps 5 --output doc/training/issues/100/results/replay-70-json-cap5-2026-11-13-scripted-v1.json
uv run --project apps/api python doc/training/issues/70/evaluate_sse.py --max-steps 5 --output doc/training/issues/100/results/replay-70-sse-cap5-2026-11-13-scripted-v1.json
uv run --project apps/api python doc/training/issues/99/evaluate.py --max-steps 5 --output doc/training/issues/100/results/replay-99-json-cap5-2026-11-13-scripted-v1.json
```

At each cap 3/4/5, #70 JSON completes 8/8 with 8 correct-tool / 8 correct-argument
cases; #70 SSE completes 8/8 with 8 correct-tool / 8 correct-argument cases;
#99 completes 35/35 with `case_pass` 35/35. Every report has zero `max_steps` and
zero `timeout`. The [comparison table](README.md#replay-comparison-2026-11-13)
links each report and gives its p50/p95 and summed synthetic input/output/total
tokens. The deterministic percentile method is linear interpolation at `(n-1)*p`
on sorted latency milliseconds, rounded to three decimals, stated in every JSON.

## Acceptance coverage

| Criterion                                                                          | Evidence                                                                                                                                                                   |
| ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Range 1-5, default 3, reject 0/6, environment override                             | `apps/api/tests/unit/test_assistant_contracts.py:252`, `test_assistant_settings_have_bounds_and_env`; `apps/api/app/config.py:140` changes only `le=3` to `le=5`           |
| Actual four-model-call path                                                        | `apps/api/tests/unit/test_assistant_contracts.py:657`, `test_four_step_retry_clarification_requires_cap_four`, caps 3 and 4                                                |
| Original cap-3 last-step invariant preserved                                       | Unchanged `test_assistant_loop_caps_steps_disables_last_tools_and_logs_privately` in the same file, full unit suite passes                                                 |
| #70 JSON/SSE hooks, real loop receives caps, network forbidden, new summary fields | `apps/api/tests/unit/test_assistant_evaluation_scoring.py:151`, `test_issue70_cap_replay_summary_without_network`, six parametrizations                                    |
| #70 CLI flag and default replay                                                    | Same file `:209`, `test_issue70_cli_max_steps_defaults_to_replay`, both transports                                                                                         |
| Vertex gates before provider construction                                          | Same file `:223`, `test_issue70_vertex_refuses_before_provider_construction`, both transports; existing #99 refusal test remains passing                                   |
| Percentiles, null tokens, failures, empty reports                                  | Same file `:254`, `test_comparison_summary_linear_percentiles_null_usage_and_stop_counts`                                                                                  |
| #99 cap-5/zero override contract                                                   | Unchanged `test_max_steps_override_after_settings_construction`, `apps/api/tests/unit/test_assistant_write_evaluation.py:244`; shared helper now validates Settings copies |
| #99 metrics and all existing 35 ids                                                | Same file `:359`, `test_write_cap_comparison_summary`, plus unchanged committed-replay case-contract test and nine CLI reports                                             |
| Docs/default decision                                                              | Settings table in `apps/api/README.md`, present-tense cap in `doc/architecture.md` / `doc/project-memory.md`, #70/#99 READMEs and [#100 README](README.md)                 |
| Append-only decision                                                               | New end section in `doc/decisions.md`, dated 2026-11-13; original file is a byte-for-byte prefix of the final file                                                         |
| #71 pin unchanged                                                                  | No diff in `apps/api/tests/unit/test_assistant_routing_evaluation.py` or `doc/training/issues/71/evaluate.py`; 3 steps / 60 seconds retained                               |

The four-call script uses the real loop and validation:

1. `get_review_stats(target_language="invalid")` fails validation; execute is not called.
2. A valid English stats read executes against a synthetic result.
3. `ask_clarification` passes real validation and the real in-memory clarification helper, returning terminal `status=ok`.
4. Tools are disabled and the provider returns final text.

At cap 3, the third call has tools disabled, no successful question/part exists,
and `stop_reason=max_steps`. At cap 4, the terminal helper succeeds, a question part
exists, the exact plain-text question + final answer is returned, and
`stop_reason=completed`. Both paths assert elapsed monotonic time below 25 seconds,
provider-call count equal to the cap, and the exact tools-disabled sequence.

## Limits and deviations

No optional four-step #99 cases were added; the required unit test is sufficient
and keeps all 35 default-cap committed replay expectations intact. `e2e-todo.md`
is unchanged because there is no UI change or new browser gap. No generated API
artifacts or frontend files changed. No API generation was needed or run.

No PostgreSQL/integration tests, Docker operations, Playwright/Chromium, standalone
#71/#72 evaluations, deployment or real Vertex run occurred. Those checks are
outside this session's authorization. The 25-second deadline, 30-second Cloud Run
timeout, tool-call/tool-result bounds, #71 protocol and default 3 are unchanged.
Workflows, migrations, secrets, historical decisions and 2026-11-07 result files
were not edited. Replay reports were later committed under `doc/training/issues/100/results/`.

Suggested commit split, messages only:

- `feat(api): allow assistant step caps through five while retaining default three`
- `feat(eval): add cap-aware summaries and offline SSE replay`
- `docs: record issue 100 replay comparisons and retained default`

## Independent operator re-verification

Re-run on the same worktree after the implementation session, 2026-11-13
15:10-15:21 Asia/Taipei, without Vertex and without reading `.env`. Python
used the worktree's own `apps/api/.venv`, `PYTHONPATH=/tmp/codex-100/no-env`
(dotenv loads disabled; `CODEX_PG_PORT=5433` retargets `DEFAULT_DATABASE_URL`
for integration only), and `UV_NO_SYNC=1`. No `ENABLE_ISSUE70_VERTEX_EVAL` or
`ENABLE_ISSUE99_VERTEX_EVAL`. No `--vertex`.

| Check                                                                                                                                        | Result                                                                                                                                                                                                                                                                                                            |
| -------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `uv run ruff check .` and `uv run ruff format --check .` from `apps/api`                                                                     | exit 0; 127 files already formatted                                                                                                                                                                                                                                                                               |
| `uv run pytest tests/unit -q`                                                                                                                | **exit 0, 537 passed**, 1 existing Starlette deprecation warning, 25.95s                                                                                                                                                                                                                                          |
| Nine replay CLIs at caps 3/4/5 into `/tmp/codex-100/replay-verify/`                                                                          | **exit 0** each. Completion, token sums, secondary scores and report method match the committed files (latency and `executed_on` differ, as expected). #70 JSON 8/8, #70 SSE 8/8, #99 35/35 `case_pass`, zero `max_steps` / `timeout` at every cap. SSE synthetic totals 330 tokens at cap 3 and 360 at caps 4/5. |
| `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest tests/integration -q` against disposable **pg100 on `127.0.0.1:5433`**                       | **exit 0, 418 passed**, 51 existing warnings (Starlette + vector type), 265s                                                                                                                                                                                                                                      |
| `npm run check` in this worktree, with `PUBLIC_*` from committed `.env.example` only                                                         | **exit 0, 0 errors / 0 warnings**                                                                                                                                                                                                                                                                                 |
| `npm run test:frontend` Node portion in this worktree                                                                                        | **55 passed**, 0 failed                                                                                                                                                                                                                                                                                           |
| `npx vitest run` on main `a222822` (frontend is unchanged on this branch; worktree `node_modules` was a symlink that Vite could not resolve) | **exit 0, 253 passed**, 20 files. A preload returned empty content for real `.env` reads and never opened those files.                                                                                                                                                                                            |
| `npm run lint:changed -- a222822`                                                                                                            | exit 0                                                                                                                                                                                                                                                                                                            |
| `npm run api:check`                                                                                                                          | exit 0, generated artifacts unchanged                                                                                                                                                                                                                                                                             |
| `git diff --check`                                                                                                                           | exit 0                                                                                                                                                                                                                                                                                                            |
| `doc/decisions.md` prefix vs `a222822`                                                                                                       | exact byte prefix; only an append after the last #101 section                                                                                                                                                                                                                                                     |
| 2026-11-07 #70 result file hashes                                                                                                            | unchanged                                                                                                                                                                                                                                                                                                         |
| Playwright                                                                                                                                   | not run (no frontend change)                                                                                                                                                                                                                                                                                      |

Red-first on a detached throwaway worktree at `/tmp/codex-100/red-main` (`a222822`, production still `le=3`, no eval hooks), with only the new/changed test files copied in:

```text
uv run pytest -q --tb=short --no-header \
  tests/unit/test_assistant_contracts.py::test_assistant_settings_have_bounds_and_env[assistant_max_steps-3-1-5] \
  tests/unit/test_assistant_contracts.py::test_four_step_retry_clarification_requires_cap_four \
  tests/unit/test_assistant_evaluation_scoring.py::test_issue70_cap_replay_summary_without_network \
  tests/unit/test_assistant_evaluation_scoring.py::test_issue70_cli_max_steps_defaults_to_replay \
  tests/unit/test_assistant_evaluation_scoring.py::test_issue70_vertex_refuses_before_provider_construction \
  tests/unit/test_assistant_evaluation_scoring.py::test_comparison_summary_linear_percentiles_null_usage_and_stop_counts \
  tests/unit/test_assistant_write_evaluation.py::test_write_cap_comparison_summary
```

**exit 1, 14 failed, 1 passed** in 1.75s. The one pass is
`test_four_step_retry_clarification_requires_cap_four[3]`, which already describes
the existing cap-3 loop (tools disabled on the last call, `stop_reason=max_steps`).
The cap-4 case and the bounds test fail with `Input should be less than or equal to 3`.
#70 hook tests fail with missing `max_steps` / `run_replay` / `comparison_summary`
or a required `--model-query-date` on the old SSE CLI. `#99`
`test_write_cap_comparison_summary` fails with `KeyError: 'completed_count'`.
