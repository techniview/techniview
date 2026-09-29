"""Track late submissions and instructor late approval."""

import sqlalchemy as sa
from alembic import op

revision = "20260924_0004"
down_revision = "20260924_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "submissions",
        sa.Column("is_late", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "submissions",
        sa.Column("late_approved_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "submissions",
        sa.Column(
            "late_approved_by_membership_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("submissions", "late_approved_by_membership_id")
    op.drop_column("submissions", "late_approved_at")
    op.drop_column("submissions", "is_late")
