# Publish static guest review cards

Status: owner-approved on 2026-10-23. Implementation and independent review are authorized;
production setup and deployment remain separate. Publication details incorporate the
[owner-approved follow-up](2026-10-23-separate-guest-export-plan.md).

## Intent

Give guests the existing review experience without sending their card reads or answers to
FastAPI or PostgreSQL. A manually dispatched GitHub Action exports approved content and proposes
a PR. A separate manual Pages Action publishes the reviewed, committed snapshot.

The owner selected deck `e3fa16a8-698b-445f-af1f-920c6758b377`, English content, a pool of up to
50 cards, and manually dispatched GitHub Actions for repeatable updates. The owner explicitly
requires manual execution; this export and publication flow has no schedule or push trigger.
A new protected export API is authorized
if needed. This document proposes the machine authentication and publication details.

## Approaches

- Existing user-authenticated APIs can export cards with a fresh Google user ID token. The
  list endpoint lacks full study content, so export also needs card-detail reads. This works
  manually but requires a fresh browser token for subsequent runs instead of a dedicated
  short-lived machine identity.
- A scoped machine-authenticated export endpoint can reuse the existing public projection and
  bounded read-only query. GitHub obtains a short-lived Google service-account ID token through
  WIF. This is the proposed approach for the requested Action.
- A Cloud Run export job can query the database without an HTTP endpoint. It needs a job,
  artifact storage, and a transfer lifecycle. That adds infrastructure beyond this small export.

## Backend boundary

Add `GET /v1/internal/guest-cards/export`. Its machine identity dependency is separate from
`current_user`; it must not create users or change browser authentication behavior.

Verify the Google signature, issuer, expiry, dedicated export audience, expected service-account
subject, and verified service-account email. Missing or invalid credentials fail before database
checkout. A normal browser ID token cannot authorize export, and an export token cannot
authorize the existing private management or review APIs.

Use a dedicated export service account with no database, Secret Manager, deployment, or
project-wide roles. Configure WIF impersonation narrowly for the repository's trusted main-branch
publication workflow and protected environment. Reuse the existing WIF provider where its
claim mappings and conditions support this scope; do not broaden existing deployment identities.
Any new IAM binding remains an explicit operational setup step.

The export audience, service-account identity, and approved deck ID are server settings. They
default to disabled; partial configuration fails validation. The endpoint accepts no caller-selected
deck, arbitrary filters, or caller-selected limit. The selected deck must be English.
Validate its existence and language; a missing or wrong-language deck fails export instead of
silently publishing an empty pool. An archived deck or an active deck with zero active cards
returns an intentional empty pool, withdrawing published cards on the next successful deployment.

Reuse `PublicReviewCard` and the explicit public SELECT projection and bounded read-only
transaction. Retire the unused anonymous `/v1/public/review-cards` route and its obsolete
source-based admission and cooldown plumbing when the guest frontend switches to static content.
Leaving its allowlist empty still opens a database transaction on an admitted anonymous request
today, so an empty setting alone does not achieve the desired boundary. There is no anonymous
API fallback. The export reads up to 50 distinct active cards from the
approved deck in one transaction with a statement timeout. It randomly samples eligible cards
and returns a versioned snapshot with generation time and items. Reject concurrent exports with
a nonblocking permit; do not depend on browser IP attribution for machine authorization.

Only the existing public card fields are eligible: card ID, language, term, meaning,
pronunciation, reading, romanization, part of speech and detail, target-language definition,
example sentence and translation, synonyms, and antonyms. Exclude owner and deck metadata, notes,
tags, example source, dates, versions, review state, and embeddings. Do not fetch private content
and then dump the complete model. Export never writes learning data or calls AI providers.

## Export script and publication

Add one reusable export script. Accept the HTTPS API base URL and a short-lived token through
the process environment, never command-line token arguments. Disable redirects so credentials
cannot be forwarded elsewhere. Bound request duration and response size; validate the exact
snapshot fields, English language, unique IDs, and maximum of 50 cards before writing anything.

Write the file atomically. Print only safe counts and byte size. Do not print credentials,
HTTP response bodies, private content, or full validation inputs. Use a proposed 512 KiB encoded
JSON size cap; exceeding it fails the export without truncating cards. This is a publication
guard, not a measured performance target. Retain a successful empty result distinctly from a
failed request.

