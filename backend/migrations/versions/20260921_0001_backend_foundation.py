"""Create the backend foundation tables."""

import sqlalchemy as sa
from alembic import op

revision = "20260921_0001"
down_revision = None
branch_labels = None
depends_on = None


def _id(name: str = "id", **kwargs) -> sa.Column:
    return sa.Column(
        name,
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        **kwargs,
    )


def _enum(*values: str, name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False)


def _progress_columns() -> tuple[sa.Column, ...]:
    return (
        sa.Column("first_opened_at", sa.DateTime(), nullable=True),
        sa.Column("first_passed_at", sa.DateTime(), nullable=True),
        sa.Column("best_score", sa.Numeric(9, 8), nullable=False),
        sa.Column("valid_attempt_count", sa.Integer(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("wrong_answer_count", sa.Integer(), nullable=False),
        sa.Column("compile_error_count", sa.Integer(), nullable=False),
        sa.Column("runtime_error_count", sa.Integer(), nullable=False),
        sa.Column("timeout_count", sa.Integer(), nullable=False),
        sa.Column("resource_limit_count", sa.Integer(), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
    )


def upgrade() -> None:
    op.create_table(
        "courses",
        _id(primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "problem_tags",
        _id(primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("slug", sa.String(80), nullable=False),
    )
    op.create_index("ix_problem_tags_slug", "problem_tags", ["slug"], unique=True)
    op.create_table(
        "users",
        _id(primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "role",
            _enum("student", "professor", name="userrole"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("disabled_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table(
        "course_memberships",
        _id(primary_key=True, autoincrement=True),
        _id("course_id", nullable=False),
        _id("user_id", nullable=False),
        sa.Column(
            "role",
            _enum("student", "instructor", name="membershiprole"),
            nullable=False,
        ),
        sa.Column(
            "joined_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("withdrawn_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("course_id", "user_id", name="uq_memberships_course_user"),
        sa.UniqueConstraint("id", "course_id", name="uq_memberships_id_course"),
    )
    op.create_index(
        "ix_course_memberships_course_id",
        "course_memberships",
        ["course_id"],
    )
    op.create_index(
        "ix_course_memberships_user_id",
        "course_memberships",
        ["user_id"],
    )
    op.create_table(
        "problems",
        _id(primary_key=True, autoincrement=True),
        _id("owner_id", nullable=True),
        _id("copied_from_id", nullable=True),
        sa.Column(
            "origin",
            _enum("imported", "custom", name="problemorigin"),
            nullable=False,
        ),
        sa.Column(
            "state",
            _enum("draft", "published", "archived", name="problemstate"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column(
            "difficulty",
            _enum("easy", "medium", "hard", name="difficulty"),
            nullable=False,
        ),
        sa.Column(
            "execution_mode",
            _enum("call_based", "stdin_stdout", name="executionmode"),
            nullable=False,
        ),
        sa.Column("function_name", sa.String(255), nullable=False),
        sa.Column("starter_code", sa.Text(), nullable=False),
        sa.Column("cpu_time_limit_seconds", sa.Numeric(6, 3), nullable=False),
        sa.Column("memory_limit_kb", sa.Integer(), nullable=False),
        sa.Column("source_dataset", sa.String(255), nullable=True),
        sa.Column("source_problem_id", sa.String(255), nullable=True),
        sa.Column("attribution", sa.Text(), nullable=True),
        sa.Column("license", sa.String(255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["copied_from_id"], ["problems.id"]),
        sa.UniqueConstraint(
            "source_dataset", "source_problem_id", name="uq_problems_source"
        ),
    )
    op.create_index("ix_problems_difficulty", "problems", ["difficulty"])
    op.create_index("ix_problems_state", "problems", ["state"])
    op.create_table(
        "user_sessions",
        _id(primary_key=True, autoincrement=True),
        sa.Column("token_hash", sa.BINARY(32), nullable=False, unique=True),
        _id("user_id", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])
    op.create_table(
        "assignments",
        _id(primary_key=True, autoincrement=True),
        _id("course_id", nullable=False),
        _id("assigned_by_membership_id", nullable=False),
        sa.Column("title", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "state",
            _enum("draft", "published", "archived", name="assignmentstate"),
            nullable=False,
        ),
        sa.Column("available_at", sa.DateTime(), nullable=True),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by_membership_id", "course_id"],
            ["course_memberships.id", "course_memberships.course_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("id", "course_id", name="uq_assignments_id_course"),
    )
    op.create_index("ix_assignments_course_id", "assignments", ["course_id"])
    op.create_index("ix_assignments_state", "assignments", ["state"])
    op.create_table(
        "course_problem_analytics",
        _id("course_id", primary_key=True),
        _id("problem_id", primary_key=True),
        sa.Column("assigned_count", sa.Integer(), nullable=False),
        sa.Column("started_count", sa.Integer(), nullable=False),
        sa.Column("completed_count", sa.Integer(), nullable=False),
        sa.Column("completion_seconds_sum", sa.BigInteger(), nullable=False),
        sa.Column("valid_attempt_count", sa.Integer(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("wrong_answer_count", sa.Integer(), nullable=False),
        sa.Column("compile_error_count", sa.Integer(), nullable=False),
        sa.Column("runtime_error_count", sa.Integer(), nullable=False),
        sa.Column("timeout_count", sa.Integer(), nullable=False),
        sa.Column("resource_limit_count", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("assigned_count >= completed_count"),
        sa.CheckConstraint("assigned_count >= started_count"),
        sa.CheckConstraint("valid_attempt_count >= 0"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="RESTRICT"),
    )
    op.create_table(
        "course_problem_error_counts",
        _id("course_id", primary_key=True),
        _id("problem_id", primary_key=True),
        sa.Column("python_exception_type", sa.String(255), primary_key=True),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="RESTRICT"),
    )
    op.create_table(
        "curriculum_nodes",
        _id("problem_id", primary_key=True),
        sa.Column("priority", sa.Integer(), nullable=False, unique=True),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="RESTRICT"),
    )
    op.create_table(
        "problem_tag_assignments",
        _id("problem_id", primary_key=True),
        _id("tag_id", primary_key=True),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["problem_tags.id"], ondelete="RESTRICT"),
    )
    op.create_table(
        "problem_test_cases",
        _id(primary_key=True, autoincrement=True),
        _id("problem_id", nullable=False),
        sa.Column("case_order", sa.Integer(), nullable=False),
        sa.Column(
            "visibility",
            _enum("public", "hidden", name="testvisibility"),
            nullable=False,
        ),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("expected_output", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("problem_id", "case_order", name="uq_cases_order"),
    )
    op.create_table(
        "student_practice_progress",
        _id("student_id", primary_key=True),
        _id("problem_id", primary_key=True),
        *_progress_columns(),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="RESTRICT"),
    )
    op.create_table(
        "assignment_items",
        _id(primary_key=True, autoincrement=True),
        _id("assignment_id", nullable=False),
        _id("problem_id", nullable=False),
        sa.Column("item_order", sa.Integer(), nullable=False),
        sa.Column("points", sa.Numeric(10, 4), nullable=False),
        sa.Column("submission_limit", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["assignments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("assignment_id", "problem_id"),
        sa.UniqueConstraint("assignment_id", "item_order"),
        sa.UniqueConstraint("id", "problem_id", name="uq_assignment_items_id_problem"),
    )
    op.create_table(
        "assignment_recipients",
        _id("assignment_id", primary_key=True),
        _id("membership_id", primary_key=True),
        _id("course_id", nullable=False),
        sa.ForeignKeyConstraint(
            ["assignment_id", "course_id"],
            ["assignments.id", "assignments.course_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["membership_id", "course_id"],
            ["course_memberships.id", "course_memberships.course_id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_table(
        "curriculum_edges",
        _id("prerequisite_problem_id", primary_key=True),
        _id("problem_id", primary_key=True),
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
    )
    op.create_table(
        "student_assignment_progress",
        _id("student_id", primary_key=True),
        _id("assignment_item_id", primary_key=True),
        *_progress_columns(),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["assignment_item_id"], ["assignment_items.id"], ondelete="RESTRICT"
        ),
    )
    op.create_table(
        "submissions",
        _id(primary_key=True, autoincrement=True),
        _id("student_id", nullable=False),
        _id("problem_id", nullable=False),
        _id("assignment_item_id", nullable=True),
        sa.Column("source_code", sa.Text(), nullable=False),
        sa.Column(
            "status",
            _enum(
                "queued",
                "running",
                "passed",
                "failed",
                "compile_error",
                "runtime_error",
                "timeout",
                "resource_limit",
                "infrastructure_error",
                name="submissionstatus",
            ),
            nullable=False,
        ),
        sa.Column("score", sa.Numeric(9, 8), nullable=True),
        sa.Column(
            "primary_error",
            _enum(
                "wrong_answer",
                "compile_error",
                "runtime_error",
                "timeout",
                "resource_limit",
                name="errorcategory",
            ),
            nullable=True,
        ),
        sa.Column("python_exception_type", sa.String(255), nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"]),
        sa.ForeignKeyConstraint(
            ["assignment_item_id", "problem_id"],
            ["assignment_items.id", "assignment_items.problem_id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "problem_id", name="uq_submissions_id_problem"),
    )
    op.create_index(
        "idx_submissions_student_problem",
        "submissions",
        ["student_id", "problem_id"],
    )
    op.create_table(
        "submission_case_results",
        _id("submission_id", primary_key=True),
        _id("test_case_id", primary_key=True),
        sa.Column("judge0_token", sa.String(36), nullable=True),
        sa.Column("judge0_status_id", sa.Integer(), nullable=True),
        sa.Column("infrastructure_error", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["submission_id"], ["submissions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["test_case_id"], ["problem_test_cases.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index(
        "ix_submission_case_results_judge0_token",
        "submission_case_results",
        ["judge0_token"],
        unique=True,
    )
    op.create_index("ix_submissions_status", "submissions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_submissions_status", table_name="submissions")
    op.drop_index("idx_submissions_student_problem", table_name="submissions")
    op.drop_index(
        "ix_submission_case_results_judge0_token",
        table_name="submission_case_results",
    )
    op.drop_table("submission_case_results")
    op.drop_table("submissions")
    op.drop_table("student_assignment_progress")
    op.drop_table("curriculum_edges")
    op.drop_table("assignment_recipients")
    op.drop_table("assignment_items")
    op.drop_table("student_practice_progress")
    op.drop_table("problem_test_cases")
    op.drop_table("problem_tag_assignments")
    op.drop_table("curriculum_nodes")
    op.drop_table("course_problem_error_counts")
    op.drop_table("course_problem_analytics")
    op.drop_index("ix_assignments_state", table_name="assignments")
    op.drop_index("ix_assignments_course_id", table_name="assignments")
    op.drop_table("assignments")
    op.drop_index("ix_user_sessions_expires_at", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index("ix_problems_state", table_name="problems")
    op.drop_index("ix_problems_difficulty", table_name="problems")
    op.drop_table("problems")
    op.drop_index("ix_course_memberships_user_id", table_name="course_memberships")
    op.drop_index("ix_course_memberships_course_id", table_name="course_memberships")
    op.drop_table("course_memberships")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_problem_tags_slug", table_name="problem_tags")
    op.drop_table("problem_tags")
    op.drop_table("courses")
