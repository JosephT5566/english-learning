# English Learning Full-Stack and Backend Training Plan

- Last updated: 2026-08-21
- Status: Active
- Target duration: 8 weeks, approximately 10–15 focused hours per week
- Repository: `english-learning`

## Decision

Evolve the existing English Learning application into a production-style full-stack system in this repository.

The current SvelteKit application remains the frontend. A Python FastAPI service and PostgreSQL database will replace Google Sheets and Google Apps Script as the application's runtime backend. The migration must preserve the existing review workflow and data.

This is a modular monolith. Do not split it into microservices. Semantic search is deliberately postponed until the transactional application, migration, authorization, deployment, and operations are dependable.

## Career objective

The project should create honest, defensible evidence that Joseph can own a feature across:

- requirements and API contracts
- relational data modeling and migrations
- backend implementation and testing
- authentication, authorization, and per-user data isolation
- transactions, concurrency, idempotency, and recovery
- frontend integration and failure states
- deployment, observability, rollback, and incident response
- architecture documentation and technical explanation

Project work must be described as project experience, not professional production ownership.

## Product objective

Users can securely learn English and Japanese, manage study cards, and complete reviews without depending on Google Sheets at runtime. Existing Sheet data can be imported safely, verified, and recovered if migration fails.

The initial database-backed product supports:

- Google sign-in
- separate English and Japanese learning sections backed by one language-aware domain model
- per-user card ownership
- card creation, editing, listing, filtering, and archiving
- tags
- due-review retrieval
- review submission and review history
- an idempotent Google Sheets import
- basic progress statistics
- AI-assisted card drafts for definitions, readings, learning notes, and examples
- explicit user review and confirmation before AI output becomes a study card

## Success criteria

The core migration is complete when:

1. PostgreSQL is the source of truth for application reads and writes.
2. Existing Sheet records are imported without silent loss or duplication.
3. Google ID tokens are verified by the backend, and every protected operation enforces ownership.
4. Concurrent or retried review submissions cannot corrupt review state or create duplicate events.
5. API, database integration, authorization, migration, and critical frontend flows have automated tests.
6. The frontend handles loading, validation, unauthenticated, forbidden, conflict, retryable, and server-error states.
7. The system is deployed with health checks, structured logs, useful metrics, and documented rollback and recovery procedures.
8. English and Japanese use shared APIs and review behavior without duplicating the application into language-specific backends.
9. AI output is treated as untrusted draft data, validated by the backend, and confirmed by the user before becoming durable learning content.
10. Joseph can explain the schema, migration, authorization boundary, transaction design, AI trust boundary, failure behavior, and operational decisions without generated notes.

## Proposed stack

### Frontend

- Existing SvelteKit and TypeScript application
- Existing Google Identity Services login UI
- Playwright for a small number of critical end-to-end tests

### Backend

- Python 3.12+
- FastAPI and Pydantic
- SQLAlchemy 2
- Alembic
- PostgreSQL
- pytest
- Ruff
- HTTPX for API tests and external HTTP calls

### Development and delivery

- Docker Compose for local PostgreSQL and supporting services
- GitHub Actions for frontend and backend checks
- GitHub Pages for the static frontend unless requirements change
- A container platform such as Cloud Run for the API
- A managed PostgreSQL provider selected before production deployment

Do not add a queue, cache, vector database, or Kubernetes unless a measured requirement justifies it.

## Target repository structure

Restructure gradually; do not move the frontend before backend work actually requires it.

```text
english-learning/
├── apps/
│   ├── web/                       # Existing SvelteKit application
│   └── api/
│       ├── app/
│       │   ├── auth/
│       │   ├── cards/
│       │   ├── reviews/
│       │   ├── imports/
│       │   ├── ai/
│       │   └── users/
│       └── tests/
├── migrations/                    # Alembic migrations
├── scripts/                       # Import and reconciliation utilities
├── doc/
├── compose.yaml
└── README.md
```

