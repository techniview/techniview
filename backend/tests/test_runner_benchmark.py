import asyncio
from unittest.mock import patch

import httpx
import pytest
from app.core import judge0
from performance.load_test import _submit_once


def test_worker_connection_pool_closes_after_failure():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"token": "case-token"})

    client = httpx.Client(transport=httpx.MockTransport(respond))
    with patch.object(judge0.httpx, "Client", return_value=client) as factory:
        with pytest.raises(RuntimeError), judge0.managed_judge0_client():
            judge0.judge0_submit("print(1)", wait=False, timeout=7)
            judge0.judge0_get("case-token", timeout=2)
            assert not client.is_closed
            raise RuntimeError("worker failed")
        assert factory.call_count == 1
    assert client.is_closed
    assert judge0._worker_client.get() is None
    assert requests[0].extensions["timeout"]["read"] == 7
    assert requests[1].extensions["timeout"]["read"] == 2


def test_api_completion_is_polled_and_records_real_workload():
    seen = []

    def respond(request):
        seen.append(request)
        if request.method == "POST":
            return httpx.Response(202, json={"id": 42})
        return httpx.Response(
            200,
            json={
                "done": True,
                "status": "passed",
                "passed_count": 34,
                "test_count": 34,
                "submitted_at": "2026-10-25T12:00:00",
                "completed_at": "2026-10-25T12:00:01",
            },
        )

    async def run():
        observations = []
        gate = asyncio.Event()
        gate.set()
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(respond), base_url="http://test"
        ) as api:
            result = await _submit_once(
                api,
                "test-token",
                1,
                2,
                gate,
                "def real_solution(): pass",
                observations,
            )
        assert result[0] == 42
        assert observations[0]["api_completion_seconds"] >= result[1]
        assert observations[0]["test_count"] == 34
        assert all(
            request.headers["cookie"].endswith("=test-token") for request in seen
        )
        assert len(seen) == 2
        assert seen[1].url.path == "/api/submissions/42"
        assert b"def real_solution(): pass" in seen[0].content

    asyncio.run(run())


def test_host_memory_guard_requires_continuous_pressure():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).parents[2] / "scripts/runner_benchmark_support.py"
    spec = importlib.util.spec_from_file_location("runner_benchmark_support", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    low = {"available_bytes": 1024**3, "swap_used_bytes": 0}
    healthy = {"available_bytes": 3 * 1024**3, "swap_used_bytes": 0}
    reason, since = module.stop_reason(0, low, 0, None)
    assert reason is None and since == 0
    reason, since = module.stop_reason(0, low, 4.9, since)
    assert reason is None
    reason, since = module.stop_reason(0, healthy, 5, since)
    assert reason is None and since is None
    reason, since = module.stop_reason(0, low, 6, since)
    reason, since = module.stop_reason(0, low, 11, since)
    assert reason == "available memory below 2 GiB for five seconds"
    healthy["swap_used_bytes"] = 512 * 1024**2
    assert module.stop_reason(0, healthy, 12, None)[0] is None
    healthy["swap_used_bytes"] += 1
    assert module.stop_reason(0, healthy, 12, None)[0] == "swap growth exceeded 512 MiB"


@pytest.mark.parametrize(
    "title", ["Ransom Note", "Number of Islands", "Minimum Cost for Tickets"]
)
def test_complete_catalog_workloads_through_execution_wrapper(title):
    import json
    import subprocess
    import sys
    from pathlib import Path
    from types import SimpleNamespace

    from app.models import ExecutionMode
    from app.services.execution import build_case_execution

    catalog = json.loads(
        (Path(__file__).parents[1] / "data/problem_catalog.json").read_text()
    )
    workload = next(
        problem for problem in catalog["problems"] if problem["title"] == title
    )
    problem = SimpleNamespace(
        execution_mode=ExecutionMode(workload["execution_mode"]),
        function_name=workload["function_name"],
        starter_code=workload["starter_code"],
        tags=[],
    )
    for index, case in enumerate(workload["test_cases"], 1):
        execution = build_case_execution(
            problem, SimpleNamespace(**case), workload["canonical_solution"]
        )
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", execution.source_code],
            input=execution.stdin,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        assert json.loads(result.stdout) == json.loads(execution.expected_output), (
            title,
            index,
            result.stdout,
        )


def test_disconnected_result_poll_is_recorded_without_resubmitting(capsys):
    requests = []

    def respond(request):
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(202, json={"id": 42})
        if len(requests) == 2:
            raise httpx.RemoteProtocolError("Server disconnected")
        return httpx.Response(
            200,
            json={
                "done": True,
                "status": "passed",
                "passed_count": 34,
                "test_count": 34,
                "submitted_at": "2026-10-25T12:00:00",
                "completed_at": "2026-10-25T12:00:01",
            },
        )

    async def run():
        observations = []
        gate = asyncio.Event()
        gate.set()
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(respond), base_url="http://test"
        ) as api:
            result = await _submit_once(
                api, "token", 1, 2, gate, "print(1)", observations
            )
        assert result[0] == 42
        assert observations[0]["result_poll_transport_error_count"] == 1
        assert observations[0]["api_completion_seconds"] >= 0.2
        assert [r.method for r in requests] == ["POST", "GET", "GET"]

    asyncio.run(run())
    assert '"event": "result_poll_transport_error"' in capsys.readouterr().out


def test_result_poll_http_errors_are_not_retried():
    requests = []

    def respond(request):
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(202, json={"id": 42})
        return httpx.Response(500)

    async def run():
        gate = asyncio.Event()
        gate.set()
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(respond), base_url="http://test"
        ) as api:
            with pytest.raises(httpx.HTTPStatusError):
                await _submit_once(api, "token", 1, 2, gate)
        assert [r.method for r in requests] == ["POST", "GET"]

    asyncio.run(run())


def test_resume_retains_complete_pairs(tmp_path):
    import importlib.util
    import json
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "benchmark_support",
        Path(__file__).parents[2] / "scripts/runner_benchmark_support.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for variant in ["baseline", "combined"]:
        directory = tmp_path / f"c10-r1-{variant}"
        directory.mkdir()
        (directory / "summary.json").write_text(json.dumps({"complete": True}))
    assert module.prepare_pair(tmp_path, "c10-r1", "combined", tmp_path / "archive")
    assert not (tmp_path / "archive").exists()


def test_resume_archives_both_sides_of_partial_pair(tmp_path):
    import importlib.util
    import json
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "benchmark_support",
        Path(__file__).parents[2] / "scripts/runner_benchmark_support.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    baseline = tmp_path / "c10-r1-baseline"
    baseline.mkdir()
    (baseline / "summary.json").write_text(json.dumps({"complete": True}))
    partial = tmp_path / "c10-r1-combined"
    partial.mkdir()
    (partial / "output.txt").write_text("accepted but interrupted")
    warmup = tmp_path / "c10-r1-combined-warmup"
    warmup.mkdir()
    archive = tmp_path / "archive"
    assert not module.prepare_pair(tmp_path, "c10-r1", "combined", archive)
    assert not baseline.exists() and not partial.exists() and not warmup.exists()
    assert (
        archive / partial.name / "output.txt"
    ).read_text() == "accepted but interrupted"
    assert json.loads((archive / baseline.name / "summary.json").read_text())[
        "complete"
    ]
