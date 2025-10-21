"""Add missing FastAPI Users boolean columns.

Revision ID: 20251021_add_user_flags
Revises: 0bad8afe5ae1
Create Date: 2025-10-21 13:20:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20251021_add_user_flags"
down_revision: Union[str, None] = "0bad8afe5ae1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the missing FastAPI Users columns to the users table."""

    op.add_column(
        "users",
        sa.Column(
            "is_superuser",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "is_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Remove the server defaults to keep ORM state aligned with the model.
    op.alter_column("users", "is_superuser", server_default=None)
    op.alter_column("users", "is_verified", server_default=None)


def downgrade() -> None:
    """Drop the FastAPI Users columns."""

    op.drop_column("users", "is_verified")
    op.drop_column("users", "is_superuser")