Keeping web and API code together makes the end-to-end contract, CI, documentation, and migration history visible in one place. The API should still be independently buildable and deployable.

## Initial domain model

The exact schema must be defended before implementation. Begin with these concepts:

- `users`: stable internal ID, Google subject, normalized email, timestamps
- `learning_decks`: owner, target language, explanation language, title, and status
- `learning_cards`: deck, term, meaning, optional reading or pronunciation, notes, part of speech, status, timestamps, and version
- `card_examples`: card, target-language sentence, optional translation, source, and position
- `tags` and `learning_card_tags`: normalized per-user tags and associations
- `review_states`: current scheduling state for one learning card
- `review_events`: immutable history of review decisions and state transitions
- `import_runs`: status, source identity, counts, timestamps, and failure summary
- `import_items`: source row identity, content hash, outcome, and diagnostic details
- `ai_generation_runs`: owner, request purpose, provider-neutral model identifier, status, timing, token or cost metadata, and redacted failure details
- `card_drafts`: owner, target language, immutable raw AI result, editable validated fields, source, status, and version

Important invariants should be enforced by PostgreSQL where possible:

- Google subject is unique.
- Every deck has a supported target language and an owner.
- A learning card belongs to a deck and has a non-empty term and meaning before confirmation.
- Japanese-only fields such as kana reading are optional for other languages rather than requiring a separate Japanese table.
- Review state has at most one current row per learning card.
- Review events belong to the same user and item ownership boundary.
- An import source record cannot be applied twice within the same source namespace.
- An idempotency key cannot produce multiple review events for the same user.
- Review stage, ease factor, and interval values remain within valid ranges.
- A card draft can create at most one confirmed learning card.
- A late AI result cannot overwrite a user-edited or confirmed draft.

Choose IDs, deletion behavior, timestamp handling, supported language codes, transliteration policy, and duplicate-term policy explicitly rather than inheriting them accidentally from the Sheet. Prefer standard language codes such as `en` and `ja` over UI labels, and avoid one table per language.

## API principles

- Use versioned endpoints under `/v1`.
- Return a consistent error envelope with a stable machine-readable code.
- Validate at the boundary, but use database constraints for critical invariants.
- Never trust an email, user ID, or ownership field supplied by the client.
- Derive the current user from a server-verified Google token.
- Avoid returning internal exceptions or credentials.
- Define pagination and ordering before lists can grow.
- Require an idempotency key for state-changing review submissions.

Candidate endpoints include:

```text
GET    /health/live
GET    /health/ready
GET    /v1/me
GET    /v1/decks
POST   /v1/decks
GET    /v1/cards
POST   /v1/cards
GET    /v1/cards/{id}
PATCH  /v1/cards/{id}
DELETE /v1/cards/{id}
GET    /v1/reviews/due
POST   /v1/reviews
GET    /v1/reviews/history
POST   /v1/imports/google-sheets
GET    /v1/imports/{id}
GET    /v1/statistics/overview
POST   /v1/ai/card-drafts
GET    /v1/ai/card-drafts/{id}
PATCH  /v1/ai/card-drafts/{id}
POST   /v1/ai/card-drafts/{id}/confirm
```

These are starting points, not contracts. Each endpoint needs requirements, authorization rules, failure behavior, and acceptance tests before implementation.

## AI-assisted learning boundary

AI is an authoring assistant, not the source of truth and not an authorized database actor.

The first supported flow is:

1. The authenticated user submits a term, target language, explanation language, and optional context.
2. The backend applies rate and size limits, creates a generation record, and calls the configured AI provider.
3. The provider returns a narrowly structured result containing only allowlisted learning fields.
4. The backend validates structure, supported languages, field lengths, enums, example counts, and required Japanese reading fields when applicable.
5. The result is stored as a draft with provenance, not as a confirmed learning card.
6. The user reviews and may correct the meaning, reading, notes, or examples.
7. A separate confirmation command revalidates ownership, status, version, and content, then creates the card transactionally.

