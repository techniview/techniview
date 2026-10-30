"""Store optional model estimates for submission complexity."""

import sqlalchemy as sa
from alembic import op

revision = "20261028_0015"
down_revision = "20261025_0014"
branch_labels = None
depends_on = None


def _id(name: str, **kwargs) -> sa.Column:
    return sa.Column(
        name,
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        **kwargs,
    )


def upgrade() -> None:
    op.create_table(
        "submission_complexity_analyses",
        _id("submission_id", primary_key=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("time_complexity", sa.String(64)),
        sa.Column("space_complexity", sa.String(64)),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(32)),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claimed_at", sa.DateTime()),
        sa.Column("next_attempt_at", sa.DateTime()),
        sa.Column("analyzed_at", sa.DateTime()),
        sa.ForeignKeyConstraint(
            ["submission_id"], ["submissions.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_submission_complexity_queue",
        "submission_complexity_analyses",
        ["status", "next_attempt_at", "claimed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_submission_complexity_queue",
        table_name="submission_complexity_analyses",
    )
    op.drop_table("submission_complexity_analyses")
