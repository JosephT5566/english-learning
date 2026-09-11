# Project Memory

Last updated: 2026-09-12

## Product

This is Joseph's personal English learning/review app. The primary workflow is:

1. User lands on the home page.
2. User signs in with Google if not already authenticated.
3. User starts a daily review.
4. App fetches due words from the authenticated FastAPI/PostgreSQL API.
5. User reviews swipe cards, marking remembered cards to the right and forgotten cards to the left.
6. App submits one idempotent decision batch to FastAPI; the backend derives and commits scheduling
   transitions in PostgreSQL.

The app is optimized for a small, personal learning flow rather than a public multi-user product.

An independently runnable FastAPI service exists under `apps/api/`, with liveness, typed and
secret-safe startup configuration, a lazy SQLAlchemy engine lifecycle, and database-aware readiness.
The English review flow and shared English/Japanese deck/card reads now use it. Deck/card mutations
remain the next frontend cutover boundary.

Persistence foundations are implemented locally: application-scoped SQLAlchemy session factories,
explicit short-lived transaction ownership, an empty reversible Alembic baseline, PostgreSQL-only
integration patterns, stable safe API errors, and independent frontend/backend CI definitions. The
first production domain migration now adds database-constrained users, owned English/Japanese
learning decks, confirmed language-aware cards with optional embedded learning content, and reusable
owned tags with same-owner card associations. It also adds one database-constrained current review
state per card, owned idempotent review batches, and retained before/after review events. The
complete synthetic integration fixture exercises English and Japanese through that same relational
model. Authenticated deck/card/due-review reads now expose deterministic shared English/Japanese
contracts. The backend verifies Google ID tokens, maps Google subject to an internal user, enforces
owned SQL scope, and provides owner-derived, idempotent deck/card create plus optimistic edit and
archive APIs. Review writes
now commit idempotent batches, immutable events, and current-state transitions atomically with
deterministic concurrency control. Review and management reads are connected to the user experience;
management writes are now connected through failure-safe shared forms.

A local one-time CSV dry-run boundary validates the legacy 21-field Sheet snapshot and persists only
safe import audit hashes and diagnostic codes. It does not create cards or review data.

A separate local confirmed-import CLI now requires and reproduces one eligible dry run before
atomically creating cards, normalized tags, associations, fresh review states, and durable
source-to-card mappings in an existing owned deck. Exact and concurrent replay return the completed
result without new mutations. Post-commit reconciliation persists only safe counts, hashes,
booleans, row numbers, and diagnostic codes. After the three Issue #22 source diagnostics were
corrected, the final zero-rejection 596-row snapshot was applied locally and reconciliation passed:
596 cards, mappings, and fresh review states; 184 tags; 885 card/tag associations; zero archived
cards; and no review batches or events. The private CSV and operational reports remain untracked.
The English due-review and review-write flow now uses FastAPI/PostgreSQL exclusively. It has no
automatic Apps Script fallback or dual write. Production deployment remains a later milestone, so
this cutover is verified locally rather than claimed in production.

Deck/card management uses the same authenticated FastAPI boundary for English and Japanese.
`/decks` canonicalizes a missing language to English, `/decks?language=ja` selects
Japanese, and detail pages display language-relevant fields without a separate application. The
checked-in OpenAPI schema generates the shared TypeScript contracts while runtime guards still
validate network JSON. Browser evidence covers normal review and management navigation without an
Apps Script call. Legacy modules remain only while the later write-cutover and rollback work is
unfinished.

## Current User Experience

- `/` shows today's date, a welcome message, and either a Google sign-in button or a `Start` button.
- `/review` loads up to 10 authenticated English due cards from FastAPI, shuffles them, and renders
  `SwipeCards`.
- `/decks?language=en|ja` lists the authenticated user's active or archived decks through one shared
  route and component boundary; missing language defaults to English.
- `/decks/[deckId]` lists owned cards in one deck, and `/cards/[cardId]` shows the owned card detail.
- Japanese management views conditionally show reading and romanization; English shows pronunciation.
- Users create/edit decks in drawers, create cards in a wide drawer, edit cards inline, and archive
  through an explicit confirmation. The shared overlay wrappers compose repository-owned
  shadcn-svelte Sheet and Alert Dialog components, backed by Bits UI for modal focus, keyboard,
  portal, and ARIA behavior. New cards default `learned_on` to browser-local today.
- Unclear creates retain an account-scoped exact request/key; stale edits keep entered values until
  the user explicitly reloads and discards them; unclear archives refetch before claiming success.
- Cards show an English-to-Chinese direction by default.
- A card starts on the front face. The user clicks to flip it, then can drag/swipe or use action buttons on the back face.
- Answer completion shows a `Submit Results` button. Only a validated FastAPI result changes the UI
  to completed; retryable/authentication failures remain explicitly unconfirmed.

## Important Behavior To Preserve

- Use `$app/paths.resolve()` for route navigation so GitHub Pages base paths keep working.
- Google sign-in is client-side and stores the Google ID token plus expiration in `localStorage`.
- API requests require a valid ID token from `getTokenIfValid()` and send it only in the bearer
  header.
- Browser API access is restricted to exact backend-configured origins; bearer and idempotency
  headers are allowed while credentialed cookies remain disabled.
- `SwipeCards` emits decisions and observed state versions; review stages, ease, and dates are now
  backend-owned.
- One logical submission retains the same key and body across ambiguous retries for up to 24 hours.

## Repo Memory Maintenance

Update this file when the product workflow changes. Update `architecture.md` when data flow, routes, module ownership, or integration contracts change. Update `decisions.md` when a durable decision or known issue is added/resolved.
