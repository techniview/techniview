"""Coursework history, assignment controls, durable jobs and account verification."""

import sqlalchemy as sa
from alembic import context, op

revision = "20261014_0009"
down_revision = "20261007_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE users SET email_verified_at = created_at")
    op.add_column(
        "assignments",
        sa.Column(
            "recipient_mode", sa.String(16), nullable=False, server_default="all"
        ),
    )
    op.add_column(
        "assignments", sa.Column("selected_membership_ids", sa.JSON(), nullable=True)
    )
    conn = op.get_bind()
    drafts = (
        conn.execute(sa.text("SELECT id FROM assignments WHERE state = 'draft'"))
        if not context.is_offline_mode()
        else []
    )
    assignments = sa.table(
        "assignments",
        sa.column("id"),
        sa.column("recipient_mode"),
        sa.column("selected_membership_ids", sa.JSON()),
    )
    for (aid,) in list(drafts):
        ids = list(
            conn.execute(
                sa.text(
                    "SELECT membership_id FROM assignment_recipients "
                    "WHERE assignment_id = :aid"
                ),
                {"aid": aid},
            ).scalars()
        )
        conn.execute(
            assignments.update()
            .where(assignments.c.id == aid)
            .values(recipient_mode="selected", selected_membership_ids=ids)
        )
    op.execute(
        "UPDATE assignments SET selected_membership_ids = JSON_ARRAY() "
        "WHERE selected_membership_ids IS NULL"
    )
    op.alter_column(
        "assignments",
        "selected_membership_ids",
        existing_type=sa.JSON(),
        nullable=False,
    )
    op.execute(
        "DELETE FROM assignment_recipients WHERE assignment_id IN "
        "(SELECT id FROM assignments WHERE state = 'draft')"
    )
    op.add_column(
        "assignment_recipients", sa.Column("removed_at", sa.DateTime(), nullable=True)
    )
    for name, datatype in [
        ("claim_owner", sa.String(64)),
        ("claimed_at", sa.DateTime()),
        ("next_check_at", sa.DateTime()),
    ]:
        op.add_column("submissions", sa.Column(name, datatype, nullable=True))
    op.create_index("ix_submissions_next_check_at", "submissions", ["next_check_at"])
    op.add_column(
        "submission_case_results",
        sa.Column("dispatch_started_at", sa.DateTime(), nullable=True),
    )
    # The old API dispatched inline. An unfinished row cannot be safely replayed
    # because Judge0 may already have accepted a case whose token was not saved.
    op.execute(
        "UPDATE submissions SET status = 'infrastructure_error', "
        "completed_at = CURRENT_TIMESTAMP(6), score = NULL "
        "WHERE status IN ('queued', 'running')"
    )
    # Existing tokens were already dispatched and must never be sent a second time.
    op.execute(
        "UPDATE submission_case_results r JOIN submissions s "
        "ON s.id = r.submission_id SET r.dispatch_started_at = s.submitted_at "
        "WHERE r.judge0_token IS NOT NULL"
    )
    op.alter_column(
        "course_problem_analytics",
        "completion_seconds_sum",
        existing_type=sa.BigInteger(),
        type_=sa.Numeric(20, 6),
        existing_nullable=False,
    )
    op.create_table(
        "course_enrollments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "course_id",
            sa.BigInteger(),
            sa.ForeignKey("courses.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("token_hash", sa.BINARY(32), unique=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("course_id", "email"),
    )
    op.create_table(
        "account_tokens",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("course_id", sa.BigInteger(), sa.ForeignKey("courses.id")),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("nonce", sa.String(64), unique=True, nullable=False),
        sa.Column("token_hash", sa.BINARY(32), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime()),
    )
    op.create_table(
        "email_jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("recipient", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id")),
        sa.Column("course_id", sa.BigInteger(), sa.ForeignKey("courses.id")),
        sa.Column("token_id", sa.BigInteger(), sa.ForeignKey("account_tokens.id")),
        sa.Column(
            "enrollment_id",
            sa.BigInteger(),
            sa.ForeignKey("course_enrollments.id", ondelete="SET NULL"),
        ),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(), nullable=False),
        sa.Column("claimed_at", sa.DateTime()),
        sa.Column("claimed_by", sa.String(64)),
        sa.Column("sent_at", sa.DateTime()),
        sa.Column("last_error", sa.String(255)),
    )
    op.create_table(
        "account_request_throttles",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("window_started_at", sa.DateTime(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
    )
    op.create_table(
        "assignment_audits",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "assignment_id",
            sa.BigInteger(),
            sa.ForeignKey("assignments.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "actor_membership_id",
            sa.BigInteger(),
            sa.ForeignKey("course_memberships.id"),
            nullable=False,
        ),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("before", sa.JSON(), nullable=False),
        sa.Column("after", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
    )
    if not context.is_offline_mode():
        from app.services.summaries import rebuild_course_summaries
        from sqlalchemy.orm import Session

        with Session(bind=conn) as db:
            rebuild_course_summaries(db)
            db.flush()


def downgrade() -> None:
    for table in [
        "assignment_audits",
        "account_request_throttles",
        "email_jobs",
        "account_tokens",
        "course_enrollments",
    ]:
        op.drop_table(table)
    op.alter_column(
        "course_problem_analytics",
        "completion_seconds_sum",
        existing_type=sa.Numeric(20, 6),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )
    op.drop_column("submission_case_results", "dispatch_started_at")
    op.drop_index("ix_submissions_next_check_at", table_name="submissions")
    for name in ["next_check_at", "claimed_at", "claim_owner"]:
        op.drop_column("submissions", name)
    op.drop_column("assignment_recipients", "removed_at")
    op.drop_column("assignments", "selected_membership_ids")
    op.drop_column("assignments", "recipient_mode")
    op.drop_column("users", "email_verified_at")
