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
