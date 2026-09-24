import base64
import secrets
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal
from enum import IntEnum

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, lazyload, selectinload
from sqlalchemy.orm.attributes import set_committed_value

from ..core.authorization import get_membership
from ..core.config import settings
from ..core.dependencies import (
    CurrentUser,
    DbSession,
    InstructorMembership,
    StaffMembership,
)
from ..core.errors import ApiError
from ..core.judge0 import judge0_get, judge0_submit
from ..core.security import hash_token
from ..models import (
    Assignment,
    AssignmentItem,
    ErrorCategory,
    Submission,
    SubmissionCaseResult,
    SubmissionStatus,
    TestVisibility,
)
from ..services.execution import build_case_execution
from ..services.progress import (
    finalize_progress,
    get_or_create_progress,
    recompute_assignment_grade,
    require_assigned_item,
)
from .problems import _visible_problem

router = APIRouter(prefix="/submissions", tags=["submissions"])
internal_router = APIRouter(prefix="/internal/judge0", tags=["internal"])
course_router = APIRouter(
    prefix="/courses/{course_id}/submissions", tags=["staff-submissions"]
)


class SubmissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_code: str = Field(min_length=1, max_length=65535)
    language_id: int = Field(default=71, gt=0)
    problem_id: int = Field(gt=0)
    assignment_item_id: int | None = Field(default=None, gt=0)

    @field_validator("source_code")
    @classmethod
    def _source_byte_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 65535:
            raise ValueError("source code must not exceed 65535 UTF-8 bytes")
        return value

    @field_validator("language_id")
    @classmethod
    def _python_only(cls, value: int) -> int:
        if value != 71:
            raise ValueError("only Python (language_id=71) is supported")
        return value


class Judge0Status(IntEnum):
    IN_QUEUE = 1
    PROCESSING = 2
    ACCEPTED = 3
    WRONG_ANSWER = 4
    TIME_LIMIT_EXCEEDED = 5
    COMPILATION_ERROR = 6
    SIGSEGV = 7
    SIGXFSZ = 8
    SIGFPE = 9
    SIGABRT = 10
    NZEC = 11
    RUNTIME_OTHER = 12
    INTERNAL_ERROR = 13
    EXEC_FORMAT_ERROR = 14


def get_status_message(status_code: int) -> str:
    messages = {
        1: "In queue. Waiting for a worker.",
        2: "Running your code.",
        3: "Accepted. Nice work!",
        4: "Wrong answer. Output did not match expected.",
        5: "Time limit exceeded. Check for an infinite loop or a slower step.",
        6: "Compilation error. Check your syntax.",
        7: "Crashed. Segmentation fault.",
        8: "Crashed. Output file too large.",
        9: "Crashed. Low-level fault (SIGFPE).",
        10: "Crashed. Program aborted.",
        11: "Runtime error. Program exited with an error.",
        12: "Runtime error. Something went wrong while running.",
        13: "Internal error. Our runner hit a problem. Try again.",
        14: "Exec format error. Runner could not start your program.",
    }
    return messages.get(int(status_code), f"Unknown status code: {status_code}")


def _judge0_error(error: Exception) -> HTTPException:
    if isinstance(error, httpx.TimeoutException):
        return HTTPException(status_code=504, detail="runner timed out")
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code if error.response is not None else None
        if status == 429:
            return HTTPException(status_code=429, detail="runner busy, try again")
    return HTTPException(status_code=502, detail="runner unavailable")


def _is_terminal(status_id: int | None) -> bool:
    return status_id is not None and status_id >= Judge0Status.ACCEPTED


def _error_for_status(status_id: int) -> ErrorCategory | None:
    if status_id == Judge0Status.WRONG_ANSWER:
        return ErrorCategory.WRONG_ANSWER
    if status_id == Judge0Status.TIME_LIMIT_EXCEEDED:
        return ErrorCategory.TIMEOUT
    if status_id == Judge0Status.COMPILATION_ERROR:
        return ErrorCategory.COMPILE_ERROR
    if status_id == Judge0Status.SIGXFSZ:
        return ErrorCategory.RESOURCE_LIMIT
    if status_id in {
        Judge0Status.SIGSEGV,
        Judge0Status.SIGFPE,
        Judge0Status.SIGABRT,
        Judge0Status.NZEC,
        Judge0Status.RUNTIME_OTHER,
        Judge0Status.EXEC_FORMAT_ERROR,
    }:
        return ErrorCategory.RUNTIME_ERROR
    return None


