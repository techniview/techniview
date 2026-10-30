"""Preserve microseconds in submission event timestamps."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "20261025_0014"
down_revision = "20261021_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "mysql":
        return
    op.alter_column(
        "submissions",
        "submitted_at",
        existing_type=sa.DateTime(),
        type_=mysql.DATETIME(fsp=6),
        existing_nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP(6)"),
    )
    op.alter_column(
        "submissions",
        "completed_at",
        existing_type=sa.DateTime(),
        type_=mysql.DATETIME(fsp=6),
        existing_nullable=True,
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "mysql":
        return
    op.alter_column(
        "submissions",
        "submitted_at",
        existing_type=mysql.DATETIME(fsp=6),
        type_=sa.DateTime(),
        existing_nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )
    op.alter_column(
        "submissions",
        "completed_at",
        existing_type=mysql.DATETIME(fsp=6),
        type_=sa.DateTime(),
        existing_nullable=True,
    )
