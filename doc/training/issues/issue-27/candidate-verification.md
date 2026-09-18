# Issue #27 zero-traffic candidate verification

Date: 2026-09-18 Asia/Taipei. Scope: deployed request correlation and log
privacy for one safe unauthenticated request. This is not traffic promotion,
alert delivery, or a complete authenticated release smoke test.

## Release identity and traffic gate

- Source: draft [PR #43](https://github.com/JosephT5566/english-learning/pull/43),
  commit `3704a2a0ac34cb08672d7a79297b6aeccd2b8ece`.
- Backend and frontend CI checks for that commit completed successfully in
  [CI run 35256638699](https://github.com/JosephT5566/english-learning/actions/runs/35256638699).
- Protected [image publish run 35298431630](https://github.com/JosephT5566/english-learning/actions/runs/35298431630)
  succeeded. Protected [candidate deploy run 35298548962](https://github.com/JosephT5566/english-learning/actions/runs/35298548962)
  succeeded on the same commit. This code-only change did not run a migration.
- Cloud Run reported candidate revision `english-learning-api-3704a2a0ac34`
  with the `candidate` tag and no traffic percentage. Revision
  `english-learning-api-00009-xvw` retained 100% of production traffic. The
  deploy workflow's liveness and readiness checks passed.

## Request-ID and privacy check

One unauthenticated `GET /v1/cards` with no query string went to the candidate
tag URL. It returned HTTP 401 and `X-Request-ID`
`1a355bd3-48ab-4aa1-a979-4126d4a2a44d`. A Cloud Logging lookup scoped to
the candidate revision, stdout stream, and that UUID found exactly one parsed
`jsonPayload` completion event at `2026-09-18T02:16:46.856681Z`:

```json
{
  "event": "http_request_completed",
  "request_id": "1a355bd3-48ab-4aa1-a979-4126d4a2a44d",
  "method": "GET",
  "route": "/v1/cards",
  "status_code": 401,
  "duration_ms": 22,
  "outcome": "authentication",
  "error_code": "authentication_required"
}
```

The deployed payload's keys matched exactly this allowlist. It contained no
raw URL, query, headers, token, SQL, card content, user identifier, or
exception detail. The response request ID matched the event request ID.

A separate metadata-only read found one matching Cloud Run platform request
entry among three sampled candidate entries. Its `httpRequest.requestUrl` field
was present; this particular request had no query string. No URL value was
printed or committed. The earlier baseline found query strings in some
platform logs, so application-event redaction does not resolve that retention
concern. The proposed narrow exclusion in the [issue plan](README.md) remains
unapplied.

A read-only routing preflight found only the project's `_Required` and
`_Default` sinks, with no user-defined log metrics or Monitoring alert
policies. This does not prove that no external consumer reads the logs. Keep
the proposed exclusion unapplied while the existing production revision lacks
the new application event; revisit it after an approved promotion and a
production request-ID lookup.

## Remaining boundary

The deployed check proves one auth-failure event is ingested and traceable.
It does not exercise a deployed `database` or `unexpected` failure, a review
or import outcome, an alert policy, notification delivery, or a private-data
write. The first [failure alert](failure-alert.md) still needs an operator
notification channel and a labeled alert-delivery test. The candidate has
not been promoted to production traffic.
