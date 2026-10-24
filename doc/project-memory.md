# Project Memory

Last updated: 2026-10-24

This file is the current product-state index. Training milestones, evidence limits, and the next
training action belong in [`training/project-memory.md`](training/project-memory.md); detailed
verification records belong in the linked issue artifacts. Implementation and test results take
precedence over stale documentation. Deployment statements below summarize recorded evidence, not
a fresh inspection of the live services.

## Guest review implementation (2026-10-22)

Visitors explicitly choose Continue as guest on the signed-out homepage, then use the shared
`/review` route to practice a random batch of up to ten published English cards.
The guest choice stores a fixed 30-minute absolute deadline in tab-scoped `sessionStorage`.
Reload retains that deadline but starts a fresh batch; activity never extends it. Expiry or tab
closure ends the choice. Expiry clears the guest controller and returns to signed-out home.
Guest answers remain in memory and are not saved.
Flip-before-answer, grading buttons, swipes and keyboard controls share the private presentation.
As of 2026-10-23, guest review omits the extra heading, progress notice and home/sign-in link;
the shared header provides navigation and account actions.
Completion offers an explicit Practice again action. Guest activity never reads, writes or clears
private pending review commands or account-scoped practice activity markers, and never submits answers.
Authenticated users always receive private review at `/review`. The legacy `/review/guest`
redirects to that shared entry and does not select guest mode. Fresh signed-out review entry
without an explicit, unexpired choice returns home. Primary navigation is hidden during
initialization and while signed out; the account avatar remains available. Guest and authenticated
sessions show their existing navigation. Decks, card details, search and authoring retain auth.

The top-right account avatar opens a sign-in/sign-out menu. Signing in discards the guest batch
and initializes private review. Explicit sign-out clears the guest choice and returns home.
Private token expiry or API 401 retains the current private controller and exact pending command
for same-account sign-in and retry, without silently entering guest mode. Account changes discard
the old controller and reject stale responses. Browser guest state never grants backend access.

As of 2026-10-23, the implemented guest controller loads a static snapshot once and samples
Practice again locally. It never calls the backend. The manual-only Export guest cards Action
exports up to 50 distinct English cards from approved deck
`e3fa16a8-698b-445f-af1f-920c6758b377` through the machine-authenticated exporter and proposes
`static/guest/cards.json` in a PR. Approved public content is intentionally retained in Git.
The separate manual-only Pages workflow validates and builds that committed file without BE
access. Neither export nor merge publishes automatically. The initial snapshot is intentionally
empty until the first approved export PR merges and Pages is manually published. Failed export
leaves the committed and deployed snapshots unchanged. Edits/archive take effect after export,
PR review/merge and manual Pages publication. See the
[follow-up plan](product/2026-10-23-separate-guest-export-plan.md) and
[follow-up verification](product/2026-10-23-separate-guest-export-verification.md).

