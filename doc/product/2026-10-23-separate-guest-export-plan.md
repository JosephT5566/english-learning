# Separate guest export from Pages deployment

Status: approved follow-up on 2026-10-23. The owner accepted committing the approved public
snapshot through an export-created PR. PR #58 is merged; work starts from main commit
`f0d9d5c23acf6a065c90d12579fa0a361b3f7e37` on `codex/separate-guest-card-export`.

## Outcome and boundaries

Keep both publication workflows manual-only. Pages builds the committed snapshot without
exporting cards, reading an expiring export artifact, or obtaining Google credentials. A separate
manual export workflow reads the existing protected API and proposes only the public JSON change.
It does not merge or deploy. Approved public content may remain in Git history; private fields,
credentials and arbitrary learning data remain excluded.

The prior same-run artifact transfer between export and Pages, and the rule forbidding the
approved public JSON in Git, are superseded. The machine-authenticated API, 50-card and 512 KiB
bounds, strict public-field validation and in-memory guest review behavior remain unchanged.

## Implementation and verification

- [x] Restore `.github/workflows/deploy.yml` to its build-to-Pages role. Retain manual dispatch,
      existing frontend environment/base path, Pages concurrency and protected deployment. Validate
      the committed snapshot locally before building, with no API call or export-job dependency.
- [x] Add `.github/workflows/export-guest-cards.yml`, manual dispatch and trusted main only.
      A protected export job uses the existing dedicated short-lived WIF identity and safe downloader.
      Its permissions are read-only contents plus ID-token minting. A separate proposal job gets
      only sanitized same-run JSON, with contents and PR write permissions but no Google token or
      ID-token permission. It validates the snapshot and creates or updates a dedicated automation
      PR into main, restricting `add-paths` to `static/guest/cards.json`. Never auto-merge or write main.
- [x] Use the immutable official `peter-evans/create-pull-request` v8 commit
      `5f6978faf089d4d20b00c7766989d076bb2fc7f1`. Use the repository `GITHUB_TOKEN`, not a new PAT.
      Document enabling Actions PR creation and approval of automation-created CI runs when required.
- [x] Track `static/guest/cards.json`. Bootstrap with a valid, explicitly empty snapshot, never
      synthetic example cards or an unverified real export. Preserve any unrelated local content.
      Remove its ignore rule; keep temporary export artifacts ignored. Failed exports leave main
      and the deployed snapshot unchanged. An intentional empty export can withdraw published cards
      after PR review, merge and manual Pages publication.
- [x] Add a small reusable local snapshot validation CLI using the existing schema/parser and
      size bounds. Run it in Pages, the proposal job and CI so the actual committed pool is checked
      before browser fixtures are installed. Do not print card contents or tokens.
- [x] Change browser fixture preparation to write only `build/guest/cards.json` after building,
      never `static/guest/cards.json`. Test fixture setup against a temporary directory containing a
      tracked-source sentinel to prove it is preserved.
- [x] Update workflow/CLI/fixture tests and the architecture, development, decisions, product
      memory and active design text. Mark earlier verification as historical where appropriate.
      Update WIF workflow trust references to `export-guest-cards.yml`; no live IAM changes here.
- [x] Run relevant Node/frontend tests, `npm run check`, root and nonempty-subpath guest browser
      verification/builds, generated API drift, changed-file lint, and `git diff --check`. Backend
      implementation is unchanged, so no new backend behavior test is required for this follow-up.
- [ ] Freeze sources and obtain independent reviewer verification of manual-only triggers,
      separated credential/write permissions, path-restricted PR updates, source-preserving fixtures,
      committed JSON validation and BE-independent Pages deployment. Independent review remains
      the parent's next step after the worker freezes sources.

Record exact results and any setup limitations. Do not call the real exporter, configure cloud
resources, dispatch publication, merge PRs or publish a site. Preserve unrelated untracked
`doc/product/2026-10-21-guest-review-plan.md`.
