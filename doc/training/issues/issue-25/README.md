# Issue #25 — Frontend Database Cutover

Last updated: 2026-09-12

## Status

Parts 1 and 2 are implemented and verified locally: bilingual reads plus failure-safe deck/card
create, edit, and archive now use FastAPI. Part 3 has removed Apps Script from normal frontend build
configuration and added a production API configuration gate. The full ticket remains open for the
real API/CORS setup, remote CI, deployment, and post-deployment read/write verification.

## Agreed Product Shape

- `/decks?language=en|ja` is the shared deck list. Missing `language` canonicalizes to English;
  unsupported values show validation without calling the API.
- `/decks/[deckId]?language=...` is the owned deck detail and card list.
- `/cards/[cardId]?language=...` is the owned card detail.
- English and Japanese use one route family, API client, generated contract, and component/domain
  boundary. Japanese conditionally shows reading and romanization; English shows pronunciation.
- Active and archived resources remain explicit states. Deck/card management actions will be added
  to these three pages rather than creating a separate application.
- Short deck create/edit forms will use a drawer. Card create will use a wider drawer, and card edit
  will use the card detail page. New cards will default `learned_on` to browser-local today.
- A stale edit will retain the user's values and offer an explicit “Reload latest and discard my
  changes” action. It will not retry blindly.
- An unclear mutation response will remain pending/unknown until a follow-up read proves the result;
  a failed mutation will never appear successful.
- Deck/card creation will use an account-scoped pending idempotency key. Backend create contracts
  must accept and replay it before the write UI is connected.

## Part 1 Implementation

- Added authenticated deck/card list and detail client methods with runtime response validation.
- Added shared language tabs, active/archive filtering, pagination, loading/empty/error states, and
  base-path-safe navigation.
- Added non-disclosing not-found, authentication, retryable, server, and malformed-response copy.
- Exported FastAPI OpenAPI deterministically to `apps/api/openapi.json` and generated the committed
  `src/lib/api/generated.ts` with `openapi-typescript`.
- Reused generated schema types in the frontend while retaining runtime guards for untrusted JSON.
- Added CI regeneration and diff checks for the checked-in schema and generated types.
- Enabled the shared header and added Home, Review, and Decks navigation without redesigning the
  existing blue study-space visual language.

## Part 2 Implementation

- Required a UUID `Idempotency-Key` for deck/card creation. The backend hashes versioned normalized validated
  content into the existing per-owner replay columns, returns the same resource for an exact retry,
  and rejects different content under the same key with `409 idempotency_key_reused`.
- Card creation and its initial review state remain one transaction; exact replay creates neither a
  second card nor a second state. No migration was needed because the constrained replay columns and
  partial unique indexes already existed.
- Added account-scoped 24-hour pending creation storage. Unclear, retryable, and authentication
  outcomes retain the exact body/key and lock fields until retry; confirmed or definite outcomes
  clear it.
- Added deck create/edit drawers, a wide card-create drawer, inline card editing, and explicit archive
  confirmations on the existing three pages. New cards default `learned_on` to browser-local today.
- Generated repository-owned shadcn-svelte Sheet and Alert Dialog components, backed by Bits UI,
  then composed them behind the feature-facing Drawer and ConfirmDialog wrappers. This preserves the
  existing styling while standardizing focus trapping, Escape behavior, scroll locking, portals,
  and accessible modal semantics.
- Optimistic conflicts retain form values and expose “Reload latest and discard my changes.” Archive
  uncertainty performs a follow-up read before showing an archived outcome.
- Expanded exact-origin CORS from `GET`/`POST` to the required `PATCH`/`DELETE` methods without adding
  cookies, wildcard origins, or new headers.

## Verification Evidence

Local verification on 2026-09-12:

- Svelte/TypeScript check: passed with zero errors.
- Targeted ESLint and Ruff checks for touched files: passed.
- Frontend contract/state/component tests: 13 passed.
- Scoped FastAPI read-contract test: passed with the existing upstream Starlette/httpx deprecation
  warning.
- Static production build with `BASE_PATH=/english-learning`: passed.
- Playwright Chrome: 20 flows passed, including bilingual drill-down, language-field relevance,
  archive filtering, loading, empty, authentication, non-disclosing not-found, retryable response,
  invalid-language no-request, mobile layout, and the existing review flows.
- Network evidence: the combined normal review and management trace sent persistence requests only
  to the configured FastAPI `/v1` origin and contained no Apps Script URL.
- Manual Chrome inspection: Japanese deck list, deck detail, and card detail were usable at desktop
  and mobile widths and showed the expected language-specific fields.

Part 2 verification on 2026-09-12:

- Complete PostgreSQL-backed backend suite: 236 passed with one existing upstream deprecation
  warning; focused idempotency/authorization: 9 passed; focused CORS: 6 passed.
