# Issue #23 — Transactional confirmed CSV import and reconciliation

## Outcome

Issue #23 applies one approved Issue #22 CSV snapshot exactly once to an existing owned PostgreSQL
deck. It rereads the private file, reproduces the complete dry-run metadata and hashes, and refuses
changed, deleted, rejected, foreign, archived, or language-conflicting input before product writes.

The frontend and Google Apps Script remain unchanged. Completing this import makes PostgreSQL a
verified migration candidate, not the application's runtime source of truth.

## Persistence and identity

Revision `20260910_0005` adds:

- `confirmed_import_runs`, unique by approved dry-run ID and by `(owner_id, source_namespace)`;
- `confirmed_import_mappings`, unique by source identity and by confirmed card;
- composite foreign keys binding mappings to the exact approved item hashes, apply scope, owner,
  namespace, and owned card.

Dry-run tables remain content-free approval evidence. Confirmed-import tables store counts, hashes,
safe states, and diagnostics only; canonical private card content exists only in process memory and
the normal product tables.

## Transaction boundary

The importer owns one SQLAlchemy session and PostgreSQL transaction. Inside it, the service:

1. locks the approved `import_runs` row and existing target deck;
2. compares the CLI metadata, re-read snapshot hash, and every approved item hash/outcome;
3. returns an existing completed result for exact replay;
4. creates every card in the requested deck;
5. reuses or creates normalized owned tags and creates card/tag associations;
6. creates exactly one fresh review state per card;
7. creates the completed apply run and every source-to-card mapping;
8. commits only after all rows succeed.

Any exception before or during commit rolls back all product and apply mutations. The checked-in
failure tests cover interruptions before writes, after card/tag/state/mapping writes, before the
apply record, and immediately before commit.

## Fresh scheduling

Every imported card receives:

```text
review_stage = 1
ease_factor = 2.50
interval_days = 0
last_reviewed_at = NULL
next_review_at = approved snapshot timestamp
version = 1
```

Legacy schedule values remain validation diagnostics and never initialize backend state.

## Replay and recovery

- An unchanged sequential or concurrent replay returns the original run and creates nothing.
- An edited or deleted source row changes the snapshot and blocks apply against the old dry run.
- A different dry run cannot apply an already committed owner/source namespace.
- Source edits after successful import never update, archive, or delete PostgreSQL cards.
- A process failure after commit but before reconciliation/report output is ambiguous only to the
  client. Retry finds the completed run, performs no product mutation, and completes or returns the
  persisted reconciliation.

## Reconciliation

Post-commit reconciliation verifies all rows, plus a deterministic bounded sample. It checks:

- eligible rows, mappings, and imported-card counts;
- owner and target-deck membership;
- exactly one deterministic fresh review state per mapped card;
- every canonical database content hash against its approved hash;
- canonical tag and association counts;
- archived-card count;
- sampled field booleans without raw values;
- zero review events or batches associated with imported cards.

A mismatch persists `reconciliation_status = failed`, emits safe diagnostic codes, and causes the
CLI to return exit code `3`. The report never includes raw terms, meanings, notes, examples, tokens,
credentials, SQL parameters, or database URLs.

## Evidence

- [`sanitized-confirmed-import-report.json`](sanitized-confirmed-import-report.json)
- [`sanitized-reconciliation-report.json`](sanitized-reconciliation-report.json)
- [`unchanged-replay-proof.json`](unchanged-replay-proof.json)
- [`failure-recovery-evidence.json`](failure-recovery-evidence.json)
- [`runbook.md`](runbook.md)

All artifacts use the checked-in synthetic English fixture and placeholder database identifiers.
They contain no private Sheet values.

## Verification

- Complete backend suite with PostgreSQL integration enabled: 220 passed, one existing upstream
  `TestClient` warning.
- Focused tests cover canonicalization, first apply, exact/concurrent replay, ownership and target
  checks, changed/deleted/rejected input, failure injection, post-commit recovery, reconciliation,
  CLI exit/report behavior, and evidence safety.
- Alembic clean upgrade, downgrade to baseline, re-upgrade, downgrade to base, and final re-upgrade
  pass against PostgreSQL 17.
- Ruff lint/format, `uv lock --check`, and whitespace checks pass.

The ignored real 596-row CSV has not been applied because its last recorded dry run still contained
three rejected rows. No production, remote CI, frontend cutover, or source-of-truth transition is
claimed.
