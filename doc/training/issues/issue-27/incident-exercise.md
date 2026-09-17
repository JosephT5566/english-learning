# Issue #27 local incident exercise: database readiness failure

Date: 2026-09-18 Asia/Taipei (2026-09-17 UTC). This was a **local simulated
failure**, not a production incident or a Cloud Monitoring alert test.

## Scenario and method

The API process remains alive while its database readiness probe reports an
unavailable dependency. A one-off local `TestClient` drill replaced only
`check_database_readiness` with a controllable false/true result. It did not
stop PostgreSQL, change Neon, deploy a revision, or create durable data. The
exercise used the real FastAPI routes, request middleware, response headers,
and stdout event emitter. The operator collected only bounded event fields.

## Timeline and evidence

All times below are within the recorded `2026-09-17T18:03:51.317028Z` to
`18:03:51.329133Z` local test interval; the harness did not timestamp each
individual call.

| Step        | Observation and operator action                                                                                                                                                                                                |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Detection   | `GET /health/ready` returned 503 with `not_ready` and database `unavailable`. The response `X-Request-ID` was `bafabeff-380e-4409-9600-b754db55eeae`.                                                                          |
| Correlation | One stdout `http_request_completed` event had the same request ID, route `/health/ready`, status 503, outcome `database`, and code `database_unavailable`. This matches the proposed [failure-alert filter](failure-alert.md). |
| Triage      | `GET /health/live` returned 200, separating a live API process from failed database readiness. The event and response exposed no connection string, credentials, query string, or private card content.                        |
| Mitigation  | In the simulation, the operator switched the probe result from unavailable to available. This models restored dependency access; it does not prove a real database repair procedure.                                           |
| Recovery    | A second `GET /health/ready` returned 200 and emitted a `success` completion event. The application instance was not restarted.                                                                                                |

The drill assertions checked the 503/200/200 status sequence, event outcomes
`database`/`success`/`success`, request ID equality for the failure, stable
error code, safe route names, and absence of `query` or `url` event fields.
The command exited 0. One upstream Starlette/httpx deprecation warning was
unrelated to the exercise.

## Response assessment and corrective actions

- The safe readiness response and request ID support the first triage step.
  The local event would satisfy the proposed failure condition if an
  equivalent structured event reached the expected Cloud Run stdout stream.
- Detection was manual in this drill. The current deployed revision has not
  emitted the new application event, and no policy or channel is configured.
  After the deferred candidate release, verify parsing and request ID lookup,
  then configure and test the [first alert](failure-alert.md) with the owner.
- This drill did not validate real PostgreSQL failure handling, pool
  exhaustion, Cloud Run health behavior, notification latency, or a database
  restore. A later controlled candidate exercise should record those
  separately if the operator decides the risk and cost are justified.

No production outage, user impact, mean time to detect, or mean time to
recover is inferred from this local simulation.