The AI provider must never choose a user ID, owner, database destination, authorization decision, arbitrary tool, or SQL statement. Prompt instructions and structured-output features improve behavior but are not security boundaries; application validation remains mandatory.

Preserve the raw generated result separately from the edited draft so corrections and model quality can be evaluated without overwriting provenance. Do not treat user corrections as consent to train a model. Define retention and redaction rules before storing prompts or outputs that may contain personal data.

Handle these failures explicitly:

- provider timeout or unavailable response
- invalid or incomplete structured output
- plausible-looking but incorrect definitions or examples
- stale edits from two browser tabs
- repeated confirmation after an ambiguous timeout
- a delayed generation result arriving after user edits or confirmation
- rate-limit or budget exhaustion

Start synchronously if latency is acceptable. Move generation to the durable job mechanism in Week 7 only when request duration or reliability evidence justifies it.

## Migration strategy

Treat the move from Google Sheets as a controlled data migration rather than a one-off script.

1. Document the current Sheet schema and identify malformed, missing, and duplicate values.
2. Export a read-only snapshot and record row count and a checksum.
3. Build a dry-run importer that validates every row without writing.
4. Define deterministic mappings from legacy fields and IDs to database fields.
5. Import into a staging or empty database transactionally where practical.
6. Produce created, updated, skipped, and rejected counts with row-level diagnostics.
7. Re-run the importer to prove idempotency.
8. Compare counts and representative records between the Sheet and PostgreSQL.
9. Switch frontend reads to the new API behind a temporary configuration switch.
10. Switch writes only after read verification succeeds.
11. Keep the Sheet snapshot and a documented rollback window.
12. Retire Google Apps Script runtime access only after the database path is stable.

Avoid long-lived dual writes. They introduce divergent sources of truth and difficult recovery. If a brief dual-write phase is necessary, define which system wins and how mismatches are detected and repaired.

## Weekly plan

### Week 0 — Baseline and design

Goal: understand and document the system before changing its persistence boundary.

- Run the existing frontend, checks, and production build.
- Trace login, word-list retrieval, and review-update flows end to end.
- Document the current Google Sheet fields and Apps Script contracts.
- Capture a sanitized sample dataset for tests.
- Write functional requirements, non-goals, trust boundaries, and failure expectations.
- Draft a language-aware domain model and API contract that support English and Japanese without separate backends.
- Define Japanese card requirements: term or kanji, kana reading, optional romanization, meaning, part of speech, and examples.
- Define the AI draft, edit, and confirmation trust boundaries before choosing a provider.
- Decide local and production deployment boundaries.
- Create a learning log and an architecture decision record for choosing a modular monolith.

Evidence:

- current-state architecture diagram
- proposed request-flow and trust-boundary diagram
- schema proposal with rejected alternatives
- reproducible baseline commands

Exit criteria:

- Existing behavior can be demonstrated locally.
- Every current data field has an intended database mapping or an explicit reason for removal.
- No backend code is started before the primary invariants and ownership rules are written.

### Week 1 — Backend foundation

Goal: establish a small, testable FastAPI service connected to PostgreSQL.

- Add the Python project, configuration management, and dependency tooling.
- Add local PostgreSQL through Docker Compose.
- Implement liveness and database-aware readiness endpoints.
- Configure SQLAlchemy sessions with explicit transaction ownership.
- Configure Alembic and create the first migration.
- Establish unit and PostgreSQL integration test patterns.
- Add Ruff, pytest, and backend checks to CI.
- Define the common API response and error conventions.

Evidence:

- API container starts reproducibly.
- A migration can upgrade an empty database and downgrade safely during development.
- CI runs frontend and backend checks independently.

Exit criteria:

- A new contributor can start the frontend, API, and PostgreSQL from documented commands.
- Readiness fails when the database is unavailable while liveness remains meaningful.

### Week 2 — Data model and read APIs

Goal: model multilingual learning cards and review state with database-enforced integrity.

