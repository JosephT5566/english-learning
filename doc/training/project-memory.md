# English Learning Project Memory

Last updated: 2026-08-28

## Purpose

Build credible full-stack and backend engineering depth by evolving the existing English-learning application into a deployed multilingual product. The work should demonstrate API and schema design, safe data migration, authorization, transactions, failure recovery, frontend integration, AI safety, and operational ownership.

This is project evidence, not professional production-service experience.

## Current system

- SvelteKit 2 and Svelte 5 static frontend
- GitHub Pages deployment
- Google Identity Services sign-in in the browser
- Google Apps Script API for vocabulary retrieval and review updates
- Google Sheets as the current data store
- English review routes and shared card components
- A semantic-search proposal exists but is not an active priority

## Target system

- One repository and modular monolith
- Existing SvelteKit frontend
- Python FastAPI backend
- PostgreSQL with SQLAlchemy 2 and Alembic
- Server-side Google token verification and per-user ownership enforcement
- Shared language-aware model for English and Japanese
- Transactional review history and current review state
- Idempotent Google Sheets import and controlled cutover
- AI-assisted definitions, readings, notes, and examples through editable drafts and explicit confirmation
- Automated tests, CI, deployment, observability, rollback, and recovery documentation

## Agreed decisions

- Use this repository rather than starting a new primary full-stack repository.
- Use Python first for the backend.
- Keep frontend and backend together while deploying them independently.
- Use PostgreSQL as the eventual source of truth.
- Preserve Google Sheets during a controlled migration, then remove it from the runtime path.
- Support English and Japanese through one backend and shared model.
- Defer semantic search until the transactional core is dependable.
- AI output cannot directly become confirmed learning content.
- Avoid microservices and infrastructure without demonstrated need.

## Active milestone

Week 0 — baseline and design.

Issue #4 current-state trace is documented in
[`current-state-flow-trace.md`](current-state-flow-trace.md). It includes the three request flows,
trust boundaries, Apps Script and Sheet contracts, a current-state diagram, actual local command
results, and a sanitized synthetic fixture.

GitHub tracking:

- [Weeks 0–3 roadmap issue](https://github.com/JosephT5566/english-learning/issues/12)
- Training tickets: [#4](https://github.com/JosephT5566/english-learning/issues/4) through [#11](https://github.com/JosephT5566/english-learning/issues/11)

Required outputs:

- trace Google login and client-side token handling
- trace vocabulary retrieval from Google Apps Script
- trace review updates to Google Sheets
- inventory current Sheet fields and migration risks
- define English and Japanese card requirements
- draft the AI generation → editable draft → confirmation boundary
- propose the initial schema, API boundary, and trust-boundary diagram

## Open decisions

- Exact card schema for meanings, readings, pronunciation, examples, and language codes
- Review scheduling algorithm and compatibility with existing Sheet fields
- Python dependency and packaging tool
- Production API host and managed PostgreSQL provider
- AI provider and model
- Whether initial AI generation meets synchronous latency requirements
- Exact migration rollback window and handling of source-row deletions

## Current-state findings

- `getList` is unauthenticated. The Apps Script deployment is available to `Everyone` and executes
  as the script owner.
- `getList` mutates Sheet row order and contains zero-based/one-based index mismatches: intended
  `lastReview` and `reviewStage` sorts operate on `intervalDays` and `status`; the final
  `overdueDays` sort is correct.
- Review submission authenticates the allowlisted caller but trusts client-selected card IDs and
  client-calculated stage, ease factor, and dates.
- Review rows are written one at a time, formula updates run separately, and the success response
  is only `{ "ok": true }`; partial outcomes cannot be reconciled by the frontend.
- No Sheet data-validation or uniqueness rules were identified. `overdueDays` is derived as
  `TODAY() - nextReview`, while stored `intervalDays` is not updated by the current review payload.
- The most important persistence-migration risk is carrying client-controlled state transitions
  into PostgreSQL. The new backend must enforce ownership and derive and persist transitions
  transactionally.

## Current blockers

None. Remaining issue #4 uncertainties are documented rather than hidden: blank sort behavior,
the exact Apps Script exception envelope, concurrency/locking outside the inspected function, and
the absence of a repeated signed-in end-to-end update during the documentation session.

## Next action

Review and close
[issue #4: Trace the current auth, vocabulary, and review flows](https://github.com/JosephT5566/english-learning/issues/4)
if its recorded uncertainties are acceptable. Then begin the next Week 0 design ticket before adding
FastAPI.
