"""Add explicit licensed distribution territories to catalog titles."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7e4c91d2a60"
down_revision: str | Sequence[str] | None = "91f3a6c2d8b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("movies", "series", "editions"):
        op.add_column(
            table,
            sa.Column(
                "allowed_territories",
                postgresql.JSONB(astext_type=sa.Text()),
                server_default=sa.text("'[]'::jsonb"),
                nullable=False,
            ),
        )
        op.create_check_constraint(
            f"ck_{table}_allowed_territories_array",
            table,
            "jsonb_typeof(allowed_territories) = 'array'",
        )
        op.create_index(
            f"ix_{table}_allowed_territories",
            table,
            ["allowed_territories"],
            postgresql_using="gin",
        )


def downgrade() -> None:
    for table in reversed(("movies", "series", "editions")):
        op.drop_index(f"ix_{table}_allowed_territories", table_name=table)
        op.drop_constraint(
            f"ck_{table}_allowed_territories_array", table, type_="check"
        )
        op.drop_column(table, "allowed_territories")