- Implement users, decks, language-aware cards, examples, tags, review states, and review events.
- Add foreign keys, uniqueness, check constraints, and timestamps deliberately.
- Derive indexes from list, due-review, history, and import access patterns.
- Seed representative English and Japanese development data.
- Implement deck, card list/detail, language filtering, and due-review read APIs.
- Define stable ordering and cursor pagination.
- Add positive, empty, malformed, and database-failure tests.
- Inspect representative queries with `EXPLAIN` rather than guessing about performance.

Evidence:

- entity relationship diagram
- migration and constraint tests
- index rationale tied to queries
- API examples and error contract

Exit criteria:

- Invalid ownership and review-state relationships are rejected by the database.
- English and Japanese cards pass through the same ownership and review model while preserving language-specific optional fields.
- List results have deterministic ordering and pagination behavior.

### Week 3 — Authentication, authorization, and review writes

Goal: move trust and state transitions into the backend safely.

- Verify Google ID token signature, issuer, audience, expiry, and email verification server-side.
- Map the Google subject to an internal user; do not use mutable email as the primary identity.
- Add a reusable current-user dependency.
- Enforce ownership in every deck, card, and review query.
- Implement deck and card create/edit/archive APIs.
- Implement review submission as one explicit transaction.
- Store an immutable review event and update current review state atomically.
- Use an idempotency key to make client retries safe.
- Choose and test either optimistic versioning, a conditional update, or row locking for concurrent review submissions.
- Test cross-user access and concurrent duplicate submissions.

Evidence:

- authorization matrix
- transaction sequence diagram
- tests for horizontal privilege escalation
- concurrency and idempotency test results

Exit criteria:

- A client cannot select or modify another user's data by changing an ID.
- Retrying the same review request produces one logical state transition.
- Concurrent conflicting reviews have documented, deterministic behavior.

### Week 4 — Google Sheets import and reconciliation

Goal: migrate existing data without silent corruption or duplication.

- Implement the dry-run validation path first.
- Validate headers, required values, types, ranges, duplicate legacy IDs, and malformed rows.
- Define a stable source identity and content hash.
- Implement idempotent import with actionable row-level diagnostics.
- Ensure a failed import does not leave a partially accepted dataset without an explicit recovery state.
- Record import runs and per-row outcomes.
- Add reconciliation output for counts, hashes, and sampled field comparisons.
- Test first import, repeated import, changed rows, deleted source rows, malformed input, and interruption.
- Write the migration and rollback runbook.

Evidence:

- sanitized migration report
- repeat-import proof
- failure-injection tests
- documented source-of-truth transition

Exit criteria:

- Running the same unchanged import twice creates no duplicates or unintended state changes.
- Invalid rows are visible and actionable.
- Recovery behavior is documented for failure before, during, and after database writes.

### Week 5 — Frontend integration and cutover

Goal: make the existing user workflow run entirely through the new API.

- Add a typed API client boundary in the SvelteKit application.
- Replace Sheet list reads with card and due-review API calls.
- Replace Apps Script review updates with the transactional review endpoint.
- Add card creation and editing only after the review path is stable.
- Add English and Japanese sections that share components and API contracts while presenting the appropriate fields for each language.
- Handle loading, empty, validation, unauthenticated, forbidden, conflict, retryable, and server-error states.
- Preserve the temporary configuration switch for controlled fallback.
- Add contract tests or generated types to detect frontend/backend drift.
- Add end-to-end tests for login substitution, due review, successful review, safe retry, and authorization failure.
- Perform the read cutover, verify it, and then perform the write cutover.

Evidence:

- before/after request flow
- frontend error-state matrix
- cutover checklist and verification record
- critical end-to-end test results

Exit criteria:

- Normal application usage does not call Google Apps Script.
- A failed API call never appears as a successful review to the user.
- The rollback switch and its data-consistency limitations are understood.

### Week 6 — Deployment and operational ownership

Goal: deploy and operate the full system safely.

