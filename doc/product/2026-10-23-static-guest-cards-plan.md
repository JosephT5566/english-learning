# Static guest cards implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement
> this plan task-by-task within the assigned worker. The parent coordinates the independent
> reviewer requested by the owner. Do not delegate additional agents.

**Goal:** Manually export up to 50 safe English cards and publish them with Pages so guest
review never reads or writes the backend.

**Architecture:** A dedicated machine-authenticated FastAPI endpoint produces a versioned
content-only snapshot using a read-only transaction. A reusable download script validates and
atomically writes JSON; a manual-only Pages workflow transfers the sanitized same-run artifact
into the frontend build. The guest controller downloads once and samples rounds locally.

**Tech stack:** FastAPI, Pydantic, Google ID-token verification, PostgreSQL, Node.js scripts,
Svelte 5, GitHub Actions WIF and GitHub Pages.

**Spec:** [Approved design](2026-10-23-static-guest-cards-design.md).

## Global constraints

- Fixed approved English deck: `e3fa16a8-698b-445f-af1f-920c6758b377`.
- Snapshot: `schema_version: 1`, timezone-aware `generated_at`, and `items` with at most 50
  distinct English `PublicReviewCard` values. Encoded size is at most 512 KiB.
- Guest: base-aware `static/guest/cards.json`, at most ten distinct cards per round, one download
  per mounted controller, no `/v1/` request or backend fallback. Cross-round overlap is allowed.
- Action: `workflow_dispatch` only; no schedule or push trigger for Pages/export. Trusted main
  and protected environments only. Unrelated CI triggers remain unchanged.
- Secrets: no user token or service-account key stored for automation; no database secret on
  GitHub runners; no token, card body, or untrusted validation input in failure logs/artifacts.
- Authentication precedes database checkout and never invokes `current_user` or upserts users.
- Preserve private review/auth recovery, multilingual management, static subpaths and SRS.
- Live cloud changes, publication runs and deployment are excluded. No real cards in Git.
- One worker owns source changes in the current checkout. Preserve the unrelated untracked
  `doc/product/2026-10-21-guest-review-plan.md`. Parent edits planning documents only until handoff.
- Review base: `80b57736ba3ba950d77f2cb9da02d077278ab853`; include all assigned uncommitted files.

## Review focus

- Wrong service account, audience, issuer or missing claims cannot open a DB transaction.
- Oversized, redirected or malformed exports cannot overwrite an existing valid JSON file.
- A successful empty snapshot withdraws an archived deck; a failed fetch retains deployed data.
- Practice again and aborted/auth-switched guest sessions cannot leak private data or refetch BE.
- Backend-first rollout cannot remove the route used by an older frontend before Pages succeeds.

## Task 1: Protected exporter and supporting release

**Files:** Add focused export auth/route modules and unit/integration tests under `apps/api/`.
Modify `config.py`, `main.py`, the public content/query owner, deployment configuration/examples,
and generated OpenAPI/TypeScript/schema artifacts as needed. Keep modules small and reuse the
existing public DTO and explicit SELECT projection rather than full private card models.

**Interface:** `GET /v1/internal/guest-cards/export` returns the snapshot envelope above.
Use server settings for the deck, dedicated audience, service-account subject and verified email;
all absent disables export, partial configuration fails startup. Reject query filters. Use separate
token verification from browser auth; missing or wrong credentials fail before database access.

- [x] Write and run focused failing tests for settings and machine identity claims, including
      a browser token, wrong subject/email/audience, expired token and no database checkout on refusal.
- [x] Implement the smallest separate auth dependency using supported Google verification.
- [x] Write and run PostgreSQL behavior tests for the fixed active English scope, at most 50
      unique cards, excluded fields, archived deck returning empty, nonexistent/wrong-language deck
      failure, read-only enforcement, timeout/permit cleanup, and unchanged learning tables.
- [x] Implement the bounded exporter in one read-only transaction with a statement timeout
      and nonblocking concurrency permit; do not select notes/tags/review state.
- [x] Wire opt-in server settings through existing release paths and examples. Existing browser
      auth settings and API behavior remain compatible in the supporting release.
