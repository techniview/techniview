"""Add per-class join code hash."""

import sqlalchemy as sa
from alembic import op

revision = "20260924_0003"
down_revision = "20260922_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "courses",
        sa.Column("join_code_hash", sa.BINARY(32), nullable=True),
    )
    op.create_index(
        "ix_courses_join_code_hash",
        "courses",
        ["join_code_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_courses_join_code_hash", table_name="courses")
    op.drop_column("courses", "join_code_hash")