- Containerize the API with a non-root runtime and graceful shutdown.
- Select and configure managed PostgreSQL with encrypted connections.
- Store secrets outside source control and document rotation.
- Configure production CORS for the actual frontend origin.
- Add correlation IDs and structured logs without tokens or personal data.
- Add request rate, latency, error, database-pool, authentication-failure, review, and import metrics.
- Define a small set of actionable alerts.
- Document database backup and restore verification.
- Define migration-before-deploy, backward compatibility, staged rollout, and rollback procedures.
- Run a deployment rehearsal and one incident exercise.
- Write a short post-incident report with corrective actions.

Evidence:

- deployed application
- dashboard or saved metric queries
- deployment and rollback runbook
- incident timeline and post-incident report

Exit criteria:

- Health endpoints reflect meaningful service state.
- A failing request can be traced from frontend report to backend log and database action.
- The previous application version can run safely during a rollback-compatible migration window.

### Week 7 — AI-assisted card creation and asynchronous reliability

Goal: add AI-assisted English and Japanese card creation through a safe, reviewable draft workflow.

Begin with synchronous generation if the observed latency and failure behavior fit the API timeout budget. If they do not, make generation the project's justified durable asynchronous workflow. Do not create a queue merely for architectural appearance.

- Define the input and strict structured-output contracts for English and Japanese card generation.
- Generate definitions, readings or pronunciation, learning notes, and a bounded number of examples.
- Treat model and user-provided text as untrusted input; reject unknown and server-managed fields.
- Separate immutable raw generation, editable draft, and confirmed card states.
- Implement draft edit and transactional confirmation endpoints with ownership, optimistic version, uniqueness, and idempotency checks.
- Add user-visible review and correction before confirmation.
- Add per-user rate limits, request-size limits, timeouts, and a configurable spending budget.
- Record latency, validation failures, correction rates, confirmation outcomes, and redacted provider errors.
- If asynchronous, define job ownership, attempt limits, bounded retry, late-result behavior, and stuck-job recovery.
- Test invalid output, incorrect-but-valid content, provider timeout, stale edit, double confirmation, ambiguous timeout, and delayed result.
- Create a small labeled evaluation set for English and Japanese definitions, readings, and examples.

Evidence:

- AI trust-boundary and draft state-transition diagrams
- structured-output schema and semantic validation rules
- retry, idempotency, late-result, and deduplication policy
- bilingual evaluation and correction-rate report
- user-visible draft, progress, correction, and failure behavior

Exit criteria:

- AI output cannot directly create or overwrite a confirmed card.
- Repeated or concurrent confirmation produces at most one learning card.
- A late provider result cannot replace newer user intent.
- An operator can identify rising failures, exhausted budgets, and stuck generations.

### Week 8 — Hardening, performance, and interview readiness

Goal: turn the implementation into evidence that can survive technical review.

- Create a repeatable load test for the main read and review-write flows.
- Record a baseline before optimizing.
- Diagnose one real bottleneck using query plans, metrics, and traces or timing logs.
- Apply one justified optimization and record the comparison.
- Review dependency, secret, CORS, input-validation, authorization, and logging risks.
- Review AI prompt-injection boundaries, provider credentials, output validation, data retention, and cost controls.
- Refresh the README with architecture, setup, test, deployment, and demo instructions.
- Complete architecture, data-model, API, migration, trust-boundary, and operations documents.
- Record a five-minute project explanation and a 30-minute system-design walkthrough.
- Run mock interviews on multilingual schema design, authorization, concurrency, migration, AI safety, async recovery, and operations.
- Create a backlog for future improvements without adding them to the core release.

Evidence:

- reproducible performance report
- security review checklist
- concise portfolio case study
- interview question-and-answer log based only on implemented evidence

Exit criteria:

- Joseph can defend important decisions, alternatives, failure modes, and production behavior without reading prepared answers.
- The repository gives a reviewer a clear path from README to architecture, code, tests, deployment, and operational evidence.

## Core versus stretch scope

Weeks 0–6 are the database-backed multilingual core. Week 7 adds the AI-assisted authoring workflow, and Week 8 hardens the complete product. AI work must not delay completing the migration and deployment.

