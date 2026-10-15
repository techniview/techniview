from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response
from sqlalchemy import and_, select
from sqlalchemy.orm import Session, selectinload

from ..core.authorization import get_membership
from ..core.dependencies import (
    CurrentUser,
    DbSession,
    InstructorMembership,
    StaffMembership,
)
from ..core.errors import ApiError
from ..models import (
    Assignment,
    AssignmentItem,
    AssignmentRecipient,
    AssignmentState,
    CourseMembership,
    CourseProblemAnalytics,
    Difficulty,
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
from ..services.summaries import summary_metrics

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
            AssignmentRecipient.removed_at.is_(None),
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
    scope: Literal["all", "practice", "assignments"] = "all",
    course_id: int | None = None,
    assignment_id: int | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    if course_id is not None:
        get_membership(db, course_id, user.id, include_withdrawn=True)
    if scope == "practice" and (course_id is not None or assignment_id is not None):
        raise ApiError(422, "invalid_filters", "Practice has no course or assignment.")
    rows = []
    if scope != "assignments" and course_id is None and assignment_id is None:
        rows.extend(
            (problem, record_from_progress(progress))
            for problem, progress in db.execute(
                select(Problem, StudentPracticeProgress)
                .join(
                    StudentPracticeProgress,
                    StudentPracticeProgress.problem_id == Problem.id,
                )
                .options(selectinload(Problem.tags))
                .where(StudentPracticeProgress.student_id == user.id)
            ).unique()
        )
    if scope != "practice":
        courses = db.scalars(
            select(CourseMembership.course_id).where(
                CourseMembership.user_id == user.id,
            )
        ).all()
        for identifier in courses:
            if course_id is None or course_id == identifier:
                rows.extend(
                    (problem, record)
                    for problem, _, record in _course_records(
                        db, identifier, assignment_id, user.id
                    )
                )
    grouped: dict[int, tuple[Problem, list[MetricRecord]]] = {}
    for problem, record in rows:
        if _matches_problem(problem, difficulty, tag):
            grouped.setdefault(problem.id, (problem, []))[1].append(record)
    items = [
        {"problem": problem_summary(problem), "metrics": calculate_metrics(records)}
        for problem, records in grouped.values()
    ]
    items.sort(key=lambda item: (item["problem"]["title"], item["problem"]["id"]))
    return {
        "metrics": calculate_metrics(
            [record for _, records in grouped.values() for record in records]
        ),
        "filters": {
            "difficulty": difficulty,
            "tag": tag,
            "scope": scope,
            "course_id": course_id,
            "assignment_id": assignment_id,
        },
        "items": items[offset : offset + limit],
        "total": len(items),
        "limit": limit,
        "offset": offset,
    }


@router.get(
    "/courses/{course_id}/analytics/overview",
    response_model=AnalyticsOverviewResponse,
)
def course_overview(
    course_id: int,
    db: DbSession,
    _membership: StaffMembership,
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
    totals = calculate_metrics(all_records)
    if assignment_id is None:
        summaries = list(
            db.scalars(
                select(CourseProblemAnalytics).where(
                    CourseProblemAnalytics.course_id == course_id,
                    CourseProblemAnalytics.problem_id.in_(grouped),
                )
            )
        )
        by_problem = {row.problem_id: row for row in summaries}
        for item in items:
            cached = by_problem.get(item["problem"]["id"])
            item["metrics"] = summary_metrics(
                [cached] if cached else [], item["metrics"].median_completion_seconds
            )
        totals = summary_metrics(summaries, totals.median_completion_seconds)
    return {
        "summary": totals,
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
    _membership: StaffMembership,
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
    metrics = calculate_metrics([record for _problem, record in rows])
    if assignment_id is None:
        cached = db.get(CourseProblemAnalytics, (course_id, problem_id))
        metrics = summary_metrics(
            [cached] if cached else [], metrics.median_completion_seconds
        )
    return {"problem": problem_summary(rows[0][0]), "metrics": metrics}


@router.get(
    "/courses/{course_id}/analytics/students/{student_id}/problems/{problem_id}",
    response_model=StudentProblemAnalyticsResponse,
)
def student_problem_analytics(
    course_id: int,
    student_id: int,
    problem_id: int,
    db: DbSession,
    _membership: StaffMembership,
    assignment_id: int | None = None,
):
    student_membership = db.scalar(
        select(CourseMembership).where(
            CourseMembership.course_id == course_id,
            CourseMembership.user_id == student_id,
        )
    )
    if student_membership is None:
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


@router.get("/courses/{course_id}/exports/grades.csv")
def export_course_grades(
    course_id: int,
    db: DbSession,
    _membership: InstructorMembership,
    assignment_id: int | None = None,
):
    from ..services.reporting import grade_csv

    return Response(
        grade_csv(db, course_id, assignment_id),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="grades.csv"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/courses/{course_id}/exports/research.csv")
def export_course_research(
    course_id: int,
    db: DbSession,
    _membership: InstructorMembership,
    assignment_id: int,
    publication_key: str = Query(min_length=1, max_length=200),
):
    from ..services.reporting import research_csv

    return Response(
        research_csv(db, course_id, assignment_id, publication_key),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="research.csv"',
            "Cache-Control": "private, no-store",
        },
    )
