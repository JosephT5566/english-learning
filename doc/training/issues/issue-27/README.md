# Issue #27 - Operational Ownership

Status: in progress (local request tracing implemented; deployed verification
and alert are pending). Last updated: 2026-09-17.

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

## First design and local implementation

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

`apps/api/app/request_context.py` now emits the bounded JSON completion event.
`apps/api/app/errors.py` sets the stable error code for that event, readiness
marks a failed database probe, and `apps/api/app/serve.py` disables Uvicorn
access logging. An unexpected endpoint exception is converted inside the
request middleware to the existing safe `internal_error` envelope so its raw
exception text is not printed by the server error path. The CORS middleware
answers preflights before this request middleware, so they are not included in
these events. Cloud Run's own request logs are separate and have not yet been
audited for fields or retention.

The proposed Logs Explorer lookup is:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="SERVICE_NAME"
jsonPayload.event="http_request_completed"
jsonPayload.request_id="REPORTED_REQUEST_UUID"
```

For a first failure signal, replace the last line with:

```text
jsonPayload.outcome=("database" OR "unexpected")
```

This is a query draft, not a configured alert. Its service name, parsed JSON
fields, ingestion delay, and actual baseline must be checked on a deployed
candidate before defining a threshold. The operator response is: inspect the
route, status, error code, and time window; check `/health/ready` and Cloud Run
revision status; follow the existing Issue #26 rollback/runbook if a deployed
revision is unhealthy. Do not retry ambiguous review writes with a new
idempotency key.

Google documents single-line JSON stdout as Cloud Run `jsonPayload` and the
Cloud Logging filter language at:

- https://cloud.google.com/run/docs/logging
- https://cloud.google.com/logging/docs/view/logging-query-language

### Local verification, 2026-09-17

- Focused request/error/serve/health tests: 21 passed (one existing upstream
  Starlette deprecation warning).
- Complete backend unit suite: 109 passed (same warning).
- PostgreSQL integration suite: 147 passed against the running local
  `postgres:17-alpine` service (same warning). The first attempt was blocked by
  the filesystem/network sandbox; the permitted local-database run passed.
- Ruff lint and format checks for touched Python files passed.
- Tests verified response/log request-ID equality, route-template rather than
  raw-path logging, bounded auth/database/validation/conflict/unexpected
  classes, failed-readiness classification, and exclusion of synthetic query,
  token, and exception secrets.
- No deployed candidate application-event lookup, configured alert, or
  incident/restore proof has run yet.

### Read-only Cloud Logging baseline, 2026-09-17

The existing deployed revision does not contain the new application event.
A metadata-only read of the latest 100 Cloud Run platform request logs for
`english-learning-api` in the previous seven days found `httpRequest.requestUrl`
in all 100; 21 included a query string. Sample status counts were 85 `200`,
5 `401`, 6 `404`, and 4 `503`. This bounded recent sample is not an error-rate
baseline. No URLs, query values, or private payloads were displayed or saved
in the repository. The project `_Default` bucket has 30-day retention and the
`_Required` bucket has 400-day retention; the `_Default` sink currently has
no user-defined exclusions. Cloud Run's platform request logs therefore
remain a distinct data-minimization concern despite disabling Uvicorn access
logs. The new application event has not been inspected in Cloud Logging.

After the candidate's safe application events are verified, evaluate a narrow
`_Default` sink exclusion for only this service's platform request log:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="english-learning-api"
log_id("run.googleapis.com/requests")
```

This is a proposed production logging change, not an applied exclusion. It
would remove future platform request-log entries from that sink, including
their raw URLs, while retaining container events and other services' logs.
Confirm the actual sink behavior, other destinations, and monitoring coverage
before applying it. Existing stored entries require a separate retention or
deletion decision. Cloud Run documents that request logs are generated
automatically and can be managed through Cloud Logging exclusions:
https://cloud.google.com/run/docs/logging. The routing rules are documented at
https://cloud.google.com/logging/docs/routing/overview.

## Later boundaries

- Request, database readiness/pool, authentication, review, and import signals.
- Actionable alert set and retention rules.
- Independent backup into protected storage, isolated restore, schema/count/
  representative-data reconciliation, and a recovery runbook.
- One labeled incident exercise with timeline, detection, mitigation, recovery,
  and corrective action. Do not claim a real production incident.