Use a separate manual `export-guest-cards.yml` workflow. Its protected export job uses
`google-github-actions/auth` and narrowly scoped WIF to mint the dedicated audience ID token.
It has read-only contents and ID-token permission and uploads only validated `cards.json`.
A second job gets contents/PR write permissions but no Google credentials or ID-token permission.
It downloads only that same-run sanitized artifact, validates it with the shared local CLI,
formats it with repository Prettier, then validates the formatted bytes against the size cap.
It creates or updates a PR from `automation/guest-cards-snapshot` to main. The official
create-pull-request action is pinned to an immutable v8 commit and restricts `add-paths` to
`static/guest/cards.json`. Use `GITHUB_TOKEN`; enable repository Actions PR creation and review
any pending CI-run approval. Do not auto-merge or deploy.

Track the approved public JSON in Git, starting with an explicitly empty envelope. Public content
and prior snapshots remain in history. The owner accepted this retention in the follow-up.
Keep private fields and synthetic browser fixture words out of the production file. Ignore only
temporary export files. CI validates the committed snapshot before build or test fixtures.

Keep `deploy.yml` independent. It validates the committed JSON, builds the frontend and deploys
the same-run Pages build artifact without Google credentials or BE access. Both workflows use
only `workflow_dispatch`, restrict privileged jobs to trusted main and use separate concurrency
groups. There is no schedule, push publication, export-to-Pages dependency or automatic merge.

Failed export leaves main and Pages unchanged. A successful export updates only its PR until
review and merge. Only a successful manual Pages deployment publishes the committed snapshot.
An intentional empty export can withdraw cards through the same review/merge/publication process.
Never replace a failed API response with fixtures or accidental empty data.

First publish the static frontend with the intentional empty seed while the existing backend
remains available. Verify guests use no API requests, then deploy/configure the final protected
exporter backend and remove the unused anonymous route. Configure the exact export workflow WIF
trust, manually export, review/merge the public snapshot PR, then manually publish Pages again.
Pages remains independently deployable without BE or WIF availability.

If real cards are needed at the first static publication, optionally deploy supporting backend
commit `34c7560`, which retains the anonymous endpoint for the existing frontend. Configure the
exporter and review/merge a snapshot before static publication. Keep the supporting and final
removal releases separately deployable. Never remove the anonymous route before static Pages
publication succeeds. A rollback to the old API-dependent frontend after removal requires a
compatible backend release as well.

Protected-environment variables and WIF bindings must exist before the first manual run.
Preserve existing protected-environment review requirements. Manual dispatch does not bypass
environment approval or grant a different identity additional access.

## Guest frontend

Load the snapshot from the static site's own base-aware asset URL. Do not read
`PUBLIC_API_BASE_URL`, attach credentials, call the anonymous API, or fall back to it.
Validate the snapshot and size before using it. Download once per mounted guest controller;
cache only within that controller, respecting cancellation and guest expiry.

Each round samples at most ten distinct cards from the in-memory pool. Practice again samples
locally without a request. Fewer than ten cards yields a smaller round. Cards can recur across
rounds. Keep existing flip-before-answer behavior, explicit guest choice, 30-minute guest
deadline, and authenticated private-review behavior. Guest answers remain memory-only.

Keep loading, empty, and retryable download-error states. Remove API-specific cooldown behavior
from the static transport. A retry follows an explicit user action, with no private API fallback.
Development and CI install clearly synthetic fixtures only in ignored build output after build;
they never modify the tracked source JSON. Approved public card content is committed through PRs.

## Limits

The entire snapshot is public, including future cards selected from this approved deck.
Public content may be downloaded and retained. Archive, edit, or removal affects the next
successful snapshot deployment, not previously downloaded copies. A failed refresh retains older
public content until a successful deployment or explicit site takedown. Static hosting still
serves traffic and has its own limits, but guest reads do not consume API or database capacity.

## Verification and delivery

- Backend unit tests cover fail-closed configuration, machine-token claims, caller-filter rejection,
  public field projection, and rejection before database access.
- Disposable PostgreSQL tests cover active English deck scope, archive handling, at-most-50
  uniqueness, empty versus invalid deck behavior, read-only enforcement, and unchanged learning tables.
- Script tests cover malformed and oversized responses, redirects, timeout, secret-safe failures,
  and atomic replacement. Workflow checks verify trusted triggers and artifact-only transfer.
- Frontend tests cover snapshot validation, local ten-card sampling, cancellation, retry, and
  repeated rounds without refetch. Browser checks cover guest and existing private review with
  a synthetic static snapshot and no guest backend requests.
- Run generated API checks, frontend checks and relevant tests, backend Ruff and PostgreSQL tests,
  a static build and subpath browser verification, and changed-file lint and diff checks.
- Update architecture, development instructions, decisions, and project memory after implementation.
  Record live IAM setup and deployment separately from local verification.

Do not change production resources, dispatch publication, or claim live publication while only
implementing and verifying the repository changes.
