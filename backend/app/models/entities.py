from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BINARY,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

ID_TYPE = BigInteger().with_variant(Integer, "sqlite")


def db_enum(enum_type: type[StrEnum]) -> Enum:
    return Enum(
        enum_type,
        native_enum=False,
        values_callable=lambda members: [member.value for member in members],
    )


class UserRole(StrEnum):
    STUDENT = "student"
    PROFESSOR = "professor"


class MembershipRole(StrEnum):
    STUDENT = "student"
    INSTRUCTOR = "instructor"
    TA = "ta"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class ProblemOrigin(StrEnum):
    IMPORTED = "imported"
    CUSTOM = "custom"


class ProblemState(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ExecutionMode(StrEnum):
    CALL_BASED = "call_based"
    STDIN_STDOUT = "stdin_stdout"


class TestVisibility(StrEnum):
    PUBLIC = "public"
    HIDDEN = "hidden"


class AssignmentState(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class SubmissionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    COMPILE_ERROR = "compile_error"
    RUNTIME_ERROR = "runtime_error"
    TIMEOUT = "timeout"
    RESOURCE_LIMIT = "resource_limit"
    INFRASTRUCTURE_ERROR = "infrastructure_error"


class ErrorCategory(StrEnum):
    WRONG_ANSWER = "wrong_answer"
    COMPILE_ERROR = "compile_error"
    RUNTIME_ERROR = "runtime_error"
    TIMEOUT = "timeout"
    RESOURCE_LIMIT = "resource_limit"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(db_enum(UserRole))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now()
    )
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    token_hash: Mapped[bytes] = mapped_column(BINARY(32), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    join_code_hash: Mapped[bytes | None] = mapped_column(
        BINARY(32), unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))


class CourseMembership(Base):
    __tablename__ = "course_memberships"
    __table_args__ = (
        UniqueConstraint("course_id", "user_id", name="uq_memberships_course_user"),
        UniqueConstraint("id", "course_id", name="uq_memberships_id_course"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    role: Mapped[MembershipRole] = mapped_column(db_enum(MembershipRole))
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now()
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))

    course: Mapped[Course] = relationship()
    user: Mapped[User] = relationship()


problem_tag_assignments = Table(
    "problem_tag_assignments",
    Base.metadata,
    Column(
        "problem_id", ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True
    ),
    Column(
        "tag_id", ForeignKey("problem_tags.id", ondelete="RESTRICT"), primary_key=True
    ),
)


class ProblemTag(Base):
    __tablename__ = "problem_tags"

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)


class Problem(Base):
    __tablename__ = "problems"
    __table_args__ = (
        UniqueConstraint(
            "source_dataset", "source_problem_id", name="uq_problems_source"
        ),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    copied_from_id: Mapped[int | None] = mapped_column(ForeignKey("problems.id"))
    origin: Mapped[ProblemOrigin] = mapped_column(db_enum(ProblemOrigin))
    state: Mapped[ProblemState] = mapped_column(db_enum(ProblemState), index=True)
    title: Mapped[str] = mapped_column(String(255))
    prompt: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[Difficulty] = mapped_column(db_enum(Difficulty), index=True)
    execution_mode: Mapped[ExecutionMode] = mapped_column(db_enum(ExecutionMode))
    function_name: Mapped[str] = mapped_column(String(255))
    starter_code: Mapped[str] = mapped_column(Text)
    cpu_time_limit_seconds: Mapped[Decimal] = mapped_column(
        Numeric(6, 3), default=Decimal("2.000")
    )
    memory_limit_kb: Mapped[int] = mapped_column(Integer, default=128000)
    source_dataset: Mapped[str | None] = mapped_column(String(255))
    source_problem_id: Mapped[str | None] = mapped_column(String(255))
    attribution: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now()
    )

    tags: Mapped[list[ProblemTag]] = relationship(
        secondary=problem_tag_assignments, lazy="selectin"
    )
    test_cases: Mapped[list[ProblemTestCase]] = relationship(
        back_populates="problem", lazy="selectin", order_by="ProblemTestCase.case_order"
    )


