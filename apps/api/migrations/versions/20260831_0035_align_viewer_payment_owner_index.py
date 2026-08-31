"""Align the viewer-payment owner key with the ORM's unique-index contract.

Revision ID: 20260831_0035
Revises: 20260831_0034
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260831_0035"
down_revision: str | Sequence[str] | None = "20260831_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "viewer_payment_connections_owner_admin_id_key",
        "viewer_payment_connections",
        type_="unique",
    )
    op.drop_index(
        "ix_viewer_payment_connections_owner_admin_id",
        table_name="viewer_payment_connections",
    )
    op.create_index(
        "ix_viewer_payment_connections_owner_admin_id",
        "viewer_payment_connections",
        ["owner_admin_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_viewer_payment_connections_owner_admin_id",
        table_name="viewer_payment_connections",
    )
    op.create_index(
        "ix_viewer_payment_connections_owner_admin_id",
        "viewer_payment_connections",
        ["owner_admin_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "viewer_payment_connections_owner_admin_id_key",
        "viewer_payment_connections",
        ["owner_admin_id"],
    )
