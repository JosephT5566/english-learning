# Issue #7 - Persistence Foundations, Migrations, Tests, and CI

- Date started: 2026-09-01
- Status: In progress
- Outcome: Create dependable database and verification foundations before domain implementation

## Scope boundary

This ticket adds explicit SQLAlchemy session and transaction ownership, Alembic with a reversible
baseline, PostgreSQL integration-test patterns, a stable API error envelope, and independent backend
CI checks. Production domain tables, authentication, and frontend cutover remain out of scope.

## Implementation order

1. Define and test session/transaction ownership.
2. Configure Alembic and verify upgrade, downgrade, and re-upgrade against PostgreSQL.
3. Define the common safe API error envelope.
4. Add independent backend CI checks and document the complete verification path.

This order establishes resource ownership before migrations depend on it and keeps each failure
boundary independently testable.

## Session and transaction boundary

- FastAPI lifespan creates one application-scoped `sessionmaker` bound to the existing lazy engine.
- `database_transaction()` creates one short-lived session for one unit of work.
- The context manager owns the transaction: it commits after successful caller completion, rolls
  back when caller work or commit fails, re-raises the original exception, and always closes the
  session.
- Callers must not commit, roll back, or close the yielded session. Later service functions will
  express database operations while this boundary retains transaction ownership.
- `autoflush=False` avoids query-triggered writes at surprising points. Explicit `flush()` remains
  available when a service needs database-generated values before commit.
- `expire_on_commit=False` keeps already-loaded values usable after commit without an implicit
  refresh, which is useful when mapping results to response models after the unit of work ends.

### Verification - 2026-09-01

- Unit tests verify factory options and the exact success, caller-failure, and commit-failure paths.
- The FastAPI lifespan test verifies that the application stores the factory created from its own
  engine and still disposes the engine during shutdown.
- `uv run pytest tests/unit -q`: 23 passed with the existing upstream `TestClient` warning.
- `RUN_POSTGRES_INTEGRATION_TESTS=1 uv run pytest -q`: all 25 existing tests passed against the
  Compose PostgreSQL service with the same warning.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed; ten files were already formatted.
- Real PostgreSQL transaction behavior remains intentionally unclaimed until the Alembic/integration
  slice supplies a migrated database target.

## Next step

Add Alembic as a direct runtime/deployment dependency, configure it to obtain the secret database URL
through the existing settings boundary, create an empty reversible baseline migration, and test
`upgrade -> downgrade -> upgrade` against the Compose PostgreSQL service.
