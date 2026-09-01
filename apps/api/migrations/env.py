"""Alembic environment using the API's validated database configuration."""

from logging.config import fileConfig

from alembic import context

from app.config import load_settings
from app.database import create_database_engine, dispose_database_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Issue #7 establishes only the migration mechanism. Domain metadata is added
# when the production schema is implemented.
target_metadata = None


def run_migrations_offline() -> None:
    """Generate SQL without opening a database connection."""

    settings = load_settings()
    context.configure(
        url=settings.database_url.get_secret_value(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations through the API's configured SQLAlchemy engine."""

    engine = create_database_engine(load_settings())
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        dispose_database_engine(engine)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
