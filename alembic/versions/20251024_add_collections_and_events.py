"""Introduce collections, role bindings and ingestion events."""
from __future__ import annotations

import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20251024_add_collections_and_events"
down_revision: Union[str, None] = "20251023_add_ingestion_job_chunk_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COLLECTION_TABLE = "collections"
ROLE_COLLECTION_TABLE = "role_collections"
EVENT_TABLE = "ingestion_events"


def upgrade() -> None:
    """Create collection metadata and ingestion lifecycle events."""

    op.create_table(
        COLLECTION_TABLE,
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        ROLE_COLLECTION_TABLE,
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("role_id", sa.String(), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("collection_id", sa.String(), sa.ForeignKey(f"{COLLECTION_TABLE}.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("role_id", "collection_id", name="uq_role_collection"),
    )

    op.add_column("ingestion_jobs", sa.Column("collection_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_ingestion_jobs_collection_id",
        "ingestion_jobs",
        COLLECTION_TABLE,
        ["collection_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_table(
        EVENT_TABLE,
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("job_id", sa.String(), sa.ForeignKey("ingestion_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.String(), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("document_title", sa.String(length=255), nullable=True),
        sa.Column("document_path", sa.String(length=1024), nullable=True),
        sa.Column("step", sa.Enum("docling_parse", "chunk_assembly", "embedding_indexing", "citation_enrichment", name="ingestion_step"), nullable=False),
        sa.Column("status", sa.Enum("pending", "running", "success", "failed", name="ingestion_event_status"), nullable=False, server_default="pending"),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    bind = op.get_bind()
    compliance_id = str(uuid.uuid4())
    bind.execute(
        sa.text(
            f"INSERT INTO {COLLECTION_TABLE} (id, name, description) VALUES (:id, :name, :description)"
        ),
        {"id": compliance_id, "name": "compliance", "description": "Compliance document collection"},
    )

    bind.execute(sa.text("UPDATE ingestion_jobs SET collection_id = :cid"), {"cid": compliance_id})

    op.alter_column("ingestion_jobs", "collection_id", nullable=False)
    op.drop_column("ingestion_jobs", "collection_name")


def downgrade() -> None:
    """Drop collection metadata and lifecycle events."""

    op.add_column(
        "ingestion_jobs",
        sa.Column("collection_name", sa.String(length=255), nullable=False, server_default="compliance"),
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE ingestion_jobs ij SET collection_name = c.name FROM collections c WHERE ij.collection_id = c.id"
        )
    )

    op.drop_constraint("fk_ingestion_jobs_collection_id", "ingestion_jobs", type_="foreignkey")
    op.drop_column("ingestion_jobs", "collection_id")

    op.drop_table(EVENT_TABLE)
    op.drop_table(ROLE_COLLECTION_TABLE)
    op.drop_table(COLLECTION_TABLE)

    op.execute("DROP TYPE IF EXISTS ingestion_step")
    op.execute("DROP TYPE IF EXISTS ingestion_event_status")
