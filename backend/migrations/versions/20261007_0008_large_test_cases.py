"""Allow APPS+ test cases larger than MySQL's 64 KB TEXT limit."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "20261007_0008"
down_revision = "20261007_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "problem_test_cases",
        "input",
        existing_type=sa.Text(),
        type_=mysql.MEDIUMTEXT(),
        existing_nullable=False,
    )
    op.alter_column(
        "problem_test_cases",
        "expected_output",
        existing_type=sa.Text(),
        type_=mysql.MEDIUMTEXT(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "problem_test_cases",
        "expected_output",
        existing_type=mysql.MEDIUMTEXT(),
        type_=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "problem_test_cases",
        "input",
        existing_type=mysql.MEDIUMTEXT(),
        type_=sa.Text(),
        existing_nullable=False,
    )
