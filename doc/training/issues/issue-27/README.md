# Issue #27 - Operational Ownership

Status: in progress (baseline inspection only). Last updated: 2026-09-17.

## First acceptance boundary

Trace one failed request from the ID shown to the user to a backend operation
and failure class without logging tokens, raw card content, database URLs,
rejected input, or unnecessary personal data. Define and verify one actionable
failure signal before adding broader dashboards or backup work.

## Repository baseline

- `apps/api/app/request_context.py` creates a new server UUID for each request
  and puts it in `X-Request-ID`. It does not log a request event.
- `apps/api/app/errors.py` repeats that UUID in the safe error envelope. Expected,
  validation, framework, and unexpected errors use stable public codes; the
  unexpected-error response omits exception text.
- `src/lib/api/client.ts` carries the error request ID into `ApiClientError`.
  Review and management error views display it.
- `apps/api/app/database.py` maps SQLAlchemy failures to retryable
  `database_unavailable` without exposing connection details to the client.
- `apps/api/app/serve.py` starts Uvicorn without an application-specific logging
  configuration. `LOG_LEVEL` is validated in settings but is not wired to
  structured request events in application code.
- No application metrics, saved alert queries, or Issue #27 restore proof were
  found in the checked-in API and deployment configuration.
- Issue #26's runbook documents an optional initial transfer reconciliation;
  it was not executed and is distinct from #27's independent backup/restore
  proof.

These findings are from repository inspection, not deployed telemetry or a
production log audit. The behavior and privacy of server/access logs still need
local and deployed verification.

## Verification path for this boundary

1. Decide the minimal structured event fields and a failure class vocabulary.
2. Exercise a successful request, validation failure, auth failure, database
   failure, and unexpected exception with synthetic secret-looking input.
3. Assert that each response ID matches a safe server event and that no token,
   query value, card text, database URL, or exception detail appears in logs.
4. Inspect actual Cloud Run log ingestion and save a request-ID lookup query.
5. Define one alert from an observed failure class with owner, initial
   threshold rationale, and runbook action. Mark unmeasured thresholds as
   assumptions.

## Recommended first design (to verify in implementation)

Emit one JSON completion event for each API request with an allowlisted shape:
`event`, `request_id`, HTTP method, matched route template (or `unmatched`),
status code, duration in milliseconds, and a bounded outcome class. For an
application error, include its stable error code. Suggested initial classes are
`success`, `authentication`, `validation`, `conflict`, `database`, and
`unexpected`; review and import outcomes can add explicit operation events as
later boundaries require. A database failure event may identify a fixed
operation/phase such as `review_submit` or `transaction_commit`, but must not
contain SQL text or bound values.

The server creates the correlation UUID; incoming IDs are not trusted as the
canonical ID. Do not log request/response bodies, raw URL or query string,
authorization or idempotency headers, Google subject/email, card/deck IDs,
private learning text, database URLs, raw exception messages, or stack traces
in these events. Use fixed field names and enumerated values so Cloud Logging
queries and later metrics have bounded cardinality. Keep framework/access logs
under review: a safe application event does not prove other log sources are
redacted.

The first actionable signal should be a saved Cloud Logging query for
`database` and `unexpected` request outcomes, paired with a runbook action and
an explicitly provisional alert threshold after observing baseline traffic.
Do not invent a production SLO or page on ordinary validation/conflict traffic.

## Later boundaries

- Request, database readiness/pool, authentication, review, and import signals.
- Actionable alert set and retention rules.
- Independent backup into protected storage, isolated restore, schema/count/
  representative-data reconciliation, and a recovery runbook.
- One labeled incident exercise with timeline, detection, mitigation, recovery,
  and corrective action. Do not claim a real production incident.
