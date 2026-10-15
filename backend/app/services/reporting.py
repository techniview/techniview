import csv
import hashlib
import hmac
import io
import os

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..core.errors import ApiError
from ..models import (
    Assignment,
    AssignmentItem,
    AssignmentRecipient,
    AssignmentState,
    CourseMembership,
    StudentAssignmentProgress,
    Submission,
    User,
)


def _csv(headers, rows) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        # Quoting alone does not prevent spreadsheet formula execution.
        writer.writerow(
            [
                "'" + value
                if isinstance(value, str)
                and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n"))
                else value
                for value in row
            ]
        )
    return output.getvalue()


def grade_rows(
    db: Session, course_id: int, assignment_id: int | None = None
) -> list[dict]:
    query = (
        select(User, AssignmentItem, StudentAssignmentProgress, CourseMembership)
        .select_from(Assignment)
        .join(AssignmentItem, AssignmentItem.assignment_id == Assignment.id)
        .join(AssignmentRecipient, AssignmentRecipient.assignment_id == Assignment.id)
        .join(
            CourseMembership, CourseMembership.id == AssignmentRecipient.membership_id
        )
        .join(User, User.id == CourseMembership.user_id)
        .outerjoin(
            StudentAssignmentProgress,
            and_(
                StudentAssignmentProgress.student_id == User.id,
                StudentAssignmentProgress.assignment_item_id == AssignmentItem.id,
            ),
        )
        .where(
            Assignment.course_id == course_id,
            Assignment.state != AssignmentState.DRAFT,
            AssignmentRecipient.removed_at.is_(None),
        )
        .order_by(Assignment.id, User.id, AssignmentItem.item_order, AssignmentItem.id)
    )
    if assignment_id is not None:
        query = query.where(Assignment.id == assignment_id)
    rows = []
    for student, item, progress, membership in db.execute(query):
        score = progress.best_score if progress else 0
        rows.append(
            (
                student.id,
                student.email,
                item.assignment_id,
                item.id,
                item.problem_id,
                item.points,
                score,
                score * item.points,
                progress.valid_attempt_count if progress else 0,
                bool(progress and progress.first_passed_at),
                membership.withdrawn_at is not None,
            )
        )
    return [dict(zip(GRADE_COLUMNS, row, strict=True)) for row in rows]


GRADE_COLUMNS = (
    "student_id",
    "email",
    "assignment_id",
    "assignment_item_id",
    "problem_id",
    "points_possible",
    "best_score",
    "points_earned",
    "valid_attempts",
    "passed",
    "withdrawn",
)


def grade_csv(db: Session, course_id: int, assignment_id: int | None) -> str:
    return _csv(
        GRADE_COLUMNS,
        (row.values() for row in grade_rows(db, course_id, assignment_id)),
    )


def research_csv(
    db: Session, course_id: int, assignment_id: int, publication_key: str
) -> str:
    secret = os.environ.get("RESEARCH_EXPORT_SECRET", "")
    if len(secret.encode()) < 32:
        raise ApiError(
            503,
            "research_export_unconfigured",
            "Research exports require a secret of at least 32 bytes.",
        )
    assignment = db.scalar(
        select(Assignment).where(
            Assignment.id == assignment_id,
            Assignment.course_id == course_id,
            Assignment.state != AssignmentState.DRAFT,
        )
    )
    if assignment is None:
        raise ApiError(404, "assignment_not_found", "Published assignment not found.")

    def pseudonym(kind: str, identifier: int) -> str:
        message = (
            f"{len(publication_key)}:{publication_key}:course:{course_id}:"
            f"{kind}:{identifier}"
        )
        return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()

    query = (
        select(
            Submission.student_id,
            Submission.problem_id,
            Submission.assignment_item_id,
            Submission.status,
            Submission.score,
            Submission.primary_error,
            Submission.is_late,
            Submission.late_approved_at,
            Submission.submitted_at,
            Submission.completed_at,
        )
        .join(AssignmentItem, AssignmentItem.id == Submission.assignment_item_id)
        .where(AssignmentItem.assignment_id == assignment_id)
        .order_by(Submission.student_id, Submission.submitted_at, Submission.id)
    )
    rows = []
    starts = {}
    for (
        student,
        problem,
        item,
        status,
        score,
        error,
        late,
        approved,
        submitted,
        completed,
    ) in db.execute(query):
        first = starts.setdefault(student, submitted)
        rows.append(
            (
                pseudonym("participant", student),
                pseudonym("problem", problem),
                pseudonym("context", item),
                status,
                score,
                error,
                late,
                approved is not None,
                (submitted - first).total_seconds(),
                (completed - submitted).total_seconds() if completed else None,
            )
        )
    return _csv(
        (
            "participant",
            "problem",
            "context",
            "status",
            "score",
            "error_category",
            "is_late",
            "late_approved",
            "seconds_since_first_attempt",
            "processing_seconds",
        ),
        rows,
    )
