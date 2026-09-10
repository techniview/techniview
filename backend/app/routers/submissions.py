from enum import Enum
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from ..core.judge0 import judge0_get, judge0_submit

router = APIRouter(prefix="/submissions", tags=["submissions"])

# TODO: add auth, attach user and problem before Judge0
# TODO: store source, language, token, user in MySQL


class SubmissionCreate(BaseModel):
    source_code: str = Field(min_length=1, max_length=65536)
    language_id: int = Field(default=71, gt=0)  # default to python
    stdin: str | None = Field(default=None, max_length=65536)
    expected_output: str | None = Field(default=None, max_length=65536)
    problem_id: int | None = None
    cpu_time_limit: float | None = Field(default=None, gt=0, le=15)
    memory_limit: int | None = Field(default=None, gt=0, le=262144)

    @field_validator("language_id")
    @classmethod
    def _python_only(cls, value: int) -> int:
        # Python only for now. Reject other ids instead of passing them through.
        if value != 71:
            raise ValueError("only Python (language_id=71) is supported")
        return value


# weirdly, judge0 has an endpoint to return these. idk why. docs:
# https://ce.judge0.com/#statuses-and-languages-status
class SubmissionStatus(int, Enum):
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
    status_code = int(status_code)
    match status_code:
        case 1:
            return "In queue. Waiting for a worker."
        case 2:
            return "Running your code."
        case 3:
            return "Accepted. Nice work!"
        case 4:
            return "Wrong answer. Output did not match expected."
        case 5:
            return "Time limit exceeded. Check for an infinite loop or a slower step."
        case 6:
            return "Compilation error. Check your syntax."
        case 7:
            return "Crashed. Segmentation fault."
        case 8:
            return "Crashed. Output file too large."
        case 9:
            return "Crashed. Low-level fault (SIGFPE)."
        case 10:
            return "Crashed. Program aborted."
        case 11:
            return "Runtime error. Program exited with an error. Check stderr for the \
                    Python traceback."
        case 12:
            return "Runtime error. Something went wrong while running."
        case 13:
            return "Internal error. Our runner hit a problem. Try again."
        case 14:
            return "Exec format error. Runner could not start your program."
        case _:
            # catch-all in case we forget to update this function when Judge0 adds
            # new status codes
            return f"Unknown status code: {status_code}"


def _enrich_result(data: dict) -> dict:
    # copy so cached objects are never mutated, add done and friendly text
    # so the UI has one stable shape to render
    enriched = dict(data)
    status = enriched.get("status") or {}
    status_id = status.get("id")
    if status_id is None:
        enriched["done"] = False
        enriched["friendly_message"] = get_status_message(SubmissionStatus.IN_QUEUE)
    else:
        enriched["done"] = int(status_id) >= SubmissionStatus.ACCEPTED
        enriched["friendly_message"] = get_status_message(status_id)
    token = enriched.get("token")
    if token and "poll_url" not in enriched:
        enriched["poll_url"] = f"/api/submissions/{token}"
    return enriched


def _validate_token(token: str) -> str:
    # judge0 tokens are UUIDs. Reject junk before it reaches the runner URL
    try:
        return str(UUID(token))
    except ValueError:
        raise HTTPException(
            status_code=422, detail="invalid submission token"
        ) from None


def _judge0_error(e: Exception) -> HTTPException:
    # map transport failures to status codes without leaking internals
    if isinstance(e, httpx.TimeoutException):
        return HTTPException(status_code=504, detail="runner timed out")
    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code if e.response is not None else None
        if status == 429:
            return HTTPException(status_code=429, detail="runner busy, try again")
        return HTTPException(status_code=502, detail="runner unavailable")
    return HTTPException(status_code=502, detail="runner unavailable")


@router.post("")
@router.post("/")
def create_submission(body: SubmissionCreate, wait: bool = False):
    # TODO: log result to MySQL
    # TODO: enforce per-problem cpu_time_limit/memory_limit from problem config
    extra: dict = {}
    if body.cpu_time_limit is not None:
        extra["cpu_time_limit"] = body.cpu_time_limit
    if body.memory_limit is not None:
        extra["memory_limit"] = body.memory_limit
    try:
        data = judge0_submit(
            body.source_code,
            body.language_id,
            body.stdin,
            body.expected_output,
            wait=wait,
            timeout=20.0 if wait else 5.0,
            **extra,
        )
    except Exception as e:
        raise _judge0_error(e) from e

    # wait=false returns token only, so synthesize queued status for one shape.
    if "status" not in data and "token" in data:
        data["status"] = {"id": 1, "description": "In Queue"}
        data["poll_url"] = f"/api/submissions/{data['token']}"
    return _enrich_result(data)


@router.get("/{token}")
def get_submission(token: str):
    token = _validate_token(token)
    try:
        return _enrich_result(judge0_get(token))
    except Exception as e:
        raise _judge0_error(e) from e


# TODO: GET /submissions?user_id=&problem_id= - list history from MySQL
