"""Preserve imported problem categories and typed tags."""

import sqlalchemy as sa
from alembic import op

revision = "20261006_0006"
down_revision = "20260929_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "problem_tags",
        sa.Column(
            "kind",
            sa.Enum(
                "general",
                "technique",
                "problem_type",
                native_enum=False,
                length=12,
            ),
            server_default="general",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_problem_tags_kind",
        "problem_tags",
        "kind IN ('general', 'technique', 'problem_type')",
    )
    op.add_column("problems", sa.Column("source_category", sa.String(40)))
    op.add_column("problems", sa.Column("source_version", sa.String(64)))


def downgrade() -> None:
    op.drop_column("problems", "source_version")
    op.drop_column("problems", "source_category")
    op.drop_constraint("ck_problem_tags_kind", "problem_tags", type_="check")
    op.drop_column("problem_tags", "kind")
