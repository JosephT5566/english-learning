# Issue 72 extraction evaluation

This is an AI-drafted, synthetic answer set. The maintainer (`JosephT5566`) reviewed all eight
cases on 2026-11-05, recorded in `reviewed_by` and `reviewed_on`; the targets are therefore a
maintainer-reviewed set, not independent human annotations by multiple annotators. The model used to
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

## Manual Vertex mode

The maintainer's narrow response-schema bisect is recorded below. Other REST request/response
contracts, model availability and IAM are **unverified by this agent**; the bisect is not a general
compatibility guarantee. No documentation query or model call was performed by this agent because
this task prohibits them. A maintainer must check the
current Vertex contract/model availability and runtime ADC permissions before executing this mode.
The code does not default to any model. It reuses installed `requests` and ADC, adding no packages.

Use synthetic data only. This CLI explicitly sends fixture material directly to Google and is an
operator evaluation tool, not a product endpoint; product consent is enforced in the HTTP route.
Set these in the process environment without writing credentials or `.env` files:

```sh
export ENABLE_ISSUE72_VERTEX_EVAL=1
export VERTEX_PROJECT_ID=your-project-id
export GENERATION_MODEL=maintainer-verified-model-name
# Optional; select global only after confirming the chosen model's location.
export GENERATION_LOCATION=global
uv run --project apps/api python doc/training/issues/72/evaluate.py \
  --vertex --model-query-date YYYY-MM-DD --output /tmp/issue72-vertex.json
```

`GENERATION_LOCATION` is optional. If unset, generation uses `VERTEX_LOCATION` (default
`us-central1`); embedding always retains its regional `VERTEX_LOCATION`. The independent generation
setting accepts `global` or the existing regional format. Global generation uses host
`aiplatform.googleapis.com` with `/locations/global/`; regional generation retains its prefixed
host. This URL format comes from prior knowledge and is **unverified against the real API**.
Model/location availability, including the maintainer-reported model selection, is also unverified.

Both `--vertex` and `ENABLE_ISSUE72_VERTEX_EVAL=1` are required, along with explicit model/project
and the date the maintainer checked live model documentation. ADC must be provisioned separately.
The tool uses `Settings(_env_file=None)` and never reads `.env`. The report includes configured
model, effective `location`, returned model versions when available, model query date and execution
timestamp. Every real-mode case includes `provider_failure` and nullable `provider_http_status`.
The latter is only a bounded HTTP status integer, never provider response bodies, user text or
tokens; it is null on success or failures without a captured HTTPError status. HTTP 400/404 retain the
`invalid_response` classification, but the recorded status helps distinguish upstream rejection
from an invalid JSON/card body. Status alone cannot establish the root cause. Offline replay has
no actual provider location and does not claim one. Keep
real reports local until reviewed for safe publication. A provisional answer set remains provisional
even if the API calls succeed. Do not report any real-model metric until this mode actually runs.

## Review-derived response parsing, still unverified

PR #85's review cited Vertex Content REST metadata on text parts. That reference was not fetched
or verified for this work. The local parser now allows only text, thought and thoughtSignature
keys; text/signature must be strings and thought must be a boolean when present. It concatenates
only final text, excluding thought=true summaries and all signature metadata. All parts are
validated first; tool/media fields, unknown keys, malformed metadata and thought-only responses
are rejected. The unknown-key policy deliberately fails closed, so future provider metadata can
require a reviewed extension. This behavior is covered by handwritten synthetic contracts and a
fake-HTTP endpoint test, not actual model responses.

Malformed JSON and content/chunk decoding failures are non-retryable invalid responses (502),
while connection failures retain their availability classification. Real requests.Response.json()
and synthetic raw-body errors cover this distinction locally. No dataset review fields or real
model results were changed. See [review-fix evidence](../../../issues/issue-72-verification.md#pr-85-review-fixes).

## Maintainer array-limit bisect, 2026-11-05

The maintainer reported a live Vertex bisect for **gemini-3.8-flash at global**, on one occasion.
This agent did not repeat the calls or inspect online documentation. Reported observations:

| Schema change                                                                                                                                           | HTTP result                               |
| ------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------- |
| Original responseSchema, including minItems/maxItems                                                                                                    | 400, Request contains an invalid argument |
| Remove only minItems and maxItems together, retain the rest                                                                                             | 200                                       |
| Remove all constraints                                                                                                                                  | 200                                       |
| Remove only another group (minimum/maximum, minLength/maxLength, format, nullable, description, enum or required), with minItems/maxItems still present | 400                                       |

The last row does not show that those other keywords are rejected. The successful paired-removal
request retained the rest of that supplied schema, so that combination was accepted in this one
reported run. It does not establish keyword-by-keyword enforcement, every output scenario, other
models or future model versions. Neither minItems nor maxItems was tested alone; do not claim
which individually caused rejection. Model output quality has not been evaluated.

The provider projection now conservatively removes both array-count keywords at every schema
level, including referenced/nested arrays. It keeps minLength/maxLength, minimum/maximum, enum,
format, nullable, required and description when supplied. Local tests prove projection behavior;
the operator report supplies the narrow live payload-acceptance evidence. The full CardDrafts
server schema is unchanged: it still enforces 1-20 cards and all other field/list/cross-field rules.
The prompt already says Return 1-20 cards and was not changed. Model output is always strictly
validated, with 0/21-card output rejected as extraction_invalid_output; no retry or write occurs.
See [fix #3 verification](../../../issues/issue-72-verification.md#provider-array-count-keyword-bisect-fix-3).
