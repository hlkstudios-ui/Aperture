"""Create foundation system records table."""

import sqlalchemy as sa
from alembic import op

revision = "20260815_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_system_records_key", "system_records", ["key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_system_records_key", table_name="system_records")
    op.drop_table("system_records")
