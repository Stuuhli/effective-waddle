"""Add chunk configuration columns to ingestion jobs."""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20251023_ingest_chunk_cfg"
down_revision: Union[str, None] = "20251022_add_chunk_embeddings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Introduce chunk size, overlap and metadata for ingestion jobs."""

    op.add_column(
        "ingestion_jobs",
        sa.Column("chunk_size", sa.Integer(), nullable=False, server_default="750"),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("chunk_overlap", sa.Integer(), nullable=False, server_default="150"),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("parameters", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    """Revert ingestion job chunk configuration columns."""

    op.drop_column("ingestion_jobs", "parameters")
    op.drop_column("ingestion_jobs", "chunk_overlap")
    op.drop_column("ingestion_jobs", "chunk_size")
