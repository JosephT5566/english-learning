# Issue #10 - Backend authentication and owner authorization

## Implemented boundary

Every `/v1` product route requires `Authorization: Bearer <Google ID token>`. The backend passes the
token and configured `GOOGLE_OAUTH_CLIENT_ID` to Google's Python verifier, which validates the
signature, issuer, audience, and expiry against Google's keys. The application then requires a
nonblank `sub`, a nonblank email, and `email_verified=true`.

The verified Google `sub` is upserted into `users.google_subject` and resolves one generated internal
user ID. Email is normalized and refreshed as profile data; it is never used as the ownership key.
Handlers receive an `AuthenticatedUser` dependency and bind its internal ID into every ownership
predicate and create statement. Request bodies forbid extra fields, so `owner_id`, user IDs, and
emails cannot select ownership.

Missing credentials return `401 authentication_required`. Invalid, expired, wrong-audience,
malformed, unverified-email, and bad-signature credentials return `401 invalid_authentication`.
The token is not logged, placed in an error, or returned in a response. A Google key-fetch transport
failure returns retryable `503 identity_provider_unavailable`.

## Authorization matrix

| Route | Authentication | Authorized scope | Cross-owner result | Test evidence |
| --- | --- | --- | --- | --- |
| `GET /v1/me` | Valid Google ID token | Resolved internal user only | Not applicable | Stable `sub` mapping and email refresh |
| `GET /v1/decks`, `GET /v1/decks/{id}` | Required | Deck owner | Empty list / `404 deck_not_found` | Cross-user read test |
| `POST /v1/decks` | Required | Owner derived from auth | Client identity fields rejected `422` | Create ownership test |
| `PATCH /v1/decks/{id}` | Required | Deck owner and matching version | `404 deck_not_found` | Cross-user mutation test |
| `DELETE /v1/decks/{id}` | Required | Deck owner | `404 deck_not_found` | Cross-user mutation test |
| `GET /v1/cards`, `GET /v1/cards/{id}` | Required | Card owner | Empty list / `404 card_not_found` | Cross-user read test |
| `POST /v1/cards` | Required | Authenticated owner and owned active deck | `404 deck_not_found` | Foreign-parent create test |
| `PATCH /v1/cards/{id}` | Required | Card owner and matching version | `404 card_not_found` | Cross-user mutation test |
| `DELETE /v1/cards/{id}` | Required | Card owner | `404 card_not_found` | Cross-user mutation test |
| `GET /v1/reviews/due` | Required | Owned state joined to owned card and deck | Empty result or `404 deck_not_found` for a selected foreign deck | Cross-user due-read test |
| `GET /health/live`, `GET /health/ready` | Not required | Service health only | Not applicable | Existing health tests |

Detail and mutation endpoints intentionally use the same `404` for missing and cross-owner IDs. This
prevents resource enumeration while preserving a simple client contract. `PATCH` requires the last
seen positive version and returns `409 version_conflict` for a stale owned resource. Archive is a
soft delete and is idempotent for its owner.

## Learning checkpoint

The **authentication boundary** answers "who made this request?" It verifies the bearer token's
cryptographic and standard claims, requires a verified email claim, and maps Google's stable subject
to an internal user.

The **authorization boundary** answers "may that user perform this operation on this resource?" It
is enforced in SQL by combining the requested resource ID with the authenticated internal owner ID.
Creates bind that same server-derived owner ID.

A valid token alone does not authorize access to a card. It proves an identity, not ownership of an
arbitrary card ID. The card query must still establish `card.id = requested_id AND card.owner_id =
authenticated_user.id`; otherwise it returns the same not-found response as a nonexistent card.

## Verification

- `uv run pytest tests/unit -q`: 54 passed with one existing upstream warning.
- `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest -q`: 152 passed with the same warning.
- `uv run ruff check .`, `uv run ruff format --check .`, and `uv lock --check`: passed.

These are local correctness results. Live Google token verification, frontend cutover, review writes,
remote CI, deployment behavior, and production load remain outside this issue.
