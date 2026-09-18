# Issue #27 first failure alert

Status: enabled on 2026-09-18 as policy
`projects/eng-learning-470909/alertPolicies/13851003450661507750`.
The exact filter, email channel, 30-minute interval, and runbook link were
read back from Cloud Monitoring. A separate temporary 401 alert delivered an
email by operator report; see [`notification-test.md`](notification-test.md).
No matching 5xx event or delivery from this failure policy has been observed.

## Why this signal

Alert on a safe application request-completion event when the backend reports
`database` or `unexpected` with HTTP 5xx. These classes require an operator to
check availability or a failed backend operation. Authentication, validation,
and conflict responses are excluded because they can be normal user or retry
behavior. At this project's low and unmeasured traffic, one matching event is
an initial **assumption** for a prompt investigation, not a production SLO or
measured error-rate threshold. A log-match alert avoids inventing a traffic
denominator. Google distinguishes per-entry [log-based alerts](https://cloud.google.com/logging/docs/alerting/log-based-alerts)
from count thresholds that require [log-based metrics](https://cloud.google.com/logging/docs/alerting/monitoring-logs).

## Enabled policy

| Field                              | Initial value and rationale                                                                                     |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Name                               | English Learning API database or unexpected failure                                                             |
| Owner                              | Project operator (Joseph)                                                                                       |
| Condition                          | One matching safe application completion event                                                                  |
| Notification                       | Operator email channel tested with a temporary 401 policy and attached to this enabled policy                   |
| Minimum time between notifications | 30 minutes, provisional assumption to avoid repeated notices during one outage; revisit after observing traffic |
| Runbook                            | This file, “Response to a match” below                                                                          |

## Enabled policy verification, 2026-09-18

Cloud Monitoring reported the policy enabled with exactly one `LogMatch`
condition equal to the filter below and one operator email channel. The
notification rate limit is `1800s`; incident autoclose uses `604800s` (the
seven-day default). The policy documentation links to this runbook and
includes immediate safe triage steps. A Cloud Logging query found zero
matching `database`/`unexpected` 5xx events in the previous hour. This
verifies configuration, not actual failure detection or delivery. The
candidate remains at zero production traffic; the current production revision
does not emit this application event.

Logs Explorer and log-match alert filter:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="english-learning-api"
log_id("run.googleapis.com/stdout")
jsonPayload.event="http_request_completed"
jsonPayload.status_code>=500
jsonPayload.outcome=("database" OR "unexpected")
```

This filter selects the bounded JSON line from `request_context.py`, not the
Cloud Run platform request log that can contain raw URLs. It does not extract
user IDs, card IDs, query strings, request bodies, SQL, or exception text as
labels. To trace a reported failure, substitute the user's UUID in this
separate lookup:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="english-learning-api"
log_id("run.googleapis.com/stdout")
jsonPayload.event="http_request_completed"
jsonPayload.request_id="REPORTED_REQUEST_UUID"
```

## Response to a match

1. Record alert time, revision, `request_id`, route template, status, outcome,
   and stable error code. Keep raw request URLs, tokens, private card content,
   and exception messages out of the incident notes.
2. Check `/health/live` and `/health/ready`, then Cloud Run revision health.
   If readiness fails, check Neon availability and the runtime connection
   secret's version and permissions without printing its value. Distinguish a
   database failure from a code exception using the bounded outcome and code.
3. For an `unexpected` event after a release, compare the failing revision to
   the last known healthy revision. Follow the
   [Issue #26 release runbook](../issue-26/runbook.md) for a compatible
   application traffic rollback if the new revision is implicated. Do not
   automatically downgrade the database.
4. For an ambiguous review write, reuse the original idempotency key and
   exact payload when retrying; never create a new key merely because the
   response failed. Verify recovery with readiness and a controlled owned
   read, then record timeline, mitigation, recovery, and corrective action.

## Release and test gate

1. Verify the exact branch commit and CI, then deploy the approved zero-traffic
   candidate under the existing release procedure. The operator deferred this
   step earlier; no production traffic change is part of this alert design.
2. Generate one safe candidate request, capture its response request ID, and
   verify exactly one parsed `jsonPayload` completion event in the stdout
   stream. Check that no private fields are present. A healthy or auth-failure
   candidate request validates ingestion but does **not** test the failure
   alert condition.
3. Observe real baseline traffic and choose an operator notification channel.
   The email channel was tested with a temporary 401 candidate policy, and
   this 5xx policy is now enabled. The operator completed candidate smoke
   manually and requested no further candidate tests. Verify this policy's
   own condition later with a clearly labeled synthetic matching event or a
   naturally occurring failure; record the test time, received notice, and
   resulting query. Avoid disrupting Neon or production traffic merely to
   trigger an alert.
4. Review alert volume after the first week of observed use. Adjust the match
   scope or notification interval from evidence, not an invented SLO. If no
   event appears, investigate ingestion or lack of traffic before treating
   silence as health.

Steps 1 and 2 passed on the zero-traffic candidate. Step 3 is complete only
for the separate 401 email-path test and policy creation; this policy's 5xx
condition and delivery still need verification. Step 4 awaits observed use.

Read-only checks before candidate deployment on 2026-09-18:
`gcloud monitoring policies list` returned no policies; `gcloud logging read`
accepted the filter and returned no matching application event in the
previous seven days. A separate stdout-stream query matched the existing
Cloud Run log stream. Candidate parsing and request-ID correlation were then
verified in [`candidate-verification.md`](candidate-verification.md). These
checks do not establish failure-condition detection, notification delivery,
or live alert behavior. No user-defined log metric or policy was created.
