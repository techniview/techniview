from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session, selectinload

from ..core.dependencies import CurrentUser, DbSession
from ..core.errors import ApiError
from ..core.judge0 import judge0_submit
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
    TestVisibility,
    User,
    problem_tag_assignments,
)
from ..schemas.contracts import (
    ProblemDetailResponse,
    ProblemListResponse,
    PublicRunResponse,
)
from ..services.execution import build_case_execution
from ..services.presentation import problem_detail, problem_summary
from ..services.progress import get_or_create_progress

router = APIRouter(prefix="/problems", tags=["problems"])
MAX_SOURCE_CODE_BYTES = 65535
MAX_RUN_TEXT_BYTES = 8192
JUDGE0_ACCEPTED_STATUS = 3
JUDGE0_INCOMPLETE_STATUSES = frozenset((1, 2, 13))


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_code: str = Field(min_length=1, max_length=MAX_SOURCE_CODE_BYTES)

    @field_validator("source_code")
    @classmethod
    def source_byte_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_SOURCE_CODE_BYTES:
            raise ValueError("source code must not exceed 65535 UTF-8 bytes")
        return value


def _run_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Judge0 returned invalid execution output")
    return value.encode("utf-8")[:MAX_RUN_TEXT_BYTES].decode("utf-8", errors="ignore")


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


@router.post("/{problem_id}/run", response_model=PublicRunResponse)
def run_public_cases(
    problem_id: int, body: RunRequest, db: DbSession, user: CurrentUser
):
    problem = _visible_problem(db, problem_id, user)
    cases = [
        case for case in problem.test_cases if case.visibility == TestVisibility.PUBLIC
    ]
    if not cases:
        raise ApiError(409, "no_public_cases", "This problem has no public cases.")
    results = []
    for case in cases:
        execution = build_case_execution(problem, case, body.source_code)
        try:
            report = judge0_submit(
                execution.source_code,
                stdin=execution.stdin,
                expected_output=execution.expected_output,
                wait=True,
                timeout=10,
                cpu_time_limit=float(problem.cpu_time_limit_seconds),
                memory_limit=problem.memory_limit_kb,
            )
        except httpx.HTTPError as error:
            raise ApiError(
                502, "runner_unavailable", "The code runner is unavailable."
            ) from error
        if not isinstance(report, dict):
            raise ApiError(
                502,
                "runner_invalid_response",
                "The code runner returned an invalid result.",
            )
        status = report.get("status")
        if not isinstance(status, dict) or not isinstance(status.get("id"), int):
            raise ApiError(
                502,
                "runner_invalid_response",
                "The code runner returned an invalid result.",
            )
        status_id = status["id"]
        if status_id in JUDGE0_INCOMPLETE_STATUSES:
            raise ApiError(
                502,
                "runner_incomplete",
                "The code runner did not finish a public case.",
            )
        try:
            results.append(
                {
                    "case_order": case.case_order,
                    "status_id": status_id,
                    "input": case.input,
                    "expected_output": case.expected_output,
                    "stdout": _run_text(report.get("stdout")),
                    "stderr": _run_text(report.get("stderr")),
                    "compile_output": _run_text(report.get("compile_output")),
                }
            )
        except ValueError as error:
            raise ApiError(
                502,
                "runner_invalid_response",
                "The code runner returned an invalid result.",
            ) from error
    return {
        "passed_count": sum(
            result["status_id"] == JUDGE0_ACCEPTED_STATUS for result in results
        ),
        "test_count": len(results),
        "public_results": results,
    }
