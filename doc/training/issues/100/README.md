# Issue 100 assistant step-cap comparison

The server-only `assistant_max_steps` range is now 1-5. Its default stays 3.
JosephT5566 approved Q1-Q8 on 2026-11-13. This implementation follows those
choices without reopening them: ceiling 5; evidence-gated default; all three suites
at caps 3/4/5; separate live-run approval; a fresh current-main cap-3 Vertex baseline;
a fake four-call test; unchanged #71 protocol; no ui-design-gate.

**Vertex was not run.** This issue, `ai-ready`, and implementation start do not
authorize it. Each live run requires separate explicit maintainer approval and all
existing evaluator gates. The default remains 3 because there is no approved live
comparison, not because the decision rule was evaluated against replay.

## Decision rule (Q2)

> Adopt the smallest default whose `stop_reason=="completed"` count is ≥ the cap-3 baseline + 1 case, whose latency p95 on that set is ≤ 20s, and that introduces no new `timeout` in the streaming run. Publish #70 correct-tool / correct-argument counts and #99 `case_pass` counts as secondary columns; do not raise the default from those columns alone.

The future cap-3 baseline must be rerun on current `main`, across #70 JSON (8),
#70 SSE (8) and the full #99 corpus (35). The historical
[#70 JSON](../70/results/vertex-2026-11-07-gemini-3.5-flash-lite.json) and
[#70 SSE](../70/results/sse-vertex-2026-11-07-gemini-3.5-flash-lite.json) files are
2026-11-07 context, not this issue's baseline. They remain untouched.

The deadline stays 25 seconds and Cloud Run `--timeout` stays 30 seconds. Extra
calls can increase latency, tokens and timeout risk. No cost figures, rate limits,
caches or usage ledger are introduced. #71 stays pinned to 3 steps / 60 seconds;
#71/#72 standalone evaluations were not rerun.

## Replay comparison, 2026-11-13

All nine reports use `scripted-v1`, location `us-central1` as configuration metadata
only, and `model_query_date: null`. No network or model provider is used. Each
report records its UTC execution timestamp, configured cap, model and location.
All cases remain unreviewed and every report is provisional. #70 JSON and SSE
share eight prompts on two transports, so their counts are not independent samples.
All 35 existing #99 ids and every #70 expectation are unchanged.

These are hook/report-format baselines using handwritten scripts, not recordings.
Replay latency and synthetic tokens are not production performance, model quality,
safety or cost evidence. Completion is exactly `stop_reason == "completed"`;
secondary scores cannot raise the default. Current JSON scripts fit in three calls,
so equal completion counts across caps are expected.

Percentiles use linear interpolation on sorted case `latency_ms`, at index
`(n-1)*p`, for `p=0.5` and `p=0.95`, rounded to three decimals. The same
`latency_percentile_method` is stored in all reports. SSE latency is terminal elapsed
time and its top-level case stop reason/usage mirror `terminal.data`. Usage sums
non-null input/output/total counts independently; null case values remain visible.
Empty summaries use null percentiles and zero sums/counts.

Token columns below are input / output / total. Correct-tool and correct-argument
columns are #70 secondary counts; `case_pass` is #99's secondary count.

| Report                                                              | Cap | Completed | Max steps | Timeout | p50 ms | p95 ms | Tokens I/O/total | Correct tool | Correct arguments | case_pass |
| ------------------------------------------------------------------- | --- | --------- | --------- | ------- | ------ | ------ | ---------------- | ------------ | ----------------- | --------- |
| [#70-json](results/replay-70-json-cap3-2026-11-13-scripted-v1.json) | 3   | 8/8       | 0         | 0       | 1.187  | 1.432  | 160/80/240       | 8/8          | 8/8               | n/a       |
| [#70-json](results/replay-70-json-cap4-2026-11-13-scripted-v1.json) | 4   | 8/8       | 0         | 0       | 1.170  | 1.407  | 160/80/240       | 8/8          | 8/8               | n/a       |
| [#70-json](results/replay-70-json-cap5-2026-11-13-scripted-v1.json) | 5   | 8/8       | 0         | 0       | 1.270  | 1.682  | 160/80/240       | 8/8          | 8/8               | n/a       |
| [#70-sse](results/replay-70-sse-cap3-2026-11-13-scripted-v1.json)   | 3   | 8/8       | 0         | 0       | 1.825  | 5.598  | 220/110/330      | 8/8          | 8/8               | n/a       |
| [#70-sse](results/replay-70-sse-cap4-2026-11-13-scripted-v1.json)   | 4   | 8/8       | 0         | 0       | 1.630  | 3.832  | 240/120/360      | 8/8          | 8/8               | n/a       |
| [#70-sse](results/replay-70-sse-cap5-2026-11-13-scripted-v1.json)   | 5   | 8/8       | 0         | 0       | 1.707  | 4.151  | 240/120/360      | 8/8          | 8/8               | n/a       |
| [#99-json](results/replay-99-json-cap3-2026-11-13-scripted-v1.json) | 3   | 35/35     | 0         | 0       | 1.254  | 1.693  | 700/350/1050     | n/a          | n/a               | 35/35     |
| [#99-json](results/replay-99-json-cap4-2026-11-13-scripted-v1.json) | 4   | 35/35     | 0         | 0       | 1.271  | 1.813  | 700/350/1050     | n/a          | n/a               | 35/35     |
| [#99-json](results/replay-99-json-cap5-2026-11-13-scripted-v1.json) | 5   | 35/35     | 0         | 0       | 1.341  | 1.857  | 700/350/1050     | n/a          | n/a               | 35/35     |

SSE preparation makes a separate final stream call. When a planning call already
returns text, replay repeats that text in the stream, counting both calls and
both synthetic usages. At cap 3 the two-tools and injection cases hand off directly
on the final call; at caps 4/5 they also consume their text-only planning entry.
Thus SSE totals rise from 22 calls / 330 tokens to 24 calls / 360 tokens even though
all eight cases complete. No extra script case or changed expectation is involved.

## Future Vertex decision entry template

Status: **not run / pending separate approval**. Record the explicit approval before
each run. Require `--vertex`, the suite-specific opt-in, explicit `GENERATION_MODEL`
and `VERTEX_PROJECT_ID`, operator-managed ADC, and `--model-query-date`; Settings
must use `_env_file=None`. Refusals must precede provider construction. See the
[#70 gates](../70/README.md#manual-vertex-mode) and [#99 gates](../99/README.md).
The code-derived ceiling across the three caps is 612 calls, not a usage forecast.

| Suite/report             | Cap     | Model   | Location | Model query date | Execution date | Completed | Max steps | Timeout | p50 ms  | p95 ms  | Tokens I/O/total | Correct tool | Correct arguments | case_pass | Status           |
| ------------------------ | ------- | ------- | -------- | ---------------- | -------------- | --------- | --------- | ------- | ------- | ------- | ---------------- | ------------ | ----------------- | --------- | ---------------- |
| #70 JSON / #70 SSE / #99 | 3, 4, 5 | pending | pending  | pending          | pending        | not run   | not run   | not run | not run | not run | not run          | not run      | not run           | not run   | pending approval |

For each approved cap, link all three reports and exact commands, publish the same
columns, compare completed counts and p95 against the fresh cap-3 baseline, and
compare streaming timeout case ids for new timeouts. Record whether the smallest
qualifying cap exists. If none qualifies, retain default 3. No live result or
approval is inferred from this template.

## Local verification and scope

[Verification evidence](verification.md) records commands, exit codes, red-first
failures and test locations. The four-call unit path is invalid read -> valid read
-> successful terminal clarification -> final text. Cap 3 disables the clarification
call and stops at `max_steps`; cap 4 succeeds with a question and final text within
25 seconds. The production loop itself is unchanged.

Optional four-step #99 cases were not added. The required unit test covers the
longer path while preserving the committed default-cap replay contract and 35-case
counts. `doc/e2e-todo.md` is unchanged because there is no UI or new browser gap.
No frontend, OpenAPI/client generation, migration, workflow, production, auth,
scheduling, deployment-path or timeout change is included. Results and changes
are committed on the issue branch, with comparisons recorded in the committed
result files for maintainer review.
