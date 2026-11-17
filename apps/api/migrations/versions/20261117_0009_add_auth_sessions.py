"""Add hash-only header sessions outside product RLS.

Revision ID: 20261117_0009
Revises: 20261105_0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261117_0009"
down_revision: str | Sequence[str] | None = "20261105_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Runtime DML grants inherit the migration role's existing default privileges.
    op.create_table(
        "auth_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("principal_kind", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_reason", sa.Text()),
        sa.CheckConstraint(
            "principal_kind IN ('human', 'smoke')", name="ck_auth_sessions_kind"
        ),
        sa.CheckConstraint(
            "revoked_reason IN ('logout', 'reuse', 'allowlist', 'operator', 'switch')",
            name="ck_auth_sessions_reason",
        ),
        sa.CheckConstraint(
            "(revoked_at IS NULL) = (revoked_reason IS NULL)",
            name="ck_auth_sessions_revocation",
        ),
        sa.CheckConstraint(
            "created_at <= last_refreshed_at AND last_refreshed_at < idle_expires_at AND idle_expires_at <= absolute_expires_at",
            name="ck_auth_sessions_expiry",
        ),
    )
    op.create_index("ix_auth_sessions_user", "auth_sessions", ["user_id"])
    op.create_table(
        "auth_refresh_tokens",
        sa.Column("token_hash", sa.LargeBinary(), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("auth_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32", name="ck_auth_refresh_hash"
        ),
        sa.CheckConstraint(
            "rotated_at IS NULL OR rotated_at >= issued_at",
            name="ck_auth_refresh_rotation",
        ),
    )
    op.create_index(
        "uq_auth_refresh_current",
        "auth_refresh_tokens",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text("rotated_at IS NULL"),
    )
    op.create_index("ix_auth_refresh_session", "auth_refresh_tokens", ["session_id"])
    op.create_table(
        "auth_access_tokens",
        sa.Column("token_hash", sa.LargeBinary(), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("auth_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("octet_length(token_hash) = 32", name="ck_auth_access_hash"),
    )
    op.create_index("ix_auth_access_expires", "auth_access_tokens", ["expires_at"])
    op.create_index("ix_auth_access_session", "auth_access_tokens", ["session_id"])


def downgrade() -> None:
    op.drop_table("auth_access_tokens")
    op.drop_table("auth_refresh_tokens")
    op.drop_table("auth_sessions")
