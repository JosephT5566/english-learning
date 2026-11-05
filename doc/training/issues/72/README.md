# Issue 72 extraction evaluation

This is an AI-drafted, synthetic proposal awaiting maintainer review, not an approved
answer set. Every `reviewed_by` and `reviewed_on` is `null`. Before review, do not claim
these targets are standard answers or independent human annotations. The model used to
propose vocabulary can bias which terms seem important, which meanings seem natural,
and which attacks are represented. The eight short English inputs are original synthetic
text, not copyrighted excerpts or private user data. Japanese quality is outside this set.

## Proposed coverage and review

Eight cases keep review manageable while covering each requested category: one narrative,
one explicit word list, one ambiguous narrative, one with source/date, one without either,
one ordinary adjustment, and two injection cases split between material and adjustment
instruction. Each is 1/8 of the set; injection accounts for 2/8. Categories overlap, and these
proportions are a coverage proposal, not a representative production distribution.
Review owner is pending maintainer assignment. Review each input, expected term list and notes;
only then fill reviewer/date. Dataset size, categories and pending review are recorded in
[decisions](../../../decisions.md#2026-11-05-add-stateless-card-extraction-with-provisional-evaluation).

Definitions and example correctness have no automated metric here. A maintainer must sample
outputs, record the sample size and findings separately, and inspect contextual meanings,
translations, naturalness, source/date attribution and injection behavior. No such review or
real-model evaluation was performed for this implementation.

## Offline replay

From the repository root, without model environment variables:

```sh
uv run --project apps/api python doc/training/issues/72/evaluate.py --output /tmp/issue72-replay.json
```

`recordings.json` is handwritten synthetic output, not captured Vertex traffic. It intentionally
contains one invalid injection output. Placeholder meanings and fabricated token/latency values
exercise the reporting pipeline only; they are not model quality, cost or speed measurements.
The report says `mode=replay`, `provisional=true`, includes model versions, an execution timestamp
and a null model-documentation query date. Do not combine replay statistics with real results.

The command-line script and data live outside pytest collection. Tests at
`apps/api/tests/unit/test_extraction_evaluation.py` resolve this directory through `__file__`
and import it via `importlib.util`, so CI does not depend on its current working directory.
These tests execute the scoring/replay functions and a fake provider with transport forbidden;
CI never runs real-mode CLI or needs real-model environment variables. The endpoint's separate
scripted-provider integration tests exercise the HTTP and PostgreSQL boundaries.

## Metrics and limits

- Schema pass rate uses strict `CardDrafts` JSON validation and the 100,000-byte response cap.
  The over-limit rate counts cases exceeding card/list/string limits or the byte cap.
- Vocabulary recall and precision compare unique terms after Unicode NFKC, casefold, whitespace
  trim/collapse. Punctuation is retained, with no stemming or synonym matching. A missing/empty
  predicted list scores zero precision/recall. Reported aggregates are macro averages over cases.
- Attribution/date fabrication rates count nonempty `example_source`/`learned_on` absent verbatim
  from material or supplied drafts, divided by all output card objects. Zero output cards yield
  null rather than a perfect score. Instruction is excluded from provenance. This heuristic can
  miss wrong attributions that happen to occur in the material and can flag valid paraphrases.
- Injection cases include actual synthetic output, schema acceptance and vocabulary results.
  They prove only the server validation boundary, not that a live model resists injection.
- Adjustment preservation compares whole untouched cards after `CardFields` normalization of
  omitted/null/default fields. Missing or duplicate target terms fail preservation. The current
  ordinary adjustment marks `dawn` unchanged; editing other fields on the targeted card still
  requires manual review. An injection case is reported as injection, even if it supplies drafts.
- Each case includes latency, model version and optional usage counts; absent usage stays null.
  Replay uses fixture timing; real mode measures wall time around the provider call. Failures
  retain a safe provider code and count as schema failures, with no automatic retry.

## Manual Vertex mode, not executed

The REST request format, response format, schema subset, current model names and IAM are
**unverified against the real API**. No documentation query was performed because network model
calls and online documentation lookup were prohibited in this task. A maintainer must check the
current Vertex contract/model availability and runtime ADC permissions before executing this mode.
The code does not default to any model. It reuses installed `requests` and ADC, adding no packages.

Use synthetic data only. This CLI explicitly sends fixture material directly to Google and is an
operator evaluation tool, not a product endpoint; product consent is enforced in the HTTP route.
Set these in the process environment without writing credentials or `.env` files:

```sh
export ENABLE_ISSUE72_VERTEX_EVAL=1
export VERTEX_PROJECT_ID=your-project-id
export GENERATION_MODEL=maintainer-verified-model-name
uv run --project apps/api python doc/training/issues/72/evaluate.py \
  --vertex --model-query-date YYYY-MM-DD --output /tmp/issue72-vertex.json
```

Both `--vertex` and `ENABLE_ISSUE72_VERTEX_EVAL=1` are required, along with explicit model/project
and the date the maintainer checked live model documentation. ADC must be provisioned separately.
The tool uses `Settings(_env_file=None)` and never reads `.env`. The report includes configured
model, returned model versions when available, model query date and execution timestamp. Keep
real reports local until reviewed for safe publication. A provisional answer set remains provisional
even if the API calls succeed. Do not report any real-model metric until this mode actually runs.
