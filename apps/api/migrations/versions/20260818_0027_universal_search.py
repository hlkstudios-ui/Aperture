"""Add trigram indexes for typo-tolerant universal search.

Revision ID: 20260818_0027
Revises: 20260818_0026
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260818_0027"
down_revision: str | Sequence[str] | None = "20260818_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for table, column in (
        ("movies", "title"),
        ("movies", "original_title"),
        ("series", "title"),
        ("series", "original_title"),
        ("people", "name"),
        ("companies", "name"),
        ("characters", "name"),
    ):
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_{column}_trgm "
            f"ON {table} USING gin ({column} gin_trgm_ops)"
        )


def downgrade() -> None:
    for table, column in (
        ("characters", "name"),
        ("companies", "name"),
        ("people", "name"),
        ("series", "original_title"),
        ("series", "title"),
        ("movies", "original_title"),
        ("movies", "title"),
    ):
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_{column}_trgm")
