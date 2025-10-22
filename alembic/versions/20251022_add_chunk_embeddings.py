"""Add pgvector backed embeddings to document chunks."""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "20251022_add_chunk_embeddings"
down_revision: Union[str, None] = "20251021_add_user_flags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the pgvector extension and store embeddings on chunks."""

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("chunks", sa.Column("metadata_json", sa.JSON(), nullable=True))
    op.add_column("chunks", sa.Column("embedding", Vector(1536), nullable=True))


def downgrade() -> None:
    """Remove the chunk embedding column."""

    op.drop_column("chunks", "embedding")
    op.drop_column("chunks", "metadata_json")