class ProblemTestCase(Base):
    __tablename__ = "problem_test_cases"
    __table_args__ = (
        UniqueConstraint("problem_id", "case_order", name="uq_cases_order"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    problem_id: Mapped[int] = mapped_column(
        ForeignKey("problems.id", ondelete="RESTRICT")
    )
    case_order: Mapped[int] = mapped_column(Integer)
    visibility: Mapped[TestVisibility] = mapped_column(db_enum(TestVisibility))
    input: Mapped[str] = mapped_column(Text)
    expected_output: Mapped[str] = mapped_column(Text)

    problem: Mapped[Problem] = relationship(back_populates="test_cases")


class CurriculumNode(Base):
    __tablename__ = "curriculum_nodes"

    problem_id: Mapped[int] = mapped_column(
        ForeignKey("problems.id", ondelete="RESTRICT"), primary_key=True
    )
    priority: Mapped[int] = mapped_column(Integer, unique=True)

    problem: Mapped[Problem] = relationship(lazy="joined")


class CurriculumEdge(Base):
    __tablename__ = "curriculum_edges"

    prerequisite_problem_id: Mapped[int] = mapped_column(
        ForeignKey("curriculum_nodes.problem_id", ondelete="CASCADE"), primary_key=True
    )
    problem_id: Mapped[int] = mapped_column(
        ForeignKey("curriculum_nodes.problem_id", ondelete="CASCADE"), primary_key=True
    )


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (
        UniqueConstraint("id", "course_id", name="uq_assignments_id_course"),
        ForeignKeyConstraint(
            ["assigned_by_membership_id", "course_id"],
            ["course_memberships.id", "course_memberships.course_id"],
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), index=True
    )
    assigned_by_membership_id: Mapped[int] = mapped_column(ID_TYPE)
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    state: Mapped[AssignmentState] = mapped_column(db_enum(AssignmentState), index=True)
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now()
    )

    items: Mapped[list[AssignmentItem]] = relationship(
        back_populates="assignment",
        lazy="selectin",
        order_by="AssignmentItem.item_order",
    )


class AssignmentItem(Base):
    __tablename__ = "assignment_items"
    __table_args__ = (
        UniqueConstraint("assignment_id", "problem_id"),
        UniqueConstraint("assignment_id", "item_order"),
        UniqueConstraint("id", "problem_id", name="uq_assignment_items_id_problem"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("assignments.id", ondelete="RESTRICT")
    )
    problem_id: Mapped[int] = mapped_column(
        ForeignKey("problems.id", ondelete="RESTRICT")
    )
    item_order: Mapped[int] = mapped_column(Integer)
    points: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("1"))
    submission_limit: Mapped[int | None] = mapped_column(Integer)

    assignment: Mapped[Assignment] = relationship(back_populates="items")
    problem: Mapped[Problem] = relationship(lazy="joined")


class AssignmentRecipient(Base):
    __tablename__ = "assignment_recipients"
    __table_args__ = (
        ForeignKeyConstraint(
            ["assignment_id", "course_id"],
            ["assignments.id", "assignments.course_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["membership_id", "course_id"],
            ["course_memberships.id", "course_memberships.course_id"],
            ondelete="RESTRICT",
        ),
    )

    assignment_id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    membership_id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True)
    course_id: Mapped[int] = mapped_column(ID_TYPE)


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        Index("idx_submissions_student_problem", "student_id", "problem_id"),
        UniqueConstraint("id", "problem_id", name="uq_submissions_id_problem"),
        ForeignKeyConstraint(
            ["assignment_item_id", "problem_id"],
            ["assignment_items.id", "assignment_items.problem_id"],
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id"))
    assignment_item_id: Mapped[int | None] = mapped_column(ID_TYPE)
    source_code: Mapped[str] = mapped_column(Text)
    status: Mapped[SubmissionStatus] = mapped_column(
        db_enum(SubmissionStatus), index=True
    )
    score: Mapped[Decimal | None] = mapped_column(Numeric(9, 8))
    primary_error: Mapped[ErrorCategory | None] = mapped_column(db_enum(ErrorCategory))
    python_exception_type: Mapped[str | None] = mapped_column(String(255))
    is_late: Mapped[bool] = mapped_column(default=False)
    late_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    # Plain id, deliberately no FK: the approver's own membership may later be
    # hard-erased, which RESTRICT constraints would block.
    late_approved_by_membership_id: Mapped[int | None] = mapped_column(ID_TYPE)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))

    case_results: Mapped[list[SubmissionCaseResult]] = relationship(
        back_populates="submission",
        lazy="selectin",
        order_by="SubmissionCaseResult.test_case_id",
    )


