# Issue #27 temporary email notification test

Date: 2026-09-18 Asia/Taipei. This tested delivery from a safe candidate
authentication event through a temporary log-based alert. It did **not** test
the proposed `database` or `unexpected` 5xx failure alert.

## Test and observations

1. The operator created an email notification channel and the enabled policy
   `TEST English Learning candidate email` (ID
   `15646462828222347209`). A read-only policy check showed one channel and a
   filter restricted to candidate revision `english-learning-api-3704a2a0ac34`,
   stdout `http_request_completed`, route `/v1/cards`, HTTP 401, and outcome
   `authentication`.
2. After policy creation, a new unauthenticated candidate `GET /v1/cards`
   returned 401 with request ID `6ea8fdae-6260-41a1-83b6-d14a60445012`.
   Cloud Logging contained the matching event at
   `2026-09-18T03:56:23.883890Z` with the expected route, status, and outcome.
3. The operator reported receiving the email and finding the corresponding
   alert in Monitoring. The email address and message content were not copied
   into the repository, and delivery was not independently inspected.
4. The operator deleted the temporary policy. A subsequent read-only policy
   list returned no policies. Channel state after deletion was not checked.

The test supports one observed `log -> incident -> email` path, with email
receipt reported by the operator. It does not prove that the production failure
filter matches a deployed 5xx event, that a future incident will notify within
a specific time, or that production traffic is on the candidate revision.
