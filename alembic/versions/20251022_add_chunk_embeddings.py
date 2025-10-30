"""Add pgvector backed embeddings to document chunks."""
from __future__ import annotations

import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "20251022_add_chunk_embeddings"
down_revision: Union[str, None] = "20251021_add_user_flags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_MODEL = "qwen3-embedding:0.6b"
MODEL_DIMENSIONS = {
    "qwen3-embedding:0.6b": 1024,
    "qwen3-embedding:4b": 2560,
    "qwen4-embedding:4b": 2560,
}


def _resolve_embedding_dimension() -> int:
    """Resolve the target pgvector dimension based on environment configuration."""

    override = os.getenv("EMBEDDING_DIMENSION")
    if override:
        try:
            value = int(override)
            if value > 0:
                return value
        except ValueError:
            pass
    model_name = (
        os.getenv("LLM__EMBEDDING_MODEL")
        or os.getenv("LLM_EMBEDDING_MODEL")
        or os.getenv("EMBEDDING_MODEL")
        or DEFAULT_MODEL
    )
    key = model_name.lower()
    if key in MODEL_DIMENSIONS:
        return MODEL_DIMENSIONS[key]
    for candidate, dimension in MODEL_DIMENSIONS.items():
        if key.startswith(candidate):
            return dimension
    return MODEL_DIMENSIONS[DEFAULT_MODEL]


def upgrade() -> None:
    """Create the pgvector extension and store embeddings on chunks."""

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("chunks", sa.Column("metadata_json", sa.JSON(), nullable=True))
    op.add_column("chunks", sa.Column("embedding", Vector(_resolve_embedding_dimension()), nullable=True))


def downgrade() -> None:
    """Remove the chunk embedding column."""

    op.drop_column("chunks", "embedding")
    op.drop_column("chunks", "metadata_json")
