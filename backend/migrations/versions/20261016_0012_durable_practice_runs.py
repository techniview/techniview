"""Store public Run jobs in the durable execution queue."""

import sqlalchemy as sa
from alembic import op

revision = "20261016_0012"
down_revision = "20261015_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "submissions",
        sa.Column(
            "is_practice_run",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("submissions", "is_practice_run")
