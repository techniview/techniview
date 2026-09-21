from datetime import UTC, datetime
from decimal import Decimal
from enum import IntEnum

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..core.dependencies import CurrentUser, DbSession
from ..core.errors import ApiError
from ..core.judge0 import judge0_get, judge0_submit
from ..models import (
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
    require_assigned_item,
)
from .problems import _visible_problem

router = APIRouter(prefix="/submissions", tags=["submissions"])


class SubmissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_code: str = Field(min_length=1, max_length=65536)
    language_id: int = Field(default=71, gt=0)
    problem_id: int = Field(gt=0)
    assignment_item_id: int | None = Field(default=None, gt=0)

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


def _update_case_result(case_result: SubmissionCaseResult, data: dict) -> None:
    status = data.get("status") or {}
    status_id = status.get("id")
    if status_id is not None:
        case_result.judge0_status_id = int(status_id)
        case_result.infrastructure_error = int(status_id) == Judge0Status.INTERNAL_ERROR


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
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return submission


def _mark_infrastructure_error(db: Session, submission_id: int) -> None:
    db.rollback()
    submission = db.get(Submission, submission_id)
    if submission is None:
        return
    submission.status = SubmissionStatus.INFRASTRUCTURE_ERROR
    submission.completed_at = datetime.now(UTC).replace(tzinfo=None)
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
    for test_case in problem.test_cases:
        execution = build_case_execution(problem, test_case, body.source_code)
        try:
            data = judge0_submit(
                execution.source_code,
                body.language_id,
                execution.stdin,
                execution.expected_output,
                wait=wait,
                timeout=20.0 if wait else 5.0,
                cpu_time_limit=float(problem.cpu_time_limit_seconds),
                memory_limit=problem.memory_limit_kb,
            )
            token = data["token"]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            _mark_infrastructure_error(db, submission.id)
            raise _judge0_error(error) from error
        result = SubmissionCaseResult(
            submission_id=submission.id,
            test_case_id=test_case.id,
            judge0_token=token,
            test_case=test_case,
        )
        if wait:
            _update_case_result(result, data)
        else:
            result.judge0_status_id = Judge0Status.IN_QUEUE
        submission.case_results.append(result)
    db.flush()
    db.refresh(submission)
    _finalize_submission(db, submission)
    db.commit()
    db.refresh(submission)
    return _submission_response(submission)


@router.get("/{submission_id}")
def get_submission(submission_id: int, db: DbSession, user: CurrentUser):
    submission = db.scalar(
        select(Submission)
        .options(
            selectinload(Submission.case_results).selectinload(
                SubmissionCaseResult.test_case
            )
        )
        .where(
            Submission.id == submission_id,
            Submission.student_id == user.id,
        )
        .with_for_update()
    )
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
