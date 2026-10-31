"""Record when a submission first starts runner execution."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "20261030_0016"
down_revision = "20261028_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "submissions",
        sa.Column(
            "started_at",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"),
            nullable=True,
        ),
    )
    op.execute(
        sa.text(
            "UPDATE submissions SET started_at = ("
            "SELECT MIN(dispatch_started_at) FROM submission_case_results "
            "WHERE submission_case_results.submission_id = submissions.id) "
            "WHERE started_at IS NULL AND EXISTS ("
            "SELECT 1 FROM submission_case_results "
            "WHERE submission_case_results.submission_id = submissions.id "
            "AND dispatch_started_at IS NOT NULL)"
        )
    )
    op.create_index("idx_submissions_completed_at", "submissions", ["completed_at"])


def downgrade() -> None:
    op.drop_index("idx_submissions_completed_at", table_name="submissions")
    op.drop_column("submissions", "started_at")
