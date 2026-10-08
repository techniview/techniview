"""Replace problem prerequisites with technique-pool progression."""

import sqlalchemy as sa
from alembic import op

revision = "20261007_0007"
down_revision = "20261006_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("curriculum_edges")


def downgrade() -> None:
    op.create_table(
        "curriculum_edges",
        sa.Column("prerequisite_problem_id", sa.BigInteger(), nullable=False),
        sa.Column("problem_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["prerequisite_problem_id"],
            ["curriculum_nodes.problem_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["problem_id"],
            ["curriculum_nodes.problem_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("prerequisite_problem_id", "problem_id"),
    )
