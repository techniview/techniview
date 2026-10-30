"""Direct sandbox execution; expected output and grading stay in TechniView."""

import math
from dataclasses import dataclass

import httpx

from .config import settings
from .runner_http import request_client


class OutcomeUnknown(Exception):
    pass


@dataclass(frozen=True)
class Execution:
    source: str
    stdin: str | None
    expected: str
    cpu_seconds: float
    memory_kb: int


def execute(case: Execution) -> dict:
    output_limit = 1024 * 1024
    command = {
        "args": [
            "/usr/bin/prlimit",
            f"--fsize={output_limit}:{output_limit}",
            "--",
            "/opt/python/bin/python3.14",
            "-I",
            "-B",
            "script.py",
        ],
        "env": ["HOME=/tmp", "LANG=C.UTF-8"],
        "files": [
            {"content": case.stdin or ""},
            {"name": "stdout", "max": output_limit},
            {"name": "stderr", "max": output_limit},
        ],
        "copyIn": {"script.py": {"content": case.source}},
        "cpuLimit": int((case.cpu_seconds + 0.5) * 1_000_000_000),
        "clockLimit": settings.GO_JUDGE_WALL_SECONDS * 1_000_000_000,
        "memoryLimit": case.memory_kb * 1024,
        "strictMemoryLimit": True,
        "stackLimit": 64000 * 1024,
        "procLimit": 60,
    }
    try:
        with request_client() as client:
            response = client.post(
                f"{settings.GO_JUDGE_URL}/run",
                json={"cmd": [command]},
                timeout=settings.GO_JUDGE_WALL_SECONDS + 5,
            )
        response.raise_for_status()
        reports = response.json()
        if not isinstance(reports, list) or len(reports) != 1:
            raise ValueError("invalid sandbox response")
        return grade(case, reports[0], output_limit)
    except (httpx.HTTPError, ValueError, KeyError, TypeError, ArithmeticError) as error:
        # A transport or malformed-response error may occur after execution.
        raise OutcomeUnknown("sandbox execution outcome unknown") from error


def grade(case: Execution, report: dict, output_limit: int) -> dict:
    if not isinstance(report, dict) or not isinstance(report.get("files", {}), dict):
        raise ValueError("invalid execution report")
    for key in ("time", "runTime", "memory"):
        value = report[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError("invalid resource measurement")
    files = report.get("files", {})
    stdout, stderr = files.get("stdout", ""), files.get("stderr", "")
    if not isinstance(stdout, str) or not isinstance(stderr, str):
        raise ValueError("invalid output")
    status = report["status"]
    codes = {
        "Time Limit Exceeded": 5,
        "Memory Limit Exceeded": 12,
        "Output Limit Exceeded": 8,
        "Nonzero Exit Status": 11,
        "Dangerous Syscall": 12,
    }
    code = codes.get(status, 13)
    if status == "Signalled":
        code = {11: 7, 25: 8, 8: 9, 6: 10}.get(report["exitStatus"], 12)
    if status == "Accepted":
        code = 3 if normalize(stdout) == normalize(case.expected) else 4
        if report["time"] > case.cpu_seconds * 1_000_000_000:
            code = 5
        if len(stdout.encode()) > output_limit or len(stderr.encode()) > output_limit:
            code = 8
    return {
        "status": {"id": code},
        "stdout": stdout.encode()[:output_limit].decode("utf-8", errors="replace"),
        "stderr": stderr.encode()[:output_limit].decode("utf-8", errors="replace"),
        "time": report["time"] / 1_000_000_000,
        "memory": math.ceil(report["memory"] / 1024),
    }


def normalize(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.splitlines()).rstrip()
