from datetime import UTC, datetime

from fastapi import APIRouter, Header, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import exists, func, or_, select
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
    Submission,
    SubmissionStatus,
    TestVisibility,
    User,
    problem_tag_assignments,
)
from ..schemas.contracts import (
    ProblemDetailResponse,
    ProblemListResponse,
)
from ..services.execution import snapshot_case_result
from ..services.idempotency import (
    attach_idempotency_key,
    find_existing_submission,
    request_fingerprint,
)
from ..services.idempotency import (
    key_hash as hash_idempotency_key,
)
from ..services.presentation import problem_detail, problem_summary
from ..services.progress import get_or_create_progress

router = APIRouter(prefix="/problems", tags=["problems"])
MAX_SOURCE_CODE_BYTES = 65535
MAX_ACTIVE_PRACTICE_RUNS_PER_USER = 3


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_code: str = Field(min_length=1, max_length=MAX_SOURCE_CODE_BYTES)

    @field_validator("source_code")
    @classmethod
    def source_byte_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_SOURCE_CODE_BYTES:
            raise ValueError("source code must not exceed 65535 UTF-8 bytes")
        return value


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


@router.post("/{problem_id}/run", status_code=202)
def run_public_cases(
    problem_id: int,
    body: RunRequest,
    db: DbSession,
    user: CurrentUser,
    idempotency_key: str = Header(alias="Idempotency-Key"),
):
    db.scalar(select(User.id).where(User.id == user.id).with_for_update())
    key_digest = hash_idempotency_key(idempotency_key)
    fingerprint = request_fingerprint(
        "public_run", {"problem_id": problem_id, "source_code": body.source_code}
    )
    existing = find_existing_submission(
        db,
        user_id=user.id,
        operation="public_run",
        key_digest=key_digest,
        fingerprint=fingerprint,
    )
    if existing is not None:
        db.commit()
        from .submissions import _submission_response

        return _submission_response(existing)
    problem = _visible_problem(db, problem_id, user)
    cases = [
        case for case in problem.test_cases if case.visibility == TestVisibility.PUBLIC
    ]
    if not cases:
        raise ApiError(409, "no_public_cases", "This problem has no public cases.")
    active_runs = db.scalar(
        select(func.count())
        .select_from(Submission)
        .where(
            Submission.student_id == user.id,
            Submission.is_practice_run.is_(True),
            Submission.status.in_((SubmissionStatus.QUEUED, SubmissionStatus.RUNNING)),
        )
    )
    if active_runs >= MAX_ACTIVE_PRACTICE_RUNS_PER_USER:
        raise ApiError(
            429,
            "too_many_active_runs",
            "Wait for an active public run to finish before starting another.",
        )
    submission = Submission(
        student_id=user.id,
        problem_id=problem.id,
        assignment_item_id=None,
        source_code=body.source_code,
        status=SubmissionStatus.QUEUED,
        is_late=False,
        is_practice_run=True,
    )
    db.add(submission)
    db.flush()
    case_results = [
        snapshot_case_result(problem, case, body.source_code) for case in cases
    ]
    submission.case_results = case_results
    db.add_all(case_results)
    attach_idempotency_key(
        db,
        user_id=user.id,
        operation="public_run",
        key_digest=key_digest,
        fingerprint=fingerprint,
        submission_id=submission.id,
    )
    db.commit()
    from .submissions import _submission_response

    return _submission_response(submission)
