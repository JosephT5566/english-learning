from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import (
    DEFAULT_CORS_ALLOWED_ORIGINS,
    DEFAULT_DATABASE_URL,
    AppEnvironment,
    ConfigurationError,
    LogLevel,
    load_settings,
)
from app.main import create_app

CONFIG_ENVIRONMENT_VARIABLES = (
    "APP_ENV",
    "LOG_LEVEL",
    "DATABASE_URL",
    "DATABASE_CONNECT_TIMEOUT_SECONDS",
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_ALLOWED_EMAILS",
    "CORS_ALLOWED_ORIGINS",
)


@pytest.fixture(autouse=True)
def isolate_configuration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for variable_name in CONFIG_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable_name, raising=False)
    monkeypatch.chdir(tmp_path)


def test_load_settings_uses_safe_local_defaults() -> None:
    settings = load_settings()

    assert settings.app_env is AppEnvironment.LOCAL
    assert settings.log_level is LogLevel.INFO
    assert settings.database_url.get_secret_value() == DEFAULT_DATABASE_URL
    assert settings.database_connect_timeout_seconds == 2
    assert settings.cors_allowed_origins == DEFAULT_CORS_ALLOWED_ORIGINS
    assert DEFAULT_DATABASE_URL not in repr(settings)
    assert DEFAULT_DATABASE_URL not in str(settings)


def test_environment_variables_override_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = (
        "postgresql+psycopg://api_user:test_password@db.example:5432/test_database"
    )
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("DATABASE_CONNECT_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        '["https://app.example.com","http://localhost:4173"]',
    )

    settings = load_settings()

    assert settings.app_env is AppEnvironment.TEST
    assert settings.log_level is LogLevel.DEBUG
    assert settings.database_url.get_secret_value() == database_url
    assert settings.database_connect_timeout_seconds == 5
    assert settings.cors_allowed_origins == (
        "https://app.example.com",
        "http://localhost:4173",
    )


def test_production_accepts_explicit_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = (
        "postgresql+psycopg://api_user:production_password@db.example:5432/app"
        "?sslmode=verify-full"
    )
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "production-client-id")
    monkeypatch.setenv("GOOGLE_ALLOWED_EMAILS", "user@example.test")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["https://app.example.com"]')

    settings = load_settings()

    assert settings.app_env is AppEnvironment.PRODUCTION
    assert settings.database_url.get_secret_value() == database_url


def test_production_accepts_required_tls_channel_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = (
        "postgresql+psycopg://api_user:production_password@db.example:5432/app"
        "?sslmode=require&channel_binding=require"
    )
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "production-client-id")
    monkeypatch.setenv("GOOGLE_ALLOWED_EMAILS", "user@example.test")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["https://app.example.com"]')

    settings = load_settings()

    assert settings.database_url.get_secret_value() == database_url


@pytest.mark.parametrize(
    "query",
    [
        "",
        "?sslmode=disable",
        "?sslmode=prefer",
        "?sslmode=require",
        "?channel_binding=require",
    ],
)
def test_production_rejects_database_url_without_secure_transport(
    monkeypatch: pytest.MonkeyPatch, query: str
) -> None:
    fake_password = "RECOGNIZABLE_FAKE_PASSWORD"
    database_url = (
        f"postgresql+psycopg://api_user:{fake_password}@db.example:5432/app{query}"
    )
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "production-client-id")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["https://app.example.com"]')

    with pytest.raises(ConfigurationError) as captured_error:
        load_settings()

    message = str(captured_error.value)
    assert "DATABASE_URL" in message
    assert fake_password not in message
    assert database_url not in message


def test_production_rejects_disposable_local_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(ConfigurationError) as captured_error:
        load_settings()

    message = str(captured_error.value)
    assert "DATABASE_URL" in message
    assert DEFAULT_DATABASE_URL not in message