If time is limited, cut scope in this order:

1. extra AI-generated fields beyond definitions, readings, notes, and examples
2. asynchronous execution if synchronous generation meets measured requirements
3. extra product features
4. performance optimization beyond a measured baseline
5. frontend visual redesign

Do not cut authorization tests, migration reconciliation, idempotency, deployment verification, or recovery documentation. Those are central to the backend-learning objective.

## Deferred work

The following are explicitly outside the initial training plan:

- semantic or vector search
- RAG or chat features
- autonomous AI writes or agent-selected database operations
- a Go rewrite
- microservices
- Kubernetes
- event streaming
- complex social or collaborative features
- native mobile clients

After Week 8, evaluate semantic search using real product needs and a labeled relevance set. Evaluate a small Go service only if target roles consistently require Go and the Python design is already understood.

## Working cadence

A sustainable week can contain:

- three 90-minute implementation sessions
- one 60-minute design or reading session
- one 90-minute testing and failure-injection session
- one 45-minute verbal design review
- one 30-minute retrospective and learning-log update

Work on one issue at a time and prefer small pull requests. A weekly milestone may span several PRs.

## Per-ticket workflow

Before implementation:

1. Restate the user problem and acceptance criteria.
2. Write assumptions and non-goals.
3. Identify invariants and the trust boundary.
4. Define the API and data changes.
5. Define the transaction boundary.
6. List likely failures, user-visible behavior, detection, and recovery.
7. Compare at least one credible alternative.

During and after implementation:

1. Implement the critical path personally.
2. Use AI for focused explanations, review, scaffolding, or test ideas—not as a substitute for understanding.
3. Add positive, negative, authorization, concurrency, and failure-path tests proportional to risk.
4. Run relevant automated checks.
5. Update documentation and the learning log.
6. Explain the decision aloud in five minutes.
7. Open a focused pull request.

## Definition of done

A feature is complete only when:

- acceptance criteria pass
- authorization and validation are enforced server-side
- database invariants and transaction behavior are explicit
- relevant success and failure tests pass
- logs and metrics make important failures diagnosable
- deployment and migration compatibility are considered
- recovery or rollback behavior is documented when state can change
- public documentation matches actual behavior
- Joseph can explain the design and tradeoffs independently

## Interview evidence map

| Competency            | Project evidence                                                                      |
| --------------------- | ------------------------------------------------------------------------------------- |
| Full-stack ownership  | SvelteKit workflow integrated with a designed and deployed API                        |
| API design            | Versioned endpoints, validation, pagination, stable errors, and contract tests        |
| PostgreSQL            | Normalized schema, constraints, indexes, query plans, and Alembic migrations          |
| Authorization         | Server-verified identity and tested per-user ownership boundaries                     |
| Transactions          | Atomic review event and review-state transition                                       |
| Concurrency           | Deterministic handling of simultaneous review submissions                             |
| Idempotency           | Safe review retries and repeatable Sheet imports                                      |
| Migration             | Dry run, reconciliation, staged cutover, and rollback window                          |
| Async reliability     | Durable job state, bounded retry, deduplication, and recovery                         |
| AI application safety | Validated drafts, human confirmation, provenance, bounded permissions, and evaluation |
| Multilingual design   | Shared English/Japanese schema and APIs with explicit language-specific fields        |
| Operations            | Health checks, structured logs, metrics, alerts, deployment, and incident report      |
| Performance           | Reproducible load test and evidence-based optimization                                |

## Immediate next action

Create the Week 0 baseline issue. Its first deliverable is a current-state document tracing these three flows:

1. Google login and client-side token handling
2. vocabulary retrieval from Google Apps Script
3. review-state update to Google Sheets

The same issue should inventory the proposed Japanese fields and write the AI draft-to-confirm flow at a conceptual level. Do not scaffold FastAPI until the current contracts, data fields, ownership assumptions, multilingual requirements, and migration risks are recorded.
