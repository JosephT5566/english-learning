from unittest.mock import MagicMock, Mock

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

import app.database as database_module
import app.main as main_module
from app.config import Settings


def make_settings() -> Settings:
    return Settings.model_validate(
        {
            "app_env": "test",
            "database_url": (
                "postgresql+psycopg://api_user:test_password@db.example:5432/app"
            ),
            "database_connect_timeout_seconds": 7,
        }
    )


def test_create_database_engine_applies_connection_options(
    monkeypatch: MonkeyPatch,
) -> None:
    settings = make_settings()
    expected_engine = Mock(spec=Engine)
    captured_arguments: dict[str, object] = {}

    def fake_create_engine(url: str, **options: object) -> Engine:
        captured_arguments["url"] = url
        captured_arguments["options"] = options
        return expected_engine

    monkeypatch.setattr(database_module, "create_engine", fake_create_engine)

    engine = database_module.create_database_engine(settings)

    assert engine is expected_engine
    assert captured_arguments == {
        "url": settings.database_url.get_secret_value(),
        "options": {
            "connect_args": {"connect_timeout": 7},
            "pool_pre_ping": True,
        },
    }


def test_dispose_database_engine_closes_pool() -> None:
    engine = Mock(spec=Engine)

    database_module.dispose_database_engine(engine)

    engine.dispose.assert_called_once_with()


def test_create_database_session_factory_applies_session_options(
    monkeypatch: MonkeyPatch,
) -> None:
    engine = Mock(spec=Engine)
    expected_factory = Mock(spec=sessionmaker)
    captured_arguments: dict[str, object] = {}

    def fake_sessionmaker(**options: object) -> sessionmaker[Session]:
        captured_arguments.update(options)
        return expected_factory

    monkeypatch.setattr(database_module, "sessionmaker", fake_sessionmaker)

    factory = database_module.create_database_session_factory(engine)

    assert factory is expected_factory
    assert captured_arguments == {
        "bind": engine,
        "autoflush": False,
        "expire_on_commit": False,
    }


def test_database_transaction_commits_and_closes_on_success() -> None:
    session = Mock(spec=Session)
    session_factory = Mock(return_value=session)

    with database_module.database_transaction(session_factory) as yielded_session:
        assert yielded_session is session

    session.commit.assert_called_once_with()
    session.rollback.assert_not_called()
    session.close.assert_called_once_with()


def test_database_transaction_rolls_back_and_closes_on_failure() -> None:
    session = Mock(spec=Session)
    session_factory = Mock(return_value=session)

    with (
        pytest.raises(RuntimeError, match="operation failed"),
        database_module.database_transaction(session_factory),
    ):
        raise RuntimeError("operation failed")

    session.commit.assert_not_called()
    session.rollback.assert_called_once_with()
    session.close.assert_called_once_with()


def test_database_transaction_rolls_back_and_closes_when_commit_fails() -> None:
    session = Mock(spec=Session)
    session.commit.side_effect = SQLAlchemyError("commit failed")
    session_factory = Mock(return_value=session)

    with (
        pytest.raises(SQLAlchemyError, match="commit failed"),
        database_module.database_transaction(session_factory),
    ):
        pass

    session.commit.assert_called_once_with()
    session.rollback.assert_called_once_with()
    session.close.assert_called_once_with()


def test_check_database_readiness_executes_select_one() -> None:
    engine = MagicMock(spec=Engine)
    connection = engine.connect.return_value.__enter__.return_value

    is_ready = database_module.check_database_readiness(engine)

    assert is_ready is True
    connection.execute.assert_called_once()
    statement = connection.execute.call_args.args[0]
    assert str(statement) == "SELECT 1"


def test_check_database_readiness_handles_database_failure() -> None:
    engine = MagicMock(spec=Engine)
    engine.connect.side_effect = SQLAlchemyError("database unavailable")

    is_ready = database_module.check_database_readiness(engine)

    assert is_ready is False


def test_database_engine_lifecycle_uses_fastapi_lifespan(
    monkeypatch: MonkeyPatch,
) -> None:
    settings = make_settings()
    engine = Mock(spec=Engine)
    session_factory = Mock(spec=sessionmaker)
    lifecycle_events: list[tuple[str, object]] = []

    def fake_load_settings() -> Settings:
        lifecycle_events.append(("settings_loaded", settings))
        return settings

    def fake_create_database_engine(loaded_settings: Settings) -> Engine:
        lifecycle_events.append(("engine_created", loaded_settings))
        return engine

    def fake_create_database_session_factory(
        created_engine: Engine,
    ) -> sessionmaker[Session]:
        lifecycle_events.append(("session_factory_created", created_engine))
        return session_factory

    def fake_dispose_database_engine(created_engine: Engine) -> None:
        lifecycle_events.append(("engine_disposed", created_engine))

    monkeypatch.setattr(main_module, "load_settings", fake_load_settings)
    monkeypatch.setattr(
        main_module,
        "create_database_engine",
        fake_create_database_engine,
    )
    monkeypatch.setattr(
        main_module,
        "dispose_database_engine",
        fake_dispose_database_engine,
    )
    monkeypatch.setattr(
        main_module,
        "create_database_session_factory",
        fake_create_database_session_factory,
    )

    app = main_module.create_app()

    assert lifecycle_events == []

    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        assert app.state.settings is settings
        assert app.state.database_engine is engine
        assert app.state.database_session_factory is session_factory
        assert lifecycle_events == [
            ("settings_loaded", settings),
            ("engine_created", settings),
            ("session_factory_created", engine),
        ]

    assert lifecycle_events == [
        ("settings_loaded", settings),
        ("engine_created", settings),
        ("session_factory_created", engine),
        ("engine_disposed", engine),
    ]
