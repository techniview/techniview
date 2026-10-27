"""Record cases left unrun after a shared interpreter terminates."""

import sqlalchemy as sa
from alembic import op

revision = "20261027_0015"
down_revision = "20261025_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "submission_case_results",
        sa.Column(
            "execution_unrun", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    op.drop_column("submission_case_results", "execution_unrun")
