"""Store retrieved context and citations on messages."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251028_message_citations"
down_revision = "20251025_role_categories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("context_json", sa.JSON(), nullable=True))
    op.add_column("messages", sa.Column("citations_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "citations_json")
    op.drop_column("messages", "context_json")