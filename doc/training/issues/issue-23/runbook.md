# Confirmed import, source-of-truth, and rollback runbook

## Preconditions

- Use a dedicated clean cutover database, not a database containing test fixtures or unrelated
  development data.
- Confirm the internal owner and target deck already exist and that the deck is active with the
  intended target language.
- Keep the private CSV, reports, and any database dump outside version control with restricted local
  permissions.

## Phases and authority

1. **Before confirmed import:** the legacy Sheet remains authoritative. PostgreSQL data must not be
   presented as the live migrated dataset.
2. **Freeze and export:** stop legacy Sheet mutations and export one final UTF-8 CSV snapshot. If the
   freeze cannot be maintained, cancel the attempt and export again later.
3. **Dry run and approval:** run Issue #22 validation, require zero rejected rows, inspect the safe
   report, and retain its exact run ID, namespace, language, timestamp, validator version, and CSV.
   Passing that run ID to the confirmed CLI is the explicit operator approval.
4. **Confirmed apply:** run the Issue #23 CLI once against the existing owned deck. Do not edit the
   CSV between dry run and apply.
5. **Reconcile:** require CLI exit code `0` and inspect both safe reports. Confirm all count/hash,
   ownership, card, tag, association, archived-state, fresh-state, sample, and review-history checks.
6. **Before frontend cutover:** the Sheet remains the application's runtime source of truth.
   PostgreSQL is only a verified migration candidate, even after reconciliation passes.
7. **No long-lived dual writes:** do not attempt to keep Sheet and PostgreSQL synchronized. Maintain
   the Sheet freeze until the later cutover decision.
8. **Failure before cutover:** if apply rolls back, correct the safe failure and retry the unchanged
   approved snapshot. If apply committed but reconciliation failed, do not rerun a different source;
   discard or restore the clean cutover database and retry from the approved snapshot. A failure
   after commit but before report output is retried unchanged so the CLI can recover the completed
   result without duplicates.
9. **Later authority gate:** PostgreSQL becomes authoritative only in the frontend-cutover ticket,
   after a reviewed backup, successful reconciliation, verified backend reads and writes, rollback
   decision, and explicit switch of frontend runtime traffic away from Google Apps Script.
10. **Close the rollback window:** after the PostgreSQL runtime path remains verified for the agreed
    window, securely remove private CSV and dump artifacts. Review whether to remove the local CLI
    and import-only audit tables in a later migration; do not delete them during Issue #23.

## Which system wins

| Phase | Authoritative system | Required response to divergence |
| --- | --- | --- |
| Before freeze | Legacy Sheet | Export only after establishing a new freeze |
| Freeze through verified import | Frozen Sheet snapshot | Restore/discard PostgreSQL candidate and retry |
| Verified import before cutover | Legacy Sheet runtime; frozen CSV is migration evidence | Do not synchronize automatically |
| After explicit frontend cutover | PostgreSQL | Use PostgreSQL-backed product APIs; do not edit CSV |
| During approved rollback window | Defined by the cutover ticket | Follow its traffic switch and database restore decision |

This runbook does not claim that the source-of-truth transition occurred in Issue #23.
