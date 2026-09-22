"""Persist complete Judge0 reports and callback credentials."""

import sqlalchemy as sa
from alembic import op

revision = "20260922_0002"
down_revision = "20260921_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "submission_case_results",
        sa.Column("callback_token_hash", sa.BINARY(32), nullable=True),
    )
    op.add_column(
        "submission_case_results",
        sa.Column("execution_time_ms", sa.Numeric(12, 3), nullable=True),
    )
    op.add_column(
        "submission_case_results",
        sa.Column("memory_kb", sa.Integer(), nullable=True),
    )
    op.add_column(
        "submission_case_results",
        sa.Column("stdout", sa.Text(), nullable=True),
    )
    op.add_column(
        "submission_case_results",
        sa.Column("stderr", sa.Text(), nullable=True),
    )
    op.add_column(
        "submission_case_results",
        sa.Column("compile_output", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_submission_case_results_callback_token_hash",
        "submission_case_results",
        ["callback_token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_submission_case_results_callback_token_hash",
        table_name="submission_case_results",
    )
    op.drop_column("submission_case_results", "compile_output")
    op.drop_column("submission_case_results", "stderr")
    op.drop_column("submission_case_results", "stdout")
    op.drop_column("submission_case_results", "memory_kb")
    op.drop_column("submission_case_results", "execution_time_ms")
    op.drop_column("submission_case_results", "callback_token_hash")
