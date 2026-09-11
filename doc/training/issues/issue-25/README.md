# Issue #25 — Frontend Database Cutover

Last updated: 2026-09-12

## Status

Part 1, the read-only bilingual management boundary, is implemented and verified locally. The full
ticket remains open: deck/card create, edit, archive, mutation recovery, final cutover, rollback
execution, remote CI, deployment, and post-deployment verification are not complete.

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

Implement Part 2: extend deck/card creation to accept an `Idempotency-Key`, prove exact replay and
conflicting-key behavior on the backend, then connect the shared write UI.
