from fastapi import APIRouter, Query
from sqlalchemy import and_, select
from sqlalchemy.orm import Session, selectinload

from ..core.authorization import get_membership
from ..core.dependencies import CurrentUser, DbSession, InstructorMembership
from ..core.errors import ApiError
from ..models import (
    Assignment,
    AssignmentItem,
    AssignmentRecipient,
    AssignmentState,
    CourseMembership,
    Difficulty,
    MembershipRole,
    Problem,
    StudentAssignmentProgress,
    StudentPracticeProgress,
    User,
)
from ..schemas.contracts import (
    AnalyticsOverviewResponse,
    ProblemAnalyticsResponse,
    StudentAnalyticsResponse,
    StudentProblemAnalyticsResponse,
)
from ..services.analytics import MetricRecord, calculate_metrics, record_from_progress
from ..services.presentation import problem_summary

router = APIRouter(tags=["analytics"])


def _matches_problem(problem: Problem, difficulty: Difficulty | None, tag: str | None):
    return (difficulty is None or problem.difficulty == difficulty) and (
        tag is None or tag in {item.slug for item in problem.tags}
    )


def _course_records(
    db: Session,
    course_id: int,
    assignment_id: int | None = None,
    student_id: int | None = None,
) -> list[tuple[Problem, int, MetricRecord]]:
    query = (
        select(
            Problem,
            CourseMembership.user_id,
            AssignmentItem.id,
            StudentAssignmentProgress,
        )
        .join(AssignmentItem, AssignmentItem.problem_id == Problem.id)
        .join(Assignment, Assignment.id == AssignmentItem.assignment_id)
        .join(
            AssignmentRecipient,
            AssignmentRecipient.assignment_id == Assignment.id,
        )
        .join(
            CourseMembership,
            CourseMembership.id == AssignmentRecipient.membership_id,
        )
        .outerjoin(
            StudentAssignmentProgress,
            and_(
                StudentAssignmentProgress.assignment_item_id == AssignmentItem.id,
                StudentAssignmentProgress.student_id == CourseMembership.user_id,
            ),
        )
        .options(selectinload(Problem.tags))
        .where(
            Assignment.course_id == course_id,
            Assignment.state != AssignmentState.DRAFT,
            CourseMembership.role == MembershipRole.STUDENT,
        )
    )
    if assignment_id is not None:
        query = query.where(Assignment.id == assignment_id)
    if student_id is not None:
        query = query.where(CourseMembership.user_id == student_id)
    return [
        (problem, owner_id, record_from_progress(progress))
        for problem, owner_id, _item_id, progress in db.execute(query).unique().all()
    ]


@router.get("/me/analytics", response_model=StudentAnalyticsResponse)
def my_analytics(
    db: DbSession,
    user: CurrentUser,
    difficulty: Difficulty | None = None,
    tag: str | None = None,
):
    practice_rows = db.execute(
        select(Problem, StudentPracticeProgress)
        .join(
            StudentPracticeProgress,
            StudentPracticeProgress.problem_id == Problem.id,
        )
        .options(selectinload(Problem.tags))
        .where(StudentPracticeProgress.student_id == user.id)
    ).unique()
    records = [
        record_from_progress(progress)
        for problem, progress in practice_rows
        if _matches_problem(problem, difficulty, tag)
    ]
    assignment_rows = db.execute(
        select(Problem, AssignmentItem.id, StudentAssignmentProgress)
        .join(AssignmentItem, AssignmentItem.problem_id == Problem.id)
        .join(Assignment, Assignment.id == AssignmentItem.assignment_id)
        .join(
            AssignmentRecipient,
            AssignmentRecipient.assignment_id == Assignment.id,
        )
        .join(
            CourseMembership,
            CourseMembership.id == AssignmentRecipient.membership_id,
        )
        .outerjoin(
            StudentAssignmentProgress,
            and_(
                StudentAssignmentProgress.assignment_item_id == AssignmentItem.id,
                StudentAssignmentProgress.student_id == CourseMembership.user_id,
            ),
        )
        .options(selectinload(Problem.tags))
        .where(
            CourseMembership.user_id == user.id,
            Assignment.state != AssignmentState.DRAFT,
        )
    ).unique()
    records.extend(
        record_from_progress(progress)
        for problem, _item_id, progress in assignment_rows
        if _matches_problem(problem, difficulty, tag)
    )
    return {
        "metrics": calculate_metrics(records),
        "filters": {"difficulty": difficulty, "tag": tag},
    }


@router.get(
    "/courses/{course_id}/analytics/overview",
    response_model=AnalyticsOverviewResponse,
)
def course_overview(
    course_id: int,
    db: DbSession,
    _membership: InstructorMembership,
    assignment_id: int | None = None,
    difficulty: Difficulty | None = None,
    tag: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    grouped: dict[int, tuple[Problem, list[MetricRecord]]] = {}
    for problem, _student_id, record in _course_records(db, course_id, assignment_id):
        if not _matches_problem(problem, difficulty, tag):
            continue
        grouped.setdefault(problem.id, (problem, []))[1].append(record)
    items = [
        {"problem": problem_summary(problem), "metrics": calculate_metrics(records)}
        for problem, records in grouped.values()
    ]
    items.sort(key=lambda item: (item["problem"]["title"], item["problem"]["id"]))
    all_records = [
        record for _problem, records in grouped.values() for record in records
    ]
    return {
        "summary": calculate_metrics(all_records),
        "items": items[offset : offset + limit],
        "total": len(items),
        "limit": limit,
        "offset": offset,
    }


@router.get(
    "/courses/{course_id}/analytics/problems/{problem_id}",
    response_model=ProblemAnalyticsResponse,
)
def course_problem_analytics(
    course_id: int,
    problem_id: int,
    db: DbSession,
    _membership: InstructorMembership,
    assignment_id: int | None = None,
):
    rows = [
        (problem, record)
        for problem, _student_id, record in _course_records(
            db, course_id, assignment_id
        )
        if problem.id == problem_id
    ]
    if not rows:
        raise ApiError(
            404,
            "problem_not_assigned",
            "Problem is not assigned in this course.",
        )
    return {
        "problem": problem_summary(rows[0][0]),
        "metrics": calculate_metrics([record for _problem, record in rows]),
    }


@router.get(
    "/courses/{course_id}/analytics/students/{student_id}/problems/{problem_id}",
    response_model=StudentProblemAnalyticsResponse,
)
def student_problem_analytics(
    course_id: int,
    student_id: int,
    problem_id: int,
    db: DbSession,
    _membership: InstructorMembership,
    assignment_id: int | None = None,
):
    student_membership = get_membership(db, course_id, student_id)
    if student_membership.role != MembershipRole.STUDENT:
        raise ApiError(404, "student_not_found", "Student not found.")
    student = db.get(User, student_id)
    rows = [
        (problem, record)
        for problem, _owner_id, record in _course_records(
            db, course_id, assignment_id, student_id
        )
        if problem.id == problem_id
    ]
    if not rows or student is None:
        raise ApiError(
            404,
            "problem_not_assigned",
            "Problem is not assigned to this student.",
        )
    return {
        "student": student,
        "problem": problem_summary(rows[0][0]),
        "metrics": calculate_metrics([record for _problem, record in rows]),
    }
