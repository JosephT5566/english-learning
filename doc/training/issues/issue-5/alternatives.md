# Issue #5 Alternatives, Tradeoffs, and Unresolved Decisions

- Date: 2026-08-29
- Status: Approved design record; not implementation evidence

## Rejected alternatives

| Chosen direction | Rejected alternative | Why rejected | Accepted consequence |
| --- | --- | --- | --- |
| Shared language-aware backend | Separate English/Japanese apps or tables | Duplicates ownership, review, migration, and authorization logic | Shared validation has language-aware rules |
| Backend scheduling | Browser-calculated stages/dates | Client state is untrusted and cannot guarantee atomic history/state | Algorithm changes deploy with backend |
| Correct intended ease calculation | Preserve reversed-argument bug | Defect is accidental and indefensible | Future schedules can differ from legacy behavior |
| Non-disclosing 404 | Cross-owner 403 | Resource existence is private | Public API gives less debugging detail |
| UUID API IDs plus internal BIGINTs | One ID type everywhere | Public integers enumerate easily; internal UUIDs add needless overhead | Developers follow two explicit conventions |
| Taiwan calendar days at midnight | Exact elapsed 24-hour intervals | Product is organized around daily study | Late review may become due shortly after midnight |
| One explanation language per deck | Multiple structured translations | Extra entity/UI has no first-version requirement | Additional languages use another deck or notes |
| One embedded example | Example child table | Ordering/lifecycle complexity is unproven | Multiple examples later require migration |
| Synonym/antonym arrays | Related-term child resources | UI needs small ordered strings, not independent identities | Individual edits replace the card array |
| Relational reusable tags | Embedded tag-name arrays | Rename, filtering, normalized identity, and reuse require a resource | Association writes require transactions |
| Hard-delete tags | Archive tags | Tags are organization metadata, not learning history | Deletion is irreversible |
| Archive decks/cards | Physical user-facing deletion | History, restore, and migration recovery require stable identities | Archived data remains stored |
| Atomic review batches | Independent per-item commits | Partial outcomes complicate retry/reconciliation | One stale item rejects the batch |
| Up to 10 decisions per request | One request per card | More network overhead and weaker batch outcome | Multi-row transaction needs deterministic locks |
| Cursor pagination | Offset/page pagination | Mutable lists can skip or repeat records | No arbitrary page-number jump |
| No read-time reservation | Persisted review sessions/locks | Requires expiry and abandoned-session recovery | Concurrent tabs may cause stale conflict |
| Separate AI drafts | Drafts in normal card table | Every card/review query would need perfect incomplete-draft exclusion | Future AI adds separate tables |
| Explicit AI confirmation | Provider directly creates cards | Output is untrusted and may be wrong | Authoring has another step |
| Modular monolith | Microservices, queues, caches | No measured requirement justifies operations cost | Later evidence may require refactoring |

## Accepted tradeoffs

- Duplicate terms preserve contextual meanings but permit accidental duplicates.
- Midnight scheduling can produce a short interval for a review completed just before midnight.
- Whole-batch atomicity rejects valid decisions when one item is stale or invalid.
- Non-disclosing 404 intentionally hides diagnostic distinctions.
- One example and one explanation language limit content richness for MVP simplicity.
- Review history shows current card metadata rather than historical wording snapshots.
- Archived records consume storage and require archive-aware queries.
- Restoring a card under an archived deck does not make it reviewable.
- Tag deletion permanently removes organizational metadata.
- Cursor pagination prevents direct page-number navigation.
- Ambiguous/stale PATCH recovery requires refetch and reconciliation, not last-write-wins.
- Corrected future scheduling differs from historical buggy calculations while imported state remains.
- Redundant constrained owner IDs add storage but enable database-enforced same-owner relationships.

## Unresolved before affected implementation

- Exact Unicode normalization/case-fold implementation and test vectors for tags and card arrays.
- Canonical request serialization used to compute idempotency hashes.
- Exact scheduling algorithm version identifier and deterministic transition test vectors.
- Per-category reject versus manual-repair policy for malformed imported scheduling rows.
- Stable legacy source namespace and Sheet-row identity details.
- Bounded transaction retry counts and timeout values.
- Whether representative PostgreSQL `EXPLAIN` results justify the planned trigram search index.
- Exact Google token audience/configuration per environment.

These must become explicit implementation acceptance criteria rather than being invented silently.

## Deferred to later project milestones

- Python packaging/dependency tool.
- Production API host and managed PostgreSQL provider.
- Migration rollback window and repeated-import source-row deletion behavior.
- Operational service objectives, alert thresholds, and long-term archive retention.

## Deferred AI choices

- Provider and model.
- Raw result and failed/discarded draft retention periods.
- Provider retention/training terms and user erasure behavior.
- Synchronous versus background execution.
- Whether measurements justify a durable job mechanism.

These do not block Issue #5 because AI integration is outside the first database-backed MVP; the
draft/validation/confirmation boundary is already defined.

## Final review targets

- Remove stale references to discarded example or related-term tables.
- Confirm endpoints, schema versions, and lifecycle rules agree.
- Confirm every idempotent response is reconstructable from stored state.
- Confirm ownership, archive, and retry rules do not conflict.
- Confirm all artifacts describe the same MVP boundary.
- Route unresolved choices into later ticket acceptance criteria.
