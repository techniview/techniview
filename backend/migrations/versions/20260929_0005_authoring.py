"""Add canonical solutions and professor question sets."""

import sqlalchemy as sa
from alembic import op

revision = "20260929_0005"
down_revision = "20260924_0004"
branch_labels = None
depends_on = None

ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.add_column("problems", sa.Column("canonical_solution", sa.Text(), nullable=True))
    op.create_table(
        "question_sets",
        sa.Column("id", ID, primary_key=True, autoincrement=True),
        sa.Column(
            "owner_id",
            ID,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("state", sa.String(9), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_question_sets_owner_id", "question_sets", ["owner_id"])
    op.create_index("ix_question_sets_state", "question_sets", ["state"])
    op.create_table(
        "question_set_items",
        sa.Column("id", ID, primary_key=True, autoincrement=True),
        sa.Column(
            "question_set_id",
            ID,
            sa.ForeignKey("question_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "problem_id",
            ID,
            sa.ForeignKey("problems.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("item_order", sa.Integer(), nullable=False),
        sa.UniqueConstraint("question_set_id", "item_order"),
        sa.UniqueConstraint("question_set_id", "problem_id"),
    )
    op.create_index(
        "ix_question_set_items_question_set_id",
        "question_set_items",
        ["question_set_id"],
    )
    op.add_column("assignments", sa.Column("source_question_set_id", ID, nullable=True))
    op.create_foreign_key(
        "fk_assignments_source_question_set",
        "assignments",
        "question_sets",
        ["source_question_set_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_assignments_source_question_set", "assignments", type_="foreignkey"
    )
    op.drop_column("assignments", "source_question_set_id")
    op.drop_index(
        "ix_question_set_items_question_set_id", table_name="question_set_items"
    )
    op.drop_table("question_set_items")
    op.drop_index("ix_question_sets_state", table_name="question_sets")
    op.drop_index("ix_question_sets_owner_id", table_name="question_sets")
    op.drop_table("question_sets")
    op.drop_column("problems", "canonical_solution")
