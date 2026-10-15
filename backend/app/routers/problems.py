from datetime import UTC, datetime

from fastapi import APIRouter, Query
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session, selectinload

from ..core.dependencies import CurrentUser, DbSession
from ..core.errors import ApiError
from ..models import (
    Assignment,
    AssignmentItem,
    AssignmentRecipient,
    AssignmentState,
    Course,
    CourseMembership,
    Difficulty,
    MembershipRole,
    Problem,
    ProblemState,
    ProblemTag,
    User,
    problem_tag_assignments,
)
from ..schemas.contracts import ProblemDetailResponse, ProblemListResponse
from ..services.presentation import problem_detail, problem_summary
from ..services.progress import get_or_create_progress

router = APIRouter(prefix="/problems", tags=["problems"])


def _assignment_contexts(db: Session, user_id: int, problem_id: int | None = None):
    now = datetime.now(UTC).replace(tzinfo=None)
    query = (
        select(
            AssignmentItem.id,
            AssignmentItem.problem_id,
            Assignment.title,
            Course.id,
            Course.name,
        )
        .join(Assignment, Assignment.id == AssignmentItem.assignment_id)
        .join(Course, Course.id == Assignment.course_id)
        .join(
            AssignmentRecipient,
            AssignmentRecipient.assignment_id == AssignmentItem.assignment_id,
        )
        .join(
            CourseMembership,
            CourseMembership.id == AssignmentRecipient.membership_id,
        )
        .where(
            CourseMembership.user_id == user_id,
            CourseMembership.role == MembershipRole.STUDENT,
            CourseMembership.withdrawn_at.is_(None),
            AssignmentRecipient.removed_at.is_(None),
            Course.archived_at.is_(None),
            Assignment.state == AssignmentState.PUBLISHED,
            or_(Assignment.available_at.is_(None), Assignment.available_at <= now),
        )
    )
    if problem_id is not None:
        query = query.where(AssignmentItem.problem_id == problem_id)
    return db.execute(
        query.order_by(Course.name, Assignment.title, AssignmentItem.id)
    ).all()


def _assigned_problem_ids(db: Session, user_id: int) -> set[int]:
    return {row[1] for row in _assignment_contexts(db, user_id)}


def _staffed_problem_ids(db: Session, user_id: int) -> set[int]:
    # Staff see problems from non-draft assignments (published + archived),
    # unlike students who only see published ones.
    return set(
        db.scalars(
            select(AssignmentItem.problem_id)
            .join(Assignment, Assignment.id == AssignmentItem.assignment_id)
            .join(
                CourseMembership,
                CourseMembership.course_id == Assignment.course_id,
            )
            .where(
                CourseMembership.user_id == user_id,
                CourseMembership.withdrawn_at.is_(None),
                CourseMembership.role.in_(
                    [MembershipRole.INSTRUCTOR, MembershipRole.TA]
                ),
                Assignment.state != AssignmentState.DRAFT,
            )
        ).all()
    )


def _visible_problem(db: Session, problem_id: int, user: User) -> Problem:
    problem = db.scalar(
        select(Problem)
        .options(selectinload(Problem.tags), selectinload(Problem.test_cases))
        .where(Problem.id == problem_id)
    )
    if problem is None:
        raise ApiError(404, "problem_not_found", "Problem not found.")
    globally_visible = (
        problem.owner_id is None and problem.state == ProblemState.PUBLISHED
    )
    if not (
        globally_visible
        or problem.owner_id == user.id
        or problem.id in _assigned_problem_ids(db, user.id)
        or problem.id in _staffed_problem_ids(db, user.id)
    ):
        raise ApiError(404, "problem_not_found", "Problem not found.")
    return problem


@router.get("", response_model=ProblemListResponse)
def list_problems(
    db: DbSession,
    user: CurrentUser,
    difficulty: Difficulty | None = None,
    tag: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    assignment_items = {}
    for item_id, problem_id, *_rest in _assignment_contexts(db, user.id):
        assignment_items.setdefault(problem_id, item_id)
    assigned_ids = set(assignment_items)
    staffed_ids = _staffed_problem_ids(db, user.id)
    visibility = [
        Problem.owner_id.is_(None) & (Problem.state == ProblemState.PUBLISHED),
        Problem.owner_id == user.id,
    ]
    if assigned_ids:
        visibility.append(Problem.id.in_(assigned_ids))
    if staffed_ids:
        visibility.append(Problem.id.in_(staffed_ids))
    query = (
        select(Problem)
        .options(selectinload(Problem.tags))
        .where(or_(*visibility))
        .order_by(Problem.title, Problem.id)
    )
    if difficulty is not None:
        query = query.where(Problem.difficulty == difficulty)
    if tag:
        query = query.where(
            exists()
            .where(problem_tag_assignments.c.problem_id == Problem.id)
            .where(problem_tag_assignments.c.tag_id == ProblemTag.id)
            .where(ProblemTag.slug == tag)
        )
    problems = list(db.scalars(query).unique().all())
    return {
        "items": [
            {
                **problem_summary(item),
                "available_assignment_item_id": assignment_items.get(item.id),
            }
            for item in problems[offset : offset + limit]
        ],
        "total": len(problems),
        "limit": limit,
        "offset": offset,
    }


@router.get("/{problem_id}", response_model=ProblemDetailResponse)
def get_problem(
    problem_id: int,
    db: DbSession,
    user: CurrentUser,
):
    detail = problem_detail(_visible_problem(db, problem_id, user))
    detail["assignment_contexts"] = [
        {
            "assignment_item_id": item_id,
            "assignment_title": title,
            "course_id": course_id,
            "course_name": course_name,
        }
        for item_id, _problem_id, title, course_id, course_name in _assignment_contexts(
            db, user.id, problem_id
        )
    ]
    return detail


@router.post("/{problem_id}/start", status_code=204)
def start_problem(
    problem_id: int,
    db: DbSession,
    user: CurrentUser,
    assignment_item_id: int | None = None,
):
    _visible_problem(db, problem_id, user)
    get_or_create_progress(db, user.id, problem_id, assignment_item_id)
    db.commit()
