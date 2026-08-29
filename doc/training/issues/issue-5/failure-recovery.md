# Issue #5 Failure and Recovery Matrix

- Date: 2026-08-29
- Status: Approved MVP design; not implemented

## Guarantees

- Validation and authorization failures commit no changes.
- Card creation and its initial review state commit together.
- Tag deletion, association removal, and affected card-version changes commit together.
- A review batch, all review events, and all review-state transitions commit together.
- Reads never reserve cards or create review sessions.
- Automatic retries are bounded and used only where replay is proven safe.

## Creation idempotency

Deck and card creation require a client UUID `Idempotency-Key` because duplicate deck titles and
card terms are valid. Each created row stores nullable `creation_idempotency_key` and
`creation_request_hash`; normal API creation supplies both, while import-created rows may leave both
null. PostgreSQL enforces per-owner uniqueness for non-null creation keys and a check that the two
fields are null or present together.

- Same owner/key/hash returns the original `201 Created` body and `Location`.
- Same owner/key with different content returns `409 idempotency_key_reused`.
- Pre-commit failure leaves no resource/key, so the same request can execute normally.
- A retry after a lost committed response reconstructs the original resource response.
- Tag creation needs no separate key because normalized per-user uniqueness provides create-or-reuse.

## Operation matrix

| Operation | Failure | Durable result | Retry/recovery |
| --- | --- | --- | --- |
| Authenticate | Missing, invalid, or expired token | None | Reauthenticate, then repeat |
| List/read | Invalid filter or cursor | None | Correct request; do not retry unchanged |
| List/read | Temporary database outage | None | Retry with bounded backoff |
| Create deck | Validation failure | None | Correct fields and use a new logical request |
| Create deck | Ambiguous timeout | Unknown to client | Replay exact body with same key |
| Create card | Deck missing/cross-owner | None | Non-disclosing 404; do not retry blindly |
| Create card | Deck archived | None | Restore or select another deck |
| Create card | Card or initial state insert fails | Both roll back | Retry exact body/key when temporary |
| PATCH deck/card | Stale `If-Match` | None from stale request | Refetch, compare, and reconcile explicitly |
| PATCH deck/card | Ambiguous timeout | May have committed | GET and compare intended fields; do not blind overwrite |
| Archive | Already archived | Desired state already exists | Return idempotent success |
| Archive | Transaction failure | Rollback | Repeat safely when temporary |
| Restore | Already restored | Desired state already exists | Return current resource |
| Restore card | Parent deck archived | Card restored but not reviewable | Show effective inactive state |
| Create tag | Normalized tag exists | Existing tag retained | Return existing tag |
| Rename tag | Normalized collision | No change | User chooses another name |
| Attach tag | Already attached | Desired state exists | Return current card without version increment |
| Attach tag | 20-tag cap | No change | Remove a tag before retrying |
| Unlink tag | Already absent | Desired state exists | Return current card without version increment |
| Delete tag | Association/card-version cleanup fails | Entire transaction rolls back | Repeat when temporary |
| Delete tag | Response lost after commit | Tag and associations are gone | Treat subsequent 404 as desired recovery state; refresh cards |
| Get due | No eligible cards | No change | Return normal empty collection |
| Get due | State changes after read | Snapshot read remains valid | Submission detects stale version |
| Submit review | Validation failure | Nothing | Correct request; new logical key if content changes |
| Submit review | Stale or inactive item | Whole batch rolls back | Refetch due state; do not replay old decision blindly |
| Submit review | Temporary transaction failure | Rolled back or committed but response unknown | Same key/body replay |
| Submit review | Response lost after commit | Batch/events/states committed | Same key/body returns original result |
| Read history | No events | No change | Return normal empty collection |
| Read history | Temporary database outage | No change | Retry with bounded backoff |

## PATCH ambiguous-result recovery

After an ambiguous PATCH result, the frontend fetches the current resource and compares only the
fields it intended to change. Matching values mean the prior operation succeeded. Divergent values
require explicit reconciliation against the new version; the client never automatically overwrites
a newer edit.

## Concurrency ordering

- Archive and review lock affected cards consistently. A review committed first is valid; an archive
  committed first causes the review batch to fail inactive with no review writes.
- Tag deletion locks affected cards in deterministic UUID order before deleting associations and
  incrementing content versions.
- Review batches lock card states in deterministic UUID order. The first valid commit advances
  versions; stale contenders roll back completely.

## Retry classification

Safe automatic retry:

- GET after temporary failure;
- archive/restore desired-state commands;
- tag attach/unlink desired-state commands;
- deck/card creation with the same key and exact body;
- review submission with the same key and exact body.

Requires refetch, request correction, or user action:

- stale PATCH or review state;
- archived review target;
- tag-name conflict;
- validation or unsupported scope;
- changed content under an existing idempotency key.

Authentication errors require authentication recovery first. Ownership IDs are never changed to
work around a 404. Retryable responses may include `Retry-After`, and all automatic retries are
bounded with backoff.

## Logging and disclosure

Failures log request ID, authenticated internal user ID, operation, safe resource identifiers, error
code, known transaction outcome, retry count, and duration. Logs exclude Google tokens,
authorization headers, credentials, connection strings, and full private card content by default.
Unexpected client errors expose a request ID but never internal exceptions or transaction details.
