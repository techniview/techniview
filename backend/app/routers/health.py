import time

from fastapi import APIRouter

from ..core.db import mysql_conn, postgres_conn
from ..core.judge0 import judge0_about, judge0_submit
from ..core.redis_client import redis_conn

router = APIRouter(prefix="/health", tags=["health"])


def check_mysql():
    try:
        t0 = time.time()
        with mysql_conn() as c:
            cur = c.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            cur.execute("SELECT VERSION()")
            ver = cur.fetchone()[0]
        return {
            "ok": True,
            "version": ver,
            "latency_ms": round((time.time() - t0) * 1000, 1),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def check_postgres():
    try:
        t0 = time.time()
        with postgres_conn() as c:
            cur = c.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            cur.execute("SELECT version()")
            ver = cur.fetchone()[0]
        return {
            "ok": True,
            "version": ver[:80],
            "latency_ms": round((time.time() - t0) * 1000, 1),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def check_redis():
    try:
        t0 = time.time()
        r = redis_conn()
        try:
            pong = r.ping()
            r.set("health:check", "ok", ex=10)
            val = r.get("health:check")
        finally:
            try:
                r.close()
            except Exception:
                pass
        return {
            "ok": bool(pong and val == "ok"),
            "ping": bool(pong),
            "latency_ms": round((time.time() - t0) * 1000, 1),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def check_judge0(deep: bool = False):
    # deep=False is fast (just /about). deep=True also runs a real submit.
    # TODO: /health should stay fast, keep deep checks on /health/judge0 only.
    try:
        t0 = time.time()
        data = judge0_about()
        if not deep:
            return {
                "ok": True,
                "version": data.get("version"),
                "submit_ok": None,
                "latency_ms": round((time.time() - t0) * 1000, 1),
            }
        sub = judge0_submit("print(42)", 71, wait=True)
        ok = sub.get("status", {}).get("id") == 3 and sub.get("stdout") == "42\n"
        return {
            "ok": ok,
            "version": data.get("version"),
            "submit_ok": ok,
            "latency_ms": round((time.time() - t0) * 1000, 1),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("")
@router.get("/")
def health(deep: bool = False):
    results = {
        "mysql": check_mysql(),
        "postgres": check_postgres(),
        "redis": check_redis(),
        "judge0": check_judge0(deep=deep),
    }
    return {"ok": all(v.get("ok") for v in results.values()), "services": results}


@router.get("/mysql")
def health_mysql():
    return check_mysql()


@router.get("/postgres")
def health_postgres():
    return check_postgres()


@router.get("/redis")
def health_redis():
    return check_redis()


@router.get("/judge0")
def health_judge0(deep: bool = True):
    return check_judge0(deep=deep)