Pages can first publish the empty static seed with the existing backend unchanged. After verifying
zero guest API calls, deploy the final protected-export backend and configure the separate manual
export workflow. Supporting backend commit `34c7560` is an optional compatibility path when real
cards are required before the first static publication, not a dependency of ordinary Pages builds.
Production WIF/IAM, protected environment setup and publication remain unverified and were
not performed. See the [design](product/2026-10-23-static-guest-cards-design.md),
[verification](product/2026-10-23-static-guest-cards-verification.md), and
[development setup](development.md#guest-review-development-and-release-gate).

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
The English review flow and shared English/Japanese deck/card reads and writes now use it.
Authenticated multilingual keyword search and English-only semantic card search are implemented
through the same API and PostgreSQL ownership boundary. Keyword search does not call Vertex AI.
AI-assisted authoring and a grounded tutor are not active product capabilities; AI authoring must
create validated, editable drafts rather than directly confirming cards.

The first production provider boundary is Cloud Run in Singapore plus Neon PostgreSQL in AWS
Singapore. Neon remains the only writable source of truth; deployment does not add a database
switch, dual write, or Cloud SQL replica. The checked-in release contract uses separate
version-pinned runtime and migration database secrets, requires secure production PostgreSQL
transport, migrates before a zero-traffic candidate, and keeps traffic promotion and compatible
application rollback explicit. Cloud Run, Neon, and the GitHub Pages frontend are deployed according
to operator reports. Authenticated owned reads, a controlled review write and exact replay, candidate
smoke, promotion, and compatible rollback were also operator-reported; see
[`Issue #26`](training/issues/issue-26/README.md). A recorded read-only Cloud Run/Logging inspection
independently established production traffic allocation and application-event ingestion at that
checkpoint; see [`Issue #27 candidate verification`](training/issues/issue-27/candidate-verification.md).
These records do not establish current live health or verify every authenticated smoke outcome.

Future schema upgrades use a protected manual GitHub workflow that authenticates to GCP with OIDC
and invokes the Secret Manager-backed Cloud Run migration job. GitHub never receives the Neon URL;
data restore and traffic promotion remain separate. The initial `pg_dump`/`pg_restore` transfer was
operator-reported; restored-data reconciliation remains deferred. Runtime database-role and GCP
secret-access restrictions also retain operator-reported evidence limits in Issue #26.

English semantic search was promoted and exercised through the stable API URL and deployed search
page according to operator reports in [`Issue #40`](training/issues/issue-40/README.md).
[`Issue #41`](training/issues/issue-41/README.md) records the broader operator-reported deployed
evaluation and an **iterate** decision: retain limited search, but gate tutor use on a measured
relevance/no-answer boundary. The newer default multilingual keyword-search mode is implemented
locally; its deployment remains unverified. Neither semantic-search evidence nor readiness checks
establish deployment of that later keyword-search change.

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
automatic Apps Script fallback or dual write. Local tests verify the cutover boundary; the recorded
deployment outcomes and their evidence limits are summarized above.

Deck/card management uses the same authenticated FastAPI boundary for English and Japanese.
`/decks` canonicalizes a missing language to English, `/decks?language=ja` selects
Japanese, and detail pages display language-relevant fields without a separate application. The
checked-in OpenAPI schema generates the shared TypeScript contracts while runtime guards still
validate network JSON. Browser evidence covers normal review and management navigation without an
Apps Script call. CI and deployment no longer provide an Apps Script URL. The unused legacy wrapper
and sanitized snapshot remain as evidence, but the wrapper requires deliberate endpoint injection.

## Current User Experience

- `/` shows today's date, a welcome message, and either a Google sign-in button or a `Start` button.
- `/review` loads up to 10 authenticated English due cards from FastAPI, shuffles them, and renders
  `SwipeCards`.
- `/decks?language=en|ja` lists the authenticated user's active or archived decks through one shared
  route and component boundary; missing language defaults to English.
- `/decks/[deckId]` lists owned cards in one deck, and `/cards/[cardId]` shows the owned card detail.
- `/search` defaults to normalized keyword matching over active owned English and Japanese cards.
  Users can switch to English-only semantic search, which reports complete, partial, or empty
  embedding coverage without treating provider failure as an empty result.
- Japanese management views conditionally show reading and romanization; English shows pronunciation.
- Users create/edit decks in drawers, create and edit cards in a wide responsive dialog, and archive
  through an explicit confirmation. The shared overlay wrappers use Bits UI Dialog and repository-owned
  shadcn-svelte Sheet and Alert Dialog components for modal focus, keyboard,
  portal, and ARIA behavior. New cards default `learned_on` to browser-local today.
- Unclear creates retain an account-scoped exact request/key; stale edits keep entered values until
  the user explicitly reloads and discards them; unclear archives refetch before claiming success.
- Cards show an English-to-Chinese direction by default.
- A card starts on the front face. The user clicks to flip it, then can drag/swipe or use action buttons on the back face.
- Answer completion shows a `Submit Results` button. Only a validated FastAPI result confirms that
  batch was saved; retryable/authentication failures remain explicitly unconfirmed. A saved batch
  records a best-effort browser-local `YYYY-MM-DD` activity hint scoped to the Google subject.
  The homepage says "You've practiced today" for that account and date, including after an account
  switch on the mounted page. This does not establish that all due cards were reviewed. The legacy
  shared month/day marker is ignored, and unavailable marker storage cannot undo confirmed success.

## Important Behavior To Preserve

- Use `$app/paths.resolve()` for route navigation so GitHub Pages base paths keep working.
- Google sign-in is client-side and stores the Google ID token plus expiration in `localStorage`.
- API requests require a valid ID token from `getTokenIfValid()` and send it only in the bearer
  header.
- Production API access also requires the verified Google email to be on the backend-configured
  allowlist; the frontend list remains a user-experience precheck only.
- Browser API access is restricted to exact backend-configured origins; bearer and idempotency
  headers are allowed while credentialed cookies remain disabled.
- `SwipeCards` emits decisions and observed state versions; review stages, ease, and dates are now
  backend-owned.
- One logical submission retains the same key and body across ambiguous retries for up to 24 hours.

## Repo Memory Maintenance

Update this file when product behavior or its recorded deployment status changes. Keep one concise
product-state summary here and link to issue artifacts for verification detail; preserve the
distinction between repository-verified, operator-reported, and unverified outcomes. Update
`training/project-memory.md` for training progress and the next action, referencing this file rather
than maintaining a second product-state summary. Update `architecture.md` when data flow, routes,
module ownership, or integration contracts change. Update `decisions.md` when a durable decision or
known issue is added/resolved.