ERROR_STATUSES = {
    ErrorCategory.WRONG_ANSWER: SubmissionStatus.FAILED,
    ErrorCategory.COMPILE_ERROR: SubmissionStatus.COMPILE_ERROR,
    ErrorCategory.RUNTIME_ERROR: SubmissionStatus.RUNTIME_ERROR,
    ErrorCategory.TIMEOUT: SubmissionStatus.TIMEOUT,
    ErrorCategory.RESOURCE_LIMIT: SubmissionStatus.RESOURCE_LIMIT,
}
ERROR_PRIORITY = (
    ErrorCategory.COMPILE_ERROR,
    ErrorCategory.TIMEOUT,
    ErrorCategory.RESOURCE_LIMIT,
    ErrorCategory.RUNTIME_ERROR,
    ErrorCategory.WRONG_ANSWER,
)
TERMINAL_SUBMISSION_STATUSES = frozenset(
    {
        SubmissionStatus.PASSED,
        SubmissionStatus.FAILED,
        SubmissionStatus.COMPILE_ERROR,
        SubmissionStatus.RUNTIME_ERROR,
        SubmissionStatus.TIMEOUT,
        SubmissionStatus.RESOURCE_LIMIT,
        SubmissionStatus.INFRASTRUCTURE_ERROR,
    }
)
MAX_REPORT_TEXT_BYTES = 65_535


def _report_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("Judge0 returned a non-text report field")
    return value.encode("utf-8")[:MAX_REPORT_TEXT_BYTES].decode(
        "utf-8", errors="ignore"
    )


def _update_case_result(case_result: SubmissionCaseResult, data: dict) -> None:
    if not isinstance(data, dict):
        raise ValueError("Judge0 returned a non-object submission report")
    status = data.get("status") or {}
    if not isinstance(status, dict):
        raise TypeError("Judge0 returned an invalid status")
    status_id = status.get("id")
    if status_id is not None:
        status_id = int(status_id)
        if (
            status_id < Judge0Status.IN_QUEUE
            or status_id > Judge0Status.EXEC_FORMAT_ERROR
        ):
            raise ValueError(f"Judge0 returned an unknown status: {status_id}")
        case_result.judge0_status_id = status_id
        case_result.infrastructure_error = status_id == Judge0Status.INTERNAL_ERROR
    if data.get("time") is not None:
        execution_time_ms = Decimal(str(data["time"])) * Decimal("1000")
        if not execution_time_ms.is_finite() or execution_time_ms < 0:
            raise ValueError("Judge0 returned an invalid execution time")
        case_result.execution_time_ms = execution_time_ms.quantize(Decimal("0.001"))
    if data.get("memory") is not None:
        memory_kb = Decimal(str(data["memory"]))
        if not memory_kb.is_finite() or memory_kb < 0:
            raise ValueError("Judge0 returned invalid memory usage")
        case_result.memory_kb = int(memory_kb.to_integral_value(rounding=ROUND_CEILING))
    for field in ("stdout", "stderr", "compile_output"):
        if field in data:
            setattr(case_result, field, _report_text(data[field]))


def _finalize_submission(db: Session, submission: Submission) -> None:
    if submission.status in TERMINAL_SUBMISSION_STATUSES:
        return
    results = submission.case_results
    if not results:
        return
    if any(result.infrastructure_error for result in results):
        submission.status = SubmissionStatus.INFRASTRUCTURE_ERROR
        submission.completed_at = datetime.now(UTC).replace(tzinfo=None)
        submission.score = None
        return
    if any(not _is_terminal(result.judge0_status_id) for result in results):
        submission.status = (
            SubmissionStatus.RUNNING
            if any(
                result.judge0_status_id == Judge0Status.PROCESSING for result in results
            )
            else SubmissionStatus.QUEUED
        )
        return

    passed_count = sum(
        result.judge0_status_id == Judge0Status.ACCEPTED for result in results
    )
    submission.completed_at = datetime.now(UTC).replace(tzinfo=None)
    submission.score = Decimal(passed_count) / Decimal(len(results))
    if passed_count == len(results):
        submission.status = SubmissionStatus.PASSED
        submission.primary_error = None
    else:
        errors = {
            error
            for result in results
            if result.judge0_status_id is not None
            if (error := _error_for_status(result.judge0_status_id)) is not None
        }
        submission.primary_error = next(
            error for error in ERROR_PRIORITY if error in errors
        )
        submission.status = ERROR_STATUSES[submission.primary_error]
    finalize_progress(db, submission)


