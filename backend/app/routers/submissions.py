from enum import Enum

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core.judge0 import judge0_get, judge0_submit

router = APIRouter(prefix="/submissions", tags=["submissions"])

# TODO: add auth, attach user and problem before Judge0
# TODO: store source, language, token, user in MySQL


class SubmissionCreate(BaseModel):
    source_code: str
    language_id: int = 71  # TODO: validate against Judge0 /languages
    stdin: str | None = None
    expected_output: str | None = None
    problem_id: int | None = None
    cpu_time_limit: float | None = None
    memory_limit: int | None = None


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


def _judge0_error(e: Exception) -> HTTPException:
    # TODO: strip internals from detail before any prod use
    return HTTPException(status_code=502, detail=f"judge0 error: {e}")


@router.post("")
@router.post("/")
def create_submission(body: SubmissionCreate, wait: bool = False):
    # TODO: if wait=false, return token and let frontend poll GET /{token}
    # TODO: if wait=true, proxy sync and also log result to MySQL
    # TODO: enforce per-problem cpu_time_limit/memory_limit from problem config
    extra: dict = {}
    if body.cpu_time_limit is not None:
        extra["cpu_time_limit"] = body.cpu_time_limit
    if body.memory_limit is not None:
        extra["memory_limit"] = body.memory_limit
    try:
        return judge0_submit(
            body.source_code,
            body.language_id,
            body.stdin,
            body.expected_output,
            wait=wait,
            **extra,
        )
    except Exception as e:
        raise _judge0_error(e) from e


@router.get("/{token}")
def get_submission(token: str):
    # TODO: also fetch cached result from MySQL if available
    try:
        return judge0_get(token)
    except Exception as e:
        raise _judge0_error(e) from e


# TODO: GET /submissions?user_id=&problem_id= - list history from MySQL
