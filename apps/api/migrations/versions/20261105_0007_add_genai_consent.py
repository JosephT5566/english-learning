"""Default all users to no GenAI consent.

Revision ID: 20261105_0007
Revises: 20260920_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261105_0007"
down_revision: str | Sequence[str] | None = "20260920_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("genai_consent_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("users", "genai_consent_at")
