import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..core.config import settings
from ..core.db import mysql_conn

router = APIRouter(prefix="/health", tags=["health"])
HEALTH_CHECK_TIMEOUT_SECONDS = 3


def mysql_is_available() -> bool:
    try:
        with mysql_conn() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                return cursor.fetchone() == (1,)
    except Exception:
        return False


def judge0_is_available() -> bool:
    try:
        with httpx.Client(timeout=HEALTH_CHECK_TIMEOUT_SECONDS) as client:
            response = client.get(f"{settings.JUDGE0_URL}/about")
            response.raise_for_status()
        return True
    except httpx.HTTPError:
        return False


def _response(ok: bool):
    return JSONResponse(
        {"ok": ok},
        status_code=200 if ok else 503,
    )


@router.get("")
@router.get("/")
def health():
    return _response(mysql_is_available() and judge0_is_available())


@router.get("/ready")
def readiness():
    return _response(mysql_is_available())


@router.get("/mysql")
def health_mysql():
    return _response(mysql_is_available())


@router.get("/judge0")
def health_judge0():
    return _response(judge0_is_available())
