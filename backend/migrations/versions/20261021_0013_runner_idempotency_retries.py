"""Persist request idempotency and runner retry state."""

import sqlalchemy as sa
from alembic import op

revision = "20261021_0013"
down_revision = "20261016_0012"
branch_labels = None
depends_on = None


def _id(name: str, **kwargs) -> sa.Column:
    return sa.Column(
        name,
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        **kwargs,
    )


def upgrade() -> None:
    op.add_column("submissions", sa.Column("failure_code", sa.String(32)))
    op.add_column(
        "submission_case_results",
        sa.Column(
            "dispatch_attempt_count", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "submission_case_results",
        sa.Column(
            "poll_failure_count", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "submission_case_results", sa.Column("next_attempt_at", sa.DateTime())
    )
    op.create_table(
        "submission_idempotency_keys",
        _id("user_id", primary_key=True),
        sa.Column("operation", sa.String(32), primary_key=True),
        sa.Column("key_hash", sa.BINARY(32), primary_key=True),
        sa.Column("request_fingerprint", sa.BINARY(32), nullable=False),
        _id("submission_id", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["submission_id"], ["submissions.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("submission_id", name="uq_idempotency_submission"),
    )
    op.create_index(
        "ix_submission_idempotency_expires_at",
        "submission_idempotency_keys",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_submission_idempotency_expires_at",
        table_name="submission_idempotency_keys",
    )
    op.drop_table("submission_idempotency_keys")
    op.drop_column("submission_case_results", "next_attempt_at")
    op.drop_column("submission_case_results", "poll_failure_count")
    op.drop_column("submission_case_results", "dispatch_attempt_count")
    op.drop_column("submissions", "failure_code")
