# Separate guest export verification

Date: 2026-10-23. Checkout: `/Users/joseph/Documents/Git/english-learning`.
Branch: `codex/separate-guest-card-export`.
Review base: `f0d9d5c23acf6a065c90d12579fa0a361b3f7e37` (merged PR #58).
Scope: [approved follow-up plan](2026-10-23-separate-guest-export-plan.md).
This is the worker's verification record, not an independent review verdict.

## Implemented behavior

- Pages remains manual-only and builds the tracked snapshot without exporting, downloading an
  export artifact or obtaining Google credentials. Its privileged jobs require main.
- The separate manual export workflow requires main. The protected exporter has only contents
  read and ID-token write permissions. The PR proposal job has contents and PR write permissions,
  no Google credentials or ID-token permission, and downloads only the same-run sanitized artifact.
- The pinned official create-pull-request v8 action updates the managed
  `automation/guest-cards-snapshot` branch into main with only `static/guest/cards.json` in
  `add-paths`. It uses `GITHUB_TOKEN` and never merges or deploys.
- The proposal job validates compact export, formats it with Prettier, then revalidates the actual
  formatted bytes. This avoids formatting failures in generated PRs and rejects formatting growth
  over 512 KiB. The shared parser also validates CI/Pages source files without logging contents.
- The tracked production snapshot is intentionally empty (0 cards, 83 bytes), not a synthetic or
  real API export. The preexisting ignored file matched the browser fixture exactly before replacement.
- Browser preparation runs after build and replaces only ignored `build/guest/cards.json`.
  Its fixture source resolves relative to the script, so preparation from an isolated temporary
  working directory preserves a source-file sentinel. Guest controller/backend contracts are unchanged.
- Documentation describes Git retention, manual export/review/merge/manual Pages publication,
  repository Actions PR creation, CI approvals and the exact new WIF workflow trust reference.
  Empty-seed Pages deployment is independent of exporter setup; support commit `34c7560` remains optional.

## Checks

| Command                                                                                                                                                             | Observed result                                                                                                         |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `node --test tests/frontend/guest-publication-workflow.test.mjs tests/frontend/guest-snapshot-publication.test.mjs`                                                 | 14 passed, including safe local validation, source preservation, compact-export formatting and formatted-size rejection |
| `npm run test:frontend`                                                                                                                                             | 55 Node tests and 116 Vitest tests passed                                                                               |
| `npm run check`                                                                                                                                                     | 0 errors and 0 warnings                                                                                                 |
| `UV_CACHE_DIR=/tmp/english-learning-uv-cache npm run api:check`                                                                                                     | Passed; no generated artifact drift                                                                                     |
| `node scripts/validate-guest-snapshot.mjs static/guest/cards.json`                                                                                                  | Passed: 0 cards, 83 bytes; unchanged after browser runs                                                                 |
| `npm run test:browser -- tests/browser/guest-review-flow.spec.ts tests/browser/review-flow.spec.ts`                                                                 | 36 passed, root-hosted; includes 1280px and 390px guest flows and private regressions                                   |
| `BASE_PATH=/english-learning npm run test:browser -- tests/browser/guest-review-flow.spec.ts tests/browser/review-flow.spec.ts`                                     | 36 passed, subpath-hosted; same guest/private coverage                                                                  |
| Root and subpath `npm run build` with safe browser-test public configuration, then `cmp static/guest/cards.json build/guest/cards.json` and local output validation | Both builds passed; each emitted the exact 83-byte empty source snapshot and local output validation passed             |
| `npm run lint:changed -- f0d9d5c23acf6a065c90d12579fa0a361b3f7e37`                                                                                                  | Passed after correcting ESLint regex-space findings                                                                     |
| `git diff --check` and `git diff --cached --check`                                                                                                                  | Passed                                                                                                                  |

The clean build commands each set
`PUBLIC_GOOGLE_AUTH_CLIENT_ID=browser-contract-test`,
`PUBLIC_EMAIL_WHITE_LIST=browser-test@example.com`, and
`PUBLIC_API_BASE_URL=http://127.0.0.1:8001`. They ran `BASE_PATH= npm run build` and
`BASE_PATH=/english-learning npm run build`, each followed by
`cmp static/guest/cards.json build/guest/cards.json` and
`node scripts/validate-guest-snapshot.mjs build/guest/cards.json`. No server was running during
these independent builds. The output matched the tracked source, not the browser fixture.

The first browser attempt could not bind localhost inside the sandbox (`EPERM`). Both successful
runs used approved local-server execution outside that restriction. Playwright owned and stopped
its disposable static and mock API servers. Final `lsof` checks found no listeners on ports
4173 or 8001. Synthetic cards were confined to fixture/build output.
The local workflow checks inspect trigger, permission and transfer configuration; they do not
establish that GitHub Actions or Google WIF ran successfully.

## Evidence limits

No backend implementation, request model, database or container behavior changed. Backend Ruff,
PostgreSQL and container suites were not rerun for this workflow/publication follow-up. API drift
checking passed, but this does not establish live deployment.

No production API/card fetch, IAM change, repository setting change, workflow dispatch, publication,
merge or push was performed. WIF must trust the exact `export-guest-cards.yml@refs/heads/main`
reference, protected environments must restrict main, and repository policy must allow Actions PR
creation before the first export. Automation-created PR CI may need maintainer approval. Public
cards remain in Git history after publication. The empty bootstrap deliberately has no guest cards.

The unrelated untracked `doc/product/2026-10-21-guest-review-plan.md` is preserved and excluded from
this implementation. The parent will arrange independent reviewer verification of the frozen target.