- Frontend contract/state/component tests: 16 passed.
- Playwright Chrome: 28 passed, including exact ambiguous-create retry, local-date default,
  validation, successful and stale edits, authorization failure, ambiguous archive recovery, and
  keyboard drawer dismissal.
- Svelte/TypeScript check: zero errors and warnings; scoped Ruff/ESLint/Prettier passed.
- Static production build with `BASE_PATH=/english-learning`: passed.
- Manual Chrome inspection confirmed the compact deck drawer remains visually consistent with the
  established learning-library design.

## Part 3 Configuration Cutover

- Removed `PUBLIC_APP_SCRIPT_URL` from frontend CI and GitHub Pages deployment. The ignored local
  environment entry was also removed so SvelteKit cannot serialize the endpoint into a local static
  production artifact.
- Added `PUBLIC_API_BASE_URL` to deployment and fail the build unless all public runtime values are
  present and the API value is an HTTPS URL without credentials, a query, or a fragment.
- Preserved `src/lib/api/sheet.ts` and the sanitized Sheet fixture as rollback evidence. The wrapper
  has no ambient endpoint now; a caller must deliberately inject one, and normal runtime modules do
  not import it.
- Added source/configuration regression tests and scanned the generated static artifact for Apps
  Script variables, hosts, and URL fragments.

Part 3 local verification on 2026-09-12:

- Frontend contract/state/component/configuration tests: 20 passed.
- Svelte/TypeScript check: zero errors and warnings.
- Static production build with `BASE_PATH=/english-learning` and a configured HTTPS API origin:
  passed. The generated browser artifact contained the FastAPI value and no Apps Script variable,
  host, or endpoint fragment.
- Critical Playwright Chrome flows: 28 passed; their combined normal review/management trace still
  contains FastAPI `/v1` traffic and no Apps Script request.
- Deployment validation accepts a complete HTTPS configuration and rejects missing, HTTP,
  credential-bearing, query-bearing, and fragment-bearing API values.

Part 3 live verification is not complete. No production API host or backend deployment manifest is
recorded in this repository, so the actual GitHub variable, production CORS allowlist, remote CI,
deployed management mutation, and post-deployment network trace cannot yet be verified.

This evidence is local and fixture-backed. It does not claim live authorization isolation, remote CI,
deployment, production traffic, or management-write correctness.

## Cutover Order And Rollback Boundary

1. Verify all management reads against FastAPI while keeping mutation controls unavailable.
2. Add backend idempotent deck/card create replay and its contract tests.
3. Connect create/edit/archive UI with optimistic versions and explicit uncertain-result recovery.
4. Run bilingual, validation, stale-edit, authorization, archive, build, and network suites.
5. Record live read/write checks, then remove Apps Script configuration from the normal runtime path.

Before the first PostgreSQL-only management write, rollback can redeploy the prior frontend without
losing newly authored management data. After that point, the Sheet snapshot becomes stale. A legacy
frontend redeploy would hide or overwrite PostgreSQL-only changes unless the app is first put into
downtime and data is deliberately reconciled. There is no automatic reverse sync or dual write.

The local development data boundary was already crossed on 2026-09-11 when a live-token ten-card
review wrote only to local PostgreSQL. The legacy Sheet must not be treated as a current restore
source for that local dataset. The production boundary is unverified and must be recorded at the
first confirmed deployed PostgreSQL-only mutation.

Rollback has two levels:

1. Redeploy `6059689` to remove management mutations while retaining FastAPI review and management
   reads. This contains frontend write risk without reintroducing Sheet persistence.
2. A legacy redeploy at `9e90e68` reintroduces Apps Script/Sheet review persistence. After the first
   production PostgreSQL-only mutation, this is unsafe without downtime and explicit reconciliation.

## Five-Minute Explanation

The UI is multilingual through data, not duplication: a language query selects English or Japanese,
while routes, client methods, ownership rules, and components stay shared. Language-specific fields
are conditional presentation on the same card model. FastAPI OpenAPI is the compile-time source for
generated TypeScript, and checked-in regeneration catches drift in CI; runtime guards remain because
TypeScript cannot prove that a server response is valid at runtime. Cutover is ordered reads before
writes so incorrect display and ownership behavior can be found without mutating data. Rollback is
safe only until PostgreSQL receives data Sheets never receive; afterward a legacy fallback would
reintroduce stale Sheet state, so recovery requires downtime and explicit reconciliation.

## Next Step

Deploy the production API and PostgreSQL first, configure its exact GitHub Pages CORS origin, then
set the repository's `PUBLIC_API_BASE_URL` and execute the remaining remote CI, deployment, live
read/write, and post-write rollback-boundary checks.