def _submission_response(submission: Submission) -> dict:
    public_results = [
        {
            "case_order": result.test_case.case_order,
            "status_id": result.judge0_status_id,
            "friendly_message": (
                get_status_message(result.judge0_status_id)
                if result.judge0_status_id is not None
                else get_status_message(Judge0Status.IN_QUEUE)
            ),
        }
        for result in submission.case_results
        if result.test_case.visibility == TestVisibility.PUBLIC
    ]
    passed_count = sum(
        result.judge0_status_id == Judge0Status.ACCEPTED
        for result in submission.case_results
    )
    return {
        "id": submission.id,
        "status": submission.status,
        "done": submission.status in TERMINAL_SUBMISSION_STATUSES,
        "score": submission.score,
        "is_late": submission.is_late,
        "late_approved": submission.late_approved_at is not None,
        "passed_count": passed_count,
        "test_count": len(submission.case_results),
        "public_results": public_results,
        "poll_url": f"/api/submissions/{submission.id}",
    }


def _reserve_submission(
    db: Session,
    body: SubmissionCreate,
    student_id: int,
) -> Submission:
    item = None
    if body.assignment_item_id is not None:
        item = require_assigned_item(
            db,
            student_id,
            body.problem_id,
            body.assignment_item_id,
        )
    get_or_create_progress(
        db,
        student_id,
        body.problem_id,
        body.assignment_item_id,
    )
    if item is not None and item.submission_limit is not None:
        reserved_count = db.scalar(
            select(func.count())
            .select_from(Submission)
            .where(
                Submission.student_id == student_id,
                Submission.assignment_item_id == item.id,
                Submission.status != SubmissionStatus.INFRASTRUCTURE_ERROR,
            )
        )
        if reserved_count >= item.submission_limit:
            raise ApiError(
                409,
                "submission_limit_reached",
                "The submission limit has been reached.",
            )
    submission = Submission(
        student_id=student_id,
        problem_id=body.problem_id,
        assignment_item_id=body.assignment_item_id,
        source_code=body.source_code,
        status=SubmissionStatus.QUEUED,
        is_late=_is_late_submission(db, item),
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return submission


def _is_late_submission(db: Session, item: AssignmentItem | None) -> bool:
    if item is None:
        return False
    due_at = db.scalar(
        select(Assignment.due_at).where(Assignment.id == item.assignment_id)
    )
    return due_at is not None and datetime.now(UTC).replace(tzinfo=None) > due_at


def _load_submission(db: Session, submission_id: int) -> Submission | None:
    submission = db.scalar(
        select(Submission)
        .options(lazyload(Submission.case_results))
        .where(Submission.id == submission_id)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if submission is not None:
        # Locking reads see committed results even with a REPEATABLE READ snapshot.
        results = db.scalars(
            select(SubmissionCaseResult)
            .options(selectinload(SubmissionCaseResult.test_case))
            .where(SubmissionCaseResult.submission_id == submission_id)
            .order_by(SubmissionCaseResult.test_case_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        ).all()
        set_committed_value(submission, "case_results", results)
    return submission


def _mark_case_infrastructure_error(
    db: Session,
    submission_id: int,
    test_case_id: int,
) -> None:
    result = db.get(
        SubmissionCaseResult,
        {"submission_id": submission_id, "test_case_id": test_case_id},
    )
    if result is None:
        return
    result.judge0_status_id = Judge0Status.INTERNAL_ERROR
    result.infrastructure_error = True
    submission = _load_submission(db, submission_id)
    if submission is not None:
        _finalize_submission(db, submission)
    db.commit()


@router.post("")
@router.post("/")
def create_submission(
    body: SubmissionCreate,
    db: DbSession,
    user: CurrentUser,
    wait: bool = False,
):
    problem = _visible_problem(db, body.problem_id, user)
    if not problem.test_cases:
        raise ApiError(409, "problem_has_no_tests", "The problem has no test cases.")
    submission = _reserve_submission(db, body, user.id)
    callback_tokens: dict[int, str] = {}
    results: dict[int, SubmissionCaseResult] = {}
    for test_case in problem.test_cases:
        callback_token = secrets.token_urlsafe(32)
        result = SubmissionCaseResult(
            submission_id=submission.id,
            test_case_id=test_case.id,
            callback_token_hash=hash_token(callback_token),
            judge0_status_id=Judge0Status.IN_QUEUE,
            test_case=test_case,
        )
        callback_tokens[test_case.id] = callback_token
        results[test_case.id] = result
        db.add(result)
    db.commit()
    for test_case in problem.test_cases:
        execution = build_case_execution(problem, test_case, body.source_code)
        result = results[test_case.id]
        try:
            data = judge0_submit(
                execution.source_code,
                body.language_id,
                execution.stdin,
                execution.expected_output,
                wait=wait,
                timeout=20.0 if wait else 5.0,
                callback_url=(
                    f"{settings.JUDGE0_CALLBACK_BASE_URL}/"
                    f"{callback_tokens[test_case.id]}"
                ),
                cpu_time_limit=float(problem.cpu_time_limit_seconds),
                memory_limit=problem.memory_limit_kb,
            )
            token = data["token"]
            db.refresh(result)
            if result.judge0_token is None:
                result.judge0_token = token
            if wait:
                _update_case_result(result, data)
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            _mark_case_infrastructure_error(db, submission.id, test_case.id)
            raise _judge0_error(error) from error
        db.commit()
    submission = _load_submission(db, submission.id)
    if submission is None:
        raise RuntimeError("submission disappeared while it was being graded")
    _finalize_submission(db, submission)
    db.commit()
    submission = _load_submission(db, submission.id)
    if submission is None:
        raise RuntimeError("submission disappeared after grading")
    return _submission_response(submission)


@router.get("/{submission_id}")
def get_submission(submission_id: int, db: DbSession, user: CurrentUser):
    submission = _load_submission(db, submission_id)
    if submission is not None and submission.student_id != user.id:
        submission = None
    if submission is None:
        raise ApiError(404, "submission_not_found", "Submission not found.")
    if submission.status not in TERMINAL_SUBMISSION_STATUSES:
        for result in submission.case_results:
            if _is_terminal(result.judge0_status_id):
                continue
            if result.judge0_token is None:
                raise RuntimeError("queued case has no Judge0 token")
            try:
                data = judge0_get(result.judge0_token)
                _update_case_result(result, data)
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
                db.rollback()
                raise _judge0_error(error) from error
        _finalize_submission(db, submission)
        db.commit()
        db.refresh(submission)
    return _submission_response(submission)


@internal_router.put("/callbacks/{callback_token}", include_in_schema=False)
def receive_judge0_callback(
    callback_token: str,
    data: dict,
    db: DbSession,
):
    result = db.scalar(
        select(SubmissionCaseResult).where(
            SubmissionCaseResult.callback_token_hash == hash_token(callback_token)
        )
    )
    if result is None:
        raise HTTPException(status_code=404, detail="callback not found")
    submission = _load_submission(db, result.submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="submission not found")
    result = db.scalar(
        select(SubmissionCaseResult)
        .where(
            SubmissionCaseResult.submission_id == result.submission_id,
            SubmissionCaseResult.test_case_id == result.test_case_id,
        )
        .with_for_update()
    )
    if result is None:
        raise HTTPException(status_code=404, detail="callback not found")
    reported_token = data.get("token")
    if reported_token is not None and (
        not isinstance(reported_token, str) or len(reported_token) > 36
    ):
        raise HTTPException(status_code=400, detail="invalid Judge0 token")
    if (
        reported_token is not None
        and result.judge0_token is not None
        and reported_token != result.judge0_token
    ):
        raise HTTPException(status_code=409, detail="callback token mismatch")
    if reported_token is not None:
        result.judge0_token = reported_token
    try:
        report = dict(data)
        for field in ("stdout", "stderr", "compile_output"):
            if report.get(field) is not None:
                if not isinstance(report[field], str):
                    raise TypeError("Judge0 callback text must be a Base64 string")
                report[field] = base64.b64decode(
                    "".join(report[field].split()), validate=True
                ).decode("utf-8", errors="replace")
        _update_case_result(result, report)
    except (TypeError, ValueError, ArithmeticError) as error:
        db.rollback()
        raise HTTPException(status_code=400, detail="invalid Judge0 report") from error
    _finalize_submission(db, submission)
    db.commit()
    return {"ok": True}


def _course_item_ids(db: Session, course_id: int) -> list[int]:
    return list(
        db.scalars(
            select(AssignmentItem.id)
            .join(Assignment, Assignment.id == AssignmentItem.assignment_id)
            .where(Assignment.course_id == course_id)
        ).all()
    )


def _staff_submission_response(submission: Submission) -> dict:
    response = _submission_response(submission)
    cases = []
    for result in submission.case_results:
        case = {
            "test_case_id": result.test_case_id,
            "case_order": result.test_case.case_order,
            "visibility": result.test_case.visibility,
            "status_id": result.judge0_status_id,
            "friendly_message": (
                get_status_message(result.judge0_status_id)
                if result.judge0_status_id is not None
                else get_status_message(Judge0Status.IN_QUEUE)
            ),
            "execution_time_ms": result.execution_time_ms,
            "memory_kb": result.memory_kb,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "compile_output": result.compile_output,
        }
        if result.test_case.visibility == TestVisibility.PUBLIC:
            case["input"] = result.test_case.input
            case["expected_output"] = result.test_case.expected_output
        cases.append(case)
    response.update(
        {
            "student_id": submission.student_id,
            "problem_id": submission.problem_id,
            "assignment_item_id": submission.assignment_item_id,
            "source_code": submission.source_code,
            "primary_error": submission.primary_error,
            "python_exception_type": submission.python_exception_type,
            "submitted_at": submission.submitted_at,
            "completed_at": submission.completed_at,
            "cases": cases,
        }
    )
    return response


def _staff_submission_query(db: Session, course_id: int):
    item_ids = _course_item_ids(db, course_id)
    return (
        select(Submission)
        .options(
            selectinload(Submission.case_results).selectinload(
                SubmissionCaseResult.test_case
            )
        )
        .where(Submission.assignment_item_id.in_(item_ids) if item_ids else False)
        .order_by(Submission.id.desc())
    )


@course_router.get("")
def list_course_submissions(
    course_id: int,
    db: DbSession,
    _staff: StaffMembership,
    student_id: int | None = None,
    problem_id: int | None = None,
    assignment_id: int | None = None,
    status: SubmissionStatus | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    if student_id is not None:
        get_membership(db, course_id, student_id)
    query = _staff_submission_query(db, course_id)
    if student_id is not None:
        query = query.where(Submission.student_id == student_id)
    if problem_id is not None:
        query = query.where(Submission.problem_id == problem_id)
    if assignment_id is not None:
        query = query.where(
            Submission.assignment_item_id.in_(
                select(AssignmentItem.id).where(
                    AssignmentItem.assignment_id == assignment_id
                )
            )
        )
    if status is not None:
        query = query.where(Submission.status == status)
    submissions = list(db.scalars(query).unique().all())
    return {
        "items": [
            _staff_submission_response(item)
            for item in submissions[offset : offset + limit]
        ],
        "total": len(submissions),
        "limit": limit,
        "offset": offset,
    }


@course_router.get("/{submission_id}")
def get_course_submission(
    course_id: int,
    submission_id: int,
    db: DbSession,
    _staff: StaffMembership,
):
    # DB-only read: unlike the student view, staff inspection never polls
    # Judge0 and never finalizes, so it performs no writes.
    submission = db.scalar(
        select(Submission)
        .options(
            selectinload(Submission.case_results).selectinload(
                SubmissionCaseResult.test_case
            )
        )
        .where(Submission.id == submission_id)
    )
    if (
        submission is None
        or submission.assignment_item_id is None
        or submission.assignment_item_id not in _course_item_ids(db, course_id)
    ):
        raise ApiError(404, "submission_not_found", "Submission not found.")
    return _staff_submission_response(submission)


@course_router.post("/{submission_id}/approve-late")
def approve_late_submission(
    course_id: int,
    submission_id: int,
    db: DbSession,
    membership: InstructorMembership,
):
    submission = db.scalar(select(Submission).where(Submission.id == submission_id))
    if (
        submission is None
        or submission.assignment_item_id is None
        or submission.assignment_item_id not in _course_item_ids(db, course_id)
    ):
        raise ApiError(404, "submission_not_found", "Submission not found.")
    if not submission.is_late:
        raise ApiError(409, "not_late", "Only late submissions need late approval.")
    if submission.late_approved_at is None:
        submission.late_approved_at = datetime.now(UTC).replace(tzinfo=None)
        submission.late_approved_by_membership_id = membership.id
        db.commit()
        recompute_assignment_grade(
            db, submission.student_id, submission.assignment_item_id
        )
        db.commit()
    return _staff_submission_response(
        db.scalar(
            select(Submission)
            .options(
                selectinload(Submission.case_results).selectinload(
                    SubmissionCaseResult.test_case
                )
            )
            .where(Submission.id == submission_id)
        )
    )
