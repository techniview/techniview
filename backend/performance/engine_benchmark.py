"""Compare canonical prepared cases using explicit, identical execution limits."""

import asyncio
import json
import os
import statistics
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
from app.models import ExecutionMode
from app.services.execution import build_case_execution

LIMITS = {
    "cpu_time_limit": 2,
    "cpu_extra_time": 0,
    "wall_time_limit": 5,
    "memory_limit": 128000,
    "stack_limit": 64000,
    "max_processes_and_or_threads": 60,
    "max_file_size": 1024,
}

FILE_LIMIT_BYTES = LIMITS["max_file_size"] * 1024


async def run():
    engine = os.environ["ENGINE_BENCHMARK_ENGINE"]
    title = os.environ["LOAD_PROBLEM"]
    catalog = json.loads(
        (Path(__file__).parents[1] / "data/problem_catalog.json").read_text()
    )
    workload = next(p for p in catalog["problems"] if p["title"] == title)
    problem = SimpleNamespace(
        **{
            **workload,
            "execution_mode": ExecutionMode(workload["execution_mode"]),
            "tags": [],
        }
    )
    cases = [
        build_case_execution(
            problem, SimpleNamespace(**case), workload["canonical_solution"]
        )
        for case in workload["test_cases"]
    ]
    semaphore = asyncio.Semaphore(int(os.environ["LOAD_CONCURRENCY"]))
    async with httpx.AsyncClient(timeout=30) as client:

        async def execute(index, case):
            async with semaphore:
                started = time.perf_counter()
                if engine == "isolate":
                    response = await client.post(
                        "http://judge:2358/submissions?base64_encoded=false",
                        json={
                            "source_code": case.source_code,
                            "stdin": case.stdin or "",
                            **LIMITS,
                        },
                    )
                    response.raise_for_status()
                    token = response.json()["token"]
                    while True:
                        response = await client.get(
                            f"http://judge:2358/submissions/{token}?base64_encoded=false"
                            "&fields=token,time,memory,wall_time,stdout,stderr,status"
                        )
                        response.raise_for_status()
                        report = response.json()
                        if report["status"]["id"] not in (1, 2):
                            break
                        await asyncio.sleep(0.2)
                    assert report["status"]["id"] == 3, report
                    stdout = report["stdout"]
                    cpu, wall, memory = (
                        float(report["time"]),
                        float(report["wall_time"]),
                        report["memory"] * 1024,
                    )
                else:
                    response = await client.post(
                        "http://go-judge:5050/run",
                        json={
                            "cmd": [
                                {
                                    "args": [
                                        "/usr/bin/prlimit",
                                        f"--fsize={FILE_LIMIT_BYTES}:{FILE_LIMIT_BYTES}",
                                        "--",
                                        "/opt/python/bin/python3.14",
                                        "-I",
                                        "-B",
                                        "script.py",
                                    ],
                                    "env": ["HOME=/tmp", "LANG=C.UTF-8"],
                                    "files": [
                                        {"content": case.stdin or ""},
                                        {
                                            "name": "stdout",
                                            "max": LIMITS["max_file_size"] * 1024,
                                        },
                                        {
                                            "name": "stderr",
                                            "max": LIMITS["max_file_size"] * 1024,
                                        },
                                    ],
                                    "copyIn": {
                                        "script.py": {"content": case.source_code}
                                    },
                                    "cpuLimit": int(LIMITS["cpu_time_limit"] * 1e9),
                                    "clockLimit": int(LIMITS["wall_time_limit"] * 1e9),
                                    "memoryLimit": LIMITS["memory_limit"] * 1024,
                                    "stackLimit": LIMITS["stack_limit"] * 1024,
                                    "procLimit": LIMITS["max_processes_and_or_threads"],
                                }
                            ]
                        },
                    )
                    response.raise_for_status()
                    report = response.json()[0]
                    assert report["status"] == "Accepted", report
                    stdout = report["files"]["stdout"]
                    cpu, wall, memory = (
                        report["time"] / 1e9,
                        report["runTime"] / 1e9,
                        report["memory"],
                    )
                assert json.loads(stdout) == json.loads(case.expected_output), (
                    index,
                    stdout,
                )
                sample = {
                    "case_order": index,
                    "request_to_result_seconds": time.perf_counter() - started,
                    "execution_cpu_seconds": cpu,
                    "execution_wall_seconds": wall,
                    "memory_bytes": memory,
                }
                print(json.dumps({"event": "case_completed", **sample}), flush=True)
                return sample

        started = time.perf_counter()
        async with asyncio.timeout(300):
            samples = await asyncio.gather(
                *(execute(i, case) for i, case in enumerate(cases, 1))
            )
        report = {
            "engine": engine,
            "workload": title,
            "limits": LIMITS,
            "samples": samples,
            "count": len(samples),
            "batch_seconds": time.perf_counter() - started,
            "execution_cpu_p50": statistics.median(
                s["execution_cpu_seconds"] for s in samples
            ),
            "execution_wall_p50": statistics.median(
                s["execution_wall_seconds"] for s in samples
            ),
            "case_api_p50": statistics.median(
                s["request_to_result_seconds"] for s in samples
            ),
        }
        print(json.dumps(report), flush=True)


if __name__ == "__main__":
    asyncio.run(run())