def test_production_requires_explicit_google_oauth_client_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://api_user:password@db.example:5432/app?sslmode=verify-full",
    )

    with pytest.raises(ConfigurationError, match="GOOGLE_OAUTH_CLIENT_ID"):
        load_settings()


def test_production_requires_explicit_cors_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://api_user:password@db.example:5432/app?sslmode=verify-full",
    )
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "production-client-id")
    monkeypatch.setenv("GOOGLE_ALLOWED_EMAILS", "user@example.test")

    with pytest.raises(ConfigurationError, match="CORS_ALLOWED_ORIGINS"):
        load_settings()


def test_google_oauth_client_id_must_not_be_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "   ")

    with pytest.raises(ConfigurationError, match="GOOGLE_OAUTH_CLIENT_ID"):
        load_settings()


def test_production_requires_google_email_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://api_user:password@db.example:5432/app?sslmode=verify-full",
    )
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "production-client-id")

    with pytest.raises(ConfigurationError, match="GOOGLE_ALLOWED_EMAILS"):
        load_settings()


def test_google_email_allowlist_normalizes_and_rejects_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "GOOGLE_ALLOWED_EMAILS", " User@Example.test , second@example.test "
    )
    assert (
        load_settings().google_allowed_emails == "user@example.test,second@example.test"
    )

    monkeypatch.setenv("GOOGLE_ALLOWED_EMAILS", "USER@example.test,user@example.test")
    with pytest.raises(ConfigurationError, match="GOOGLE_ALLOWED_EMAILS"):
        load_settings()


@pytest.mark.parametrize(
    "origins",
    [
        "[]",
        '["*"]',
        '["https://app.example.com/path"]',
        '["https://user:password@app.example.com"]',
        '["https://app.example.com","https://app.example.com/"]',
    ],
)
def test_cors_origins_must_be_nonempty_unique_exact_origins(
    monkeypatch: pytest.MonkeyPatch, origins: str
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", origins)

    with pytest.raises(ConfigurationError, match="CORS_ALLOWED_ORIGINS"):
        load_settings()


@pytest.mark.parametrize(
    ("variable_name", "invalid_value"),
    [("APP_ENV", "staging"), ("LOG_LEVEL", "TRACE")],
)
def test_invalid_enum_does_not_expose_other_secrets(
    monkeypatch: pytest.MonkeyPatch,
    variable_name: str,
    invalid_value: str,
) -> None:
    fake_password = "RECOGNIZABLE_FAKE_PASSWORD"
    database_url = (
        f"postgresql+psycopg://api_user:{fake_password}@localhost:5432/test_database"
    )
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv(variable_name, invalid_value)

    with pytest.raises(ConfigurationError) as captured_error:
        load_settings()

    message = str(captured_error.value)
    assert variable_name in message
    assert fake_password not in message
    assert database_url not in message


@pytest.mark.parametrize("timeout", ["0", "11"])
def test_database_connect_timeout_is_positive_and_bounded(
    monkeypatch: pytest.MonkeyPatch, timeout: str
) -> None:
    monkeypatch.setenv("DATABASE_CONNECT_TIMEOUT_SECONDS", timeout)

    with pytest.raises(ConfigurationError, match="DATABASE_CONNECT_TIMEOUT_SECONDS"):
        load_settings()


def test_invalid_database_url_does_not_expose_fake_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_password = "RECOGNIZABLE_FAKE_PASSWORD"
    database_url = f"postgresql+wrong_driver://api_user:{fake_password}@localhost:5432/test_database"
    monkeypatch.setenv("DATABASE_URL", database_url)

    with pytest.raises(ConfigurationError) as captured_error:
        load_settings()

    message = str(captured_error.value)
    assert "DATABASE_URL" in message
    assert fake_password not in message
    assert database_url not in message


def test_settings_load_during_lifespan_not_app_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")

    app = create_app()

    with pytest.raises(ConfigurationError, match="DATABASE_URL"), TestClient(app):
        pass
