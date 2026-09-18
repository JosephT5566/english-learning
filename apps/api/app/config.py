"""Typed, secret-safe application configuration."""

from enum import StrEnum
from typing import Annotated

from pydantic import (
    Field,
    SecretStr,
    StringConstraints,
    ValidationError,
    field_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.exceptions import SettingsError
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://"
    "english_learning:english_learning@localhost:5432/english_learning"
)
DEFAULT_GOOGLE_OAUTH_CLIENT_ID = "local-development-client-id"
DEFAULT_CORS_ALLOWED_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)
SECURE_DATABASE_SSL_MODES = frozenset({"verify-ca", "verify-full"})


class AppEnvironment(StrEnum):
    """Supported deployment environments."""

    LOCAL = "local"
    TEST = "test"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    """Supported application logging levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ConfigurationError(RuntimeError):
    """Safe configuration failure suitable for startup output."""


class Settings(BaseSettings):
    """Validated settings loaded from environment variables and an optional `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        validate_default=True,
    )

    app_env: AppEnvironment = AppEnvironment.LOCAL
    log_level: LogLevel = LogLevel.INFO
    database_url: SecretStr = SecretStr(DEFAULT_DATABASE_URL)
    database_connect_timeout_seconds: Annotated[int, Field(gt=0, le=10)] = 2
    google_oauth_client_id: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1)
    ] = DEFAULT_GOOGLE_OAUTH_CLIENT_ID
    google_allowed_emails: str = ""
    cors_allowed_origins: Annotated[tuple[str, ...], Field(min_length=1)] = (
        DEFAULT_CORS_ALLOWED_ORIGINS
    )

    @field_validator("google_allowed_emails")
    @classmethod
    def normalize_allowed_emails(cls, value: str) -> str:
        emails = [email.strip().casefold() for email in value.split(",")]
        if value and (
            any(
                not email or "@" not in email or any(char.isspace() for char in email)
                for email in emails
            )
            or len(emails) != len(set(emails))
        ):
            raise ValueError("must contain unique comma-separated email addresses")
        return ",".join(emails) if value else ""

    @field_validator("cors_allowed_origins")
    @classmethod
    def require_explicit_http_origins(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Accept only exact HTTP(S) origins without paths or wildcards."""

        from urllib.parse import urlsplit

        normalized: list[str] = []
        for candidate in value:
            origin = candidate.strip().rstrip("/")
            parsed = urlsplit(origin)
            if (
                origin == "*"
                or parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("must contain only exact HTTP(S) origins")
            try:
                _ = parsed.port
            except ValueError:
                raise ValueError("must contain only exact HTTP(S) origins") from None
            normalized.append(origin)

        if len(normalized) != len(set(normalized)):
            raise ValueError("must not contain duplicate origins")
        return tuple(normalized)

    @field_validator("database_url")
    @classmethod
    def require_psycopg_database_url(cls, value: SecretStr) -> SecretStr:
        """Require a valid SQLAlchemy URL that selects the Psycopg driver."""

        try:
            parsed_url = make_url(value.get_secret_value())
        except ArgumentError:
            raise ValueError("must be a valid SQLAlchemy database URL") from None

        if parsed_url.drivername != "postgresql+psycopg":
            raise ValueError("must use the postgresql+psycopg driver")

        return value


def _invalid_environment_names(error: ValidationError) -> list[str]:
    """Extract safe environment-variable names without rejected input values."""

    names = {
        str(detail["loc"][0]).upper()
        for detail in error.errors(
            include_context=False,
            include_input=False,
            include_url=False,
        )
        if detail["loc"]
    }
    return sorted(names)


def load_settings() -> Settings:
    """Load validated application settings through a sanitized failure boundary.

    Returns:
        Frozen settings safe to share for the application lifespan.

    Raises:
        ConfigurationError: If a source or value is invalid, or production uses
            the disposable local database URL.
    """

    try:
        settings = Settings()
    except ValidationError as error:
        names = _invalid_environment_names(error)
        fields = ", ".join(names) if names else "unknown setting"
        raise ConfigurationError(
            f"Invalid configuration for {fields}; check its type and allowed value."
        ) from None
    except SettingsError:
        raise ConfigurationError("Invalid application configuration source.") from None

    if (
        settings.app_env is AppEnvironment.PRODUCTION
        and settings.database_url.get_secret_value() == DEFAULT_DATABASE_URL
    ):
        raise ConfigurationError(
            "Invalid configuration for DATABASE_URL; production requires an explicit value."
        )

    if settings.app_env is AppEnvironment.PRODUCTION:
        database_url = make_url(settings.database_url.get_secret_value())
        sslmode = database_url.query.get("sslmode")
        channel_binding = database_url.query.get("channel_binding")
        secure_transport = sslmode in SECURE_DATABASE_SSL_MODES or (
            sslmode == "require" and channel_binding == "require"
        )
        if not secure_transport:
            raise ConfigurationError(
                "Invalid configuration for DATABASE_URL; production requires "
                "verified TLS or required TLS channel binding."
            )

    if (
        settings.app_env is AppEnvironment.PRODUCTION
        and settings.google_oauth_client_id == DEFAULT_GOOGLE_OAUTH_CLIENT_ID
    ):
        raise ConfigurationError(
            "Invalid configuration for GOOGLE_OAUTH_CLIENT_ID; production requires an explicit value."
        )

    if (
        settings.app_env is AppEnvironment.PRODUCTION
        and not settings.google_allowed_emails
    ):
        raise ConfigurationError(
            "Invalid configuration for GOOGLE_ALLOWED_EMAILS; production requires an explicit allowlist."
        )

    if (
        settings.app_env is AppEnvironment.PRODUCTION
        and settings.cors_allowed_origins == DEFAULT_CORS_ALLOWED_ORIGINS
    ):
        raise ConfigurationError(
            "Invalid configuration for CORS_ALLOWED_ORIGINS; production requires an explicit value."
        )

    return settings