- [x] Regenerate API artifacts and run backend unit/integration, Ruff and contract checks.
- [x] Record a separately deployable supporting release before retiring the anonymous route.
      The worker may make one scoped local support commit if required to establish this release ref;
      never include unrelated files or real content. Otherwise report the exact unresolved release
      packaging limitation; do not claim the rollout requirement is satisfied without evidence.

## Task 2: Download script and manual publication

**Files:** `scripts/export-guest-cards.mjs`, related `tests/frontend/*.test.mjs`,
`.github/workflows/deploy.yml`, `package.json` if a command alias helps, and setup documentation.

**Interfaces:** Script reads API origin and short-lived bearer token from the environment,
validates Task 1's snapshot, and atomically writes the explicit output path. A separate protected
export job uploads only validated JSON. The build job downloads that same-run artifact into
`static/guest/cards.json` before `npm run build`.

- [x] Test malformed and extra/private fields, duplicate IDs, non-English cards, wrong version,
      invalid timestamp, 51 items, excessive bytes, redirect, timeout, and retained output on failure.
- [x] Implement HTTPS-only transport with redirect rejection, bounded response streaming and
      timeout, strict validation, safe errors and atomic file replacement. Log only counts and bytes.
- [x] Replace the Pages push trigger with manual dispatch only. Reject non-main refs before
      privileged export. Mint a short-lived token via WIF for the dedicated export service account;
      transfer only the sanitized artifact to the unprivileged build job.
- [x] Keep publication serialized and gated on export/build success. Preserve protected
      environment approvals; do not add automated commits, new credentials or a fallback dataset.
- [x] Verify script behavior and workflow triggers/permissions/artifact handling with focused tests.

## Task 3: Static guest controller and legacy removal

**Files:** `src/lib/api/public-review.ts` or its focused replacement, snapshot runtime contract,
`src/lib/components/GuestReview.svelte`, frontend and guest browser fixtures/specs. Remove obsolete
anonymous route/admission configuration and tests only after the supporting release is recorded.

**Interfaces:** Download and validate a snapshot from a base-aware same-origin asset URL with
credentials omitted. Keep its pool in the mounted controller; round sampling returns at most ten
distinct content cards. Preserve cancellation, empty/error/retry, login and deadline semantics.

- [x] Write and run failing tests for a 50-card snapshot, static subpath URL, local sampling,
      smaller/empty pools, abort/login/expiry and repeated rounds without a second download.
- [x] Implement the static transport and in-memory pool. Remove backend-specific cooldowns,
      the BE URL dependency and anonymous fallback. Use synthetic fixture files for CI/local testing.
- [x] Update browser request assertions to prove zero guest `/v1/` calls during entry, grading
      and Practice again; retain private review/auth recovery regression coverage.
- [x] Retire the legacy anonymous router and unused source admission plumbing in the final
      target. Regenerate contracts again and document that this release follows successful Pages
      publication using the supporting backend, including rollback ordering.
- [x] Run frontend checks/tests, guest/private browser tests, root build, subpath build/browser
      checks and generated API checks. Run required backend checks after retirement.

## Task 4: Documentation, independent review and closure

- [x] Update `doc/architecture.md`, `doc/development.md`, `doc/decisions.md`,
      `doc/project-memory.md` and API documentation with implemented behavior and exact setup variables.
      Describe dedicated WIF trust/IAM, publication failure/staleness, manual-only operation, and the
      three-stage release/rollback sequence. Label live setup and publication as unverified.
- [x] Run `npm run lint:changed -- 80b57736ba3ba950d77f2cb9da02d077278ab853`,
      `git diff --check`, generated API checks and all required relevant suites. Container verification
      applies if runtime contents/lifecycle change. Record actual results and blockers.
- [x] Return the worker handoff with files, support release ref, exact verification commands,
      failures/skips, remaining setup and current checkout status. Pause source edits for review.
- [x] Parent dispatches the independent `reviewer` against the full base-to-working-tree change,
      including untracked assigned files and root/subpath desktop/mobile browser behavior.
- [x] Parent routes accepted defects to worker, obtains reviewer re-verification where needed,
      and reports completion without claiming deployment or unobserved persistence/browser evidence.

Independent reviewer returned PASS on 2026-10-23 against implementation `1884a0e`, with no
actionable defects or blocked local verification. No correction round was required. See the
[verification report](2026-10-23-static-guest-cards-verification.md) for evidence and live setup limits.
