# Issue #22 — Read-only CSV import validation boundary

## Outcome

Issue #22 implements a local, one-time CSV dry run for the legacy Google Sheet. It reads a fixed
snapshot, validates every row, persists only import audit records, and emits a bounded JSON report.
It cannot create confirmed cards, tags, review states, review batches, or review events.

The private file `apps/api/legacy-google-sheet-cutover-v1.csv` is explicitly ignored. Tests and the
checked-in report use synthetic English and Japanese fixtures only.

## Boundary and invocation

The importer is a local CLI rather than a permanent HTTP upload endpoint because the Sheet is used
only for the one-time cutover. Run it from `apps/api/` after migrating PostgreSQL and creating the
owned target deck:

```bash
uv run python -m app.imports \
  --csv legacy-google-sheet-cutover-v1.csv \
  --source-namespace legacy-google-sheet-cutover-v1 \
  --owner-id OWNER_ID \
  --deck-id DECK_UUID \
  --target-language en \
  --snapshot-captured-at 2026-09-09T00:00:00+08:00 \
  --report /tmp/legacy-google-sheet-dry-run.json
```

The owner and deck must already exist. A composite owned-deck lookup rejects cross-owner IDs, and
the deck language must match the requested target language. The report path should remain outside
the repository when validating private data.

## Identity, hashing, and replay

- Source namespace is a stable, trimmed NFC string selected once for the cutover.
- Stable row identity is SHA-256 over the namespace and the trimmed NFC legacy `id`. It does not use
  a row number, card UUID, or private card content. Duplicate normalized legacy IDs reject every
  conflicting row.
- Per-row content hash is SHA-256 over target language plus the ordered, trimmed NFC header/value
  pairs. The raw values are never persisted.
- Snapshot hash is SHA-256 over target language, fixed snapshot timestamp, canonical headers, and
  canonical rows. It identifies the complete import package rather than filesystem bytes.
- Validator version is part of replay identity. Repeating the same owner, namespace, snapshot, and
  validator version returns the existing run. A changed row creates a new snapshot/run while its
  stable source identity stays the same.

## Unicode and collection policy

- Stored content candidates use Unicode NFC after trimming surrounding whitespace. NFC preserves
  compatibility distinctions that may be meaningful in learning content.
- Source IDs use case-sensitive trimmed NFC identity.
- Tag and related-word comparison keys use NFKC plus Unicode case-folding. Display values remain
  trimmed NFC.
- Synonyms, antonyms, and tags split on commas. Empty and normalized duplicates are removed with
  explicit repair diagnostics; more than 20 values or overlong entries reject the row.
- UTF-8 and UTF-8 with BOM are accepted. Input is limited to 10 MiB, 10,000 rows, and 20,000
  characters per cell. Each row and run also has a bounded diagnostic list with a separate total and
  truncation flag.

## Fresh scheduling policy

All accepted cards will start fresh during the later confirmed import. The six legacy scheduling
or derived fields are validated to explain source quality but are never authoritative:

- Valid legacy values receive the informational `legacy_schedule_reset` diagnostic.
- Missing, malformed, out-of-range, incomplete, or contradictory scheduling fields receive repair
  diagnostics and still allow otherwise valid content.
- No dry run writes a new review state or review history. The later confirmed importer must create
  the normal backend-defined initial state in the same transaction as each confirmed card.

This policy intentionally gives up historical scheduling continuity so the user can review every
migrated card from a known backend state.

## All 21 field outcomes

| Legacy field | Validated destination or explicit outcome |
| --- | --- |
| `id` | Hashed stable source identity; never a card UUID |
| `lessonDate` | `learning_cards.learned_on`, interpreted as an `Asia/Taipei` calendar date |
| `content` | Required `learning_cards.term` |
| `type` | Canonical `part_of_speech`; unknown legacy labels become `other` detail with a repair |
| `phonics` | Nullable `learning_cards.pronunciation` |
| `chineseExplain` | Required `learning_cards.meaning` |
| `engExplain` | Nullable `learning_cards.target_language_definition` |
| `synonyms` | Ordered, normalized `learning_cards.synonyms` |
| `antonyms` | Ordered, normalized `learning_cards.antonyms` |
| `tags` | Normalized owned tags and card/tag associations during confirmed import |
| `note` | Nullable `learning_cards.note` |
| `supplementary` | Nullable `learning_cards.supplementary_note` |
| `example` | Nullable `learning_cards.example_sentence` |
| `status` | Active or archived card; blank defaults active with a repair; unknown values reject |
| `reviewStage` | Validated, diagnosed, then reset |
| `easeFactor` | Validated, diagnosed, then reset |
| `intervalDays` | Validated, diagnosed, then reset |
| `lastReview` | Validated, diagnosed, then reset |
| `nextReview` | Validated, diagnosed, then reset |
| `createdDate` | `learning_cards.created_at`; blank/malformed values use the fixed snapshot time with a repair |
| `overdueDays` | Validated diagnostic only; due state remains derived at query time |

## Diagnostic safety

Diagnostics contain only an allowlisted field name, machine-readable code, severity, row number,
hashes, counts, and truncation state. They never include term, meaning, definition, tags, notes,
examples, rejected values, credentials, tokens, database URLs, or exception text. Unknown header
names are reported only as an aggregate `unknown_headers` code.

## Verification

- Pure unit tests cover deterministic English/Japanese reports, all 21 mappings, header failures,
  required values, duplicates, dates, numeric ranges, Unicode, arrays/tags, scheduling reset, and
  private-content exclusion.
- PostgreSQL tests cover owned deck/language conflicts, unchanged replay, changed content, persisted
  per-row diagnostics, and unchanged counts for every confirmed learning/review table.
- The migration test exercises clean upgrade, downgrade to baseline, re-upgrade, downgrade to base,
  and final re-upgrade.

See [`sanitized-dry-run-report.json`](sanitized-dry-run-report.json) for deterministic synthetic
English and Japanese output.

完整的問題解析、commands 說明、學習重點與 confirmed-import handoff，請參考
[`learning-notes.md`](learning-notes.md)。