class SubmissionCaseResult(Base):
    __tablename__ = "submission_case_results"

    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), primary_key=True
    )
    test_case_id: Mapped[int] = mapped_column(
        ForeignKey("problem_test_cases.id", ondelete="RESTRICT"), primary_key=True
    )
    judge0_token: Mapped[str | None] = mapped_column(
        String(36), unique=True, index=True
    )
    callback_token_hash: Mapped[bytes | None] = mapped_column(
        BINARY(32), unique=True, index=True
    )
    judge0_status_id: Mapped[int | None] = mapped_column(Integer)
    infrastructure_error: Mapped[bool] = mapped_column(default=False)
    execution_time_ms: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    memory_kb: Mapped[int | None] = mapped_column(Integer)
    stdout: Mapped[str | None] = mapped_column(Text)
    stderr: Mapped[str | None] = mapped_column(Text)
    compile_output: Mapped[str | None] = mapped_column(Text)

    submission: Mapped[Submission] = relationship(back_populates="case_results")
    test_case: Mapped[ProblemTestCase] = relationship(lazy="joined")


class ProgressColumns:
    first_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    first_passed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    best_score: Mapped[Decimal] = mapped_column(Numeric(9, 8), default=Decimal("0"))
    valid_attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    wrong_answer_count: Mapped[int] = mapped_column(Integer, default=0)
    compile_error_count: Mapped[int] = mapped_column(Integer, default=0)
    runtime_error_count: Mapped[int] = mapped_column(Integer, default=0)
    timeout_count: Mapped[int] = mapped_column(Integer, default=0)
    resource_limit_count: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))


class StudentPracticeProgress(ProgressColumns, Base):
    __tablename__ = "student_practice_progress"

    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    problem_id: Mapped[int] = mapped_column(
        ForeignKey("problems.id", ondelete="RESTRICT"), primary_key=True
    )


class StudentAssignmentProgress(ProgressColumns, Base):
    __tablename__ = "student_assignment_progress"

    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    assignment_item_id: Mapped[int] = mapped_column(
        ForeignKey("assignment_items.id", ondelete="RESTRICT"), primary_key=True
    )


class CourseProblemAnalytics(Base):
    __tablename__ = "course_problem_analytics"
    __table_args__ = (
        CheckConstraint("assigned_count >= completed_count"),
        CheckConstraint("assigned_count >= started_count"),
        CheckConstraint("valid_attempt_count >= 0"),
    )

    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), primary_key=True
    )
    problem_id: Mapped[int] = mapped_column(
        ForeignKey("problems.id", ondelete="RESTRICT"), primary_key=True
    )
    assigned_count: Mapped[int] = mapped_column(Integer, default=0)
    started_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, default=0)
    completion_seconds_sum: Mapped[int] = mapped_column(BigInteger, default=0)
    valid_attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    wrong_answer_count: Mapped[int] = mapped_column(Integer, default=0)
    compile_error_count: Mapped[int] = mapped_column(Integer, default=0)
    runtime_error_count: Mapped[int] = mapped_column(Integer, default=0)
    timeout_count: Mapped[int] = mapped_column(Integer, default=0)
    resource_limit_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now()
    )


class CourseProblemErrorCount(Base):
    __tablename__ = "course_problem_error_counts"

    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="RESTRICT"), primary_key=True
    )
    problem_id: Mapped[int] = mapped_column(
        ForeignKey("problems.id", ondelete="RESTRICT"), primary_key=True
    )
    python_exception_type: Mapped[str] = mapped_column(String(255), primary_key=True)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now()
    )
