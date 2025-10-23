"""Split roles into permission and workspace categories."""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251025_role_categories"
down_revision = "20251024_collections_events"
branch_labels = None
depends_on = None

role_category = sa.Enum("permission", "workspace", name="role_category")


def upgrade() -> None:
    bind = op.get_bind()
    role_category.create(bind, checkfirst=True)
    op.add_column(
        "roles",
        sa.Column(
            "category",
            role_category,
            nullable=False,
            server_default="workspace",
        ),
    )
    op.execute(
        "UPDATE roles SET category='permission' WHERE name IN ('user','admin','rag','graphrag')"
    )


def downgrade() -> None:
    op.drop_column("roles", "category")
    bind = op.get_bind()
    role_category.drop(bind, checkfirst=True)
