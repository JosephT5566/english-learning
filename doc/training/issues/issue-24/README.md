# Issue #24 - Review API cutover

Status: implemented and verified locally, including one live authenticated review; remote CI and
production deployment remain.

## Acceptance boundary

The existing English flip/swipe review now uses authenticated FastAPI/PostgreSQL reads and writes:

1. `GET /v1/reviews/due?target_language=en&limit=10` returns the review-ready cards and state
   versions.
2. `SwipeCards` permits an answer only after the top card is flipped and emits only `card_id`, the
   four-valued decision, and `expected_version`.
3. The review page creates one persisted logical command on the first submit and sends it to
   `POST /v1/reviews` with one UUID `Idempotency-Key`.
4. Only a validated success response produces the completed-review UI. Scheduling is exclusively a
   backend responsibility.

No review route imports or calls the Google Apps Script client. There is no fallback switch and no
dual write.

## Auth and retry invariants

- The current Google ID token appears only as `Authorization: Bearer <token>`. It is never placed in
  a URL, request body, pending command, error, or documentation.
- Missing, locally expired, or server-rejected credentials clear both token storage and the Svelte
  signed-in store. An unconfirmed pending review remains available after the same user signs in
  again.
- A pending command stores version `1`, Google subject, exact body, UUID key, creation time, and a
  24-hour expiry. Google subject is only a client privacy boundary; backend token verification and
  owner-scoped SQL remain authoritative.
- A different Google subject, malformed storage, duplicate cards, or expiry deletes the command
  without displaying the prior account's card IDs or decisions.
- Network, invalid-response, retryable provider/database, and server failures retain the exact
  command and key. The client never retries automatically.
- Success removes the pending command. A definite validation/not-found response removes it and
  cannot look successful.
- Any `409` retires the command. `stale_review_state` explains that the atomic batch saved nothing;
  recovery refetches due cards and starts a new logical review instead of copying old decisions to
  a new key.

## Error-state matrix

| Condition | User-visible state | Pending command | Recovery |
| --- | --- | --- | --- |
| Due request pending | Loading | None | Wait |
| Due list empty | Empty | None | End normally |
| Local expiry or API `401` | Sign in required; not confirmed | Retain for same subject | Sign in, return, retry exact command |
| Network / retryable `503` / provider failure | Review not confirmed | Retain exact body and key | Manual retry |
| Invalid success/error response or unexpected `5xx` | Review not confirmed | Retain exact body and key | Manual retry; use request ID when present |
| `409` stale/inactive/key conflict | Review not saved | Retire | Refetch and begin a new review |
| `400` / `404` / `422` | Review rejected/unavailable | Retire | Refetch; do not expose ownership distinctions |
| Valid `200 ReviewResult` | Completed | Remove | Return home |

## Cutover and rollback

- Cutover is a frontend release boundary: deploy the version that reads and writes only FastAPI.
  PostgreSQL becomes the review runtime authority at that point.
- Do not silently fall back to Apps Script, enable a runtime flag, or dual-write Google Sheets.
- Rollback means redeploying the previous frontend version. This creates temporary downtime during
  the redeploy and deliberately returns the old frontend to Google Sheets.
- Reviews accepted into PostgreSQL after cutover are not synchronized back to Google Sheets. A
  rollback therefore creates explicit PostgreSQL/Sheet divergence; operators must preserve both
  datasets and reconcile deliberately before another authority transition.
- The API rejects wildcard CORS and requires an explicit production frontend origin. Supplying that
  final origin, production deployment, and post-deployment verification belong to the deployment
  milestone.

## Local verification

- `npm run test:frontend`: nine Node contract/state tests plus two Svelte component tests passed,
  including exact pending-command recovery, 24-hour expiry, cross-account deletion, malformed
  storage, imported part-of-speech detail presentation, actual flip gating, and the emitted backend
  command shape.
- `PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run check`: passed with three pre-existing unused
  layout CSS warnings and no errors.
- Static production builds passed both with `BASE_PATH=/english-learning` and with an empty local
  base path.
- Focused backend unit contracts: 31 passed with the existing upstream `TestClient` warning.
- Focused PostgreSQL read/review/auth integration contracts: 35 passed with the same warning. The
  final full PostgreSQL-backed backend suite passed all 220 tests in 83.28 seconds.
- Ruff lint/format, the uv lock check, production static build with
  `BASE_PATH=/english-learning`, and whitespace checks passed. Repository-wide `npm run lint`
  remains blocked by the pre-existing Prettier baseline (57 reported files after adding this
  ticket's test files); targeted ESLint for every touched frontend source/test passes.
- `npm run test:browser`: ten Playwright/Chrome tests passed against checked-in deterministic
  servers. They cover disabled answer controls before flip, due-card rendering, retryable `503` as
  not confirmed, exact-key/body retry to success, pending cleanup, stale conflict retirement, empty
  and loading states, due/submission `401` sign-out, validation/not-found rejection, unexpected
  server failure, invalid success-response behavior, and a mobile-viewport regression requiring the
  card stack and card to receive usable height.
- Five focused CORS contracts verify allowed due/submission preflights, rejected origins/methods/
  headers, and `X-Request-ID` exposure. Real Uvicorn preflights from both supported local origins
  returned `200` with the intended methods and headers. After the CORS addition, the complete
  PostgreSQL-backed backend suite passed all 231 tests in 87.71 seconds.
- A real Chrome page at `http://localhost:5173/review` used a live Google ID token to load and submit
  10 due cards through local FastAPI/PostgreSQL. The confirmed UI reported 10 saved answers. A
  content-free database check found exactly one batch, 10 events for 10 distinct cards, and all 10
  current states equal to their recorded `srs-v1` resulting states.

This is a local correctness and live authenticated review result, not remote CI, deployment, or
production evidence.

## Five-minute explanation

1. Google Identity Services gives the browser an ID token. The frontend performs only expiry/privacy
   checks; FastAPI verifies signature, issuer, audience, expiry, verified email, and owner identity.
   The token travels only in the bearer header.
2. A logical submission begins on the first submit click. Its exact items and one UUID key persist
   for 24 hours. Ambiguous or retryable outcomes reuse both; success or a definite non-retryable
   response retires them.
3. Each item carries the state version observed by the due read. A stale version rejects the entire
   transaction, so the client states that nothing was saved and refetches instead of overwriting.
4. The cutover has one runtime path. That prevents hidden partial dual-write behavior but makes
   rollback operational: redeploy the former frontend, accept downtime, and acknowledge that
   PostgreSQL reviews performed after cutover do not exist in the Sheet.
