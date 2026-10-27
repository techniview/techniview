"""Exercise the test-only shared interpreter through the real runner."""

import os
import time
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from app.models import ExecutionMode
from app.services.execution import build_shared_execution

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1"
    or os.getenv("RUNNER_GROUP_PROFILE") != "1"
    or os.getenv("RUNNER_EXECUTION_MODEL") != "shared_python",
    reason="requires the disposable shared Python runner profile",
)


@pytest.mark.parametrize("fatal", [False, True])
def test_shared_group_preserves_state_and_marks_unrun(fatal):
    problem = SimpleNamespace(
        execution_mode=ExecutionMode.CALL_BASED,
        function_name="solve",
        starter_code="def solve(value): pass",
        tags=[],
    )
    source = (
        "import os\ncount = 0\n"
        "def solve(value):\n"
        "    global count\n"
        "    count += 1\n"
        "    if value == 2 and " + str(fatal) + ": os._exit(7)\n"
        "    return [value, count]\n"
    )
    prepared = [
        SimpleNamespace(input=f"[{index}]", expected_output="hidden")
        for index in (1, 2, 3)
    ]
    script = build_shared_execution(problem, prepared, source)
    assert "hidden" not in script
    cases = [
        {
            "case_id": index,
            "source_code": source,
            "expected_output": f"[{index},{index}]\n",
            "shared_input": case.input,
        }
        for index, case in enumerate(prepared, 1)
    ]
    with httpx.Client(base_url="http://judge:2358", timeout=15) as runner:
        response = runner.post(
            "/internal/submission-groups",
            json={
                "idempotency_key": uuid4().hex,
                "execution_model": "shared_python",
                "shared_script": script,
                "cases": cases,
            },
        )
        assert response.status_code == 201, response.text
        group = response.json()
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            state = runner.get(f"/internal/submission-groups/{group['token']}").json()
            if state["state"] == "complete":
                reports = [
                    runner.get(
                        f"/submissions/{item['token']}?base64_encoded=false"
                    ).json()
                    for item in group["cases"]
                ]
                if fatal:
                    assert state["termination"] == "fatal", state
                    assert [report["status"]["id"] for report in reports] == [
                        3,
                        11,
                        13,
                    ], reports
                    assert reports[2]["execution_unrun"] is True
                else:
                    assert state["termination"] == "complete", state
                    assert [report["status"]["id"] for report in reports] == [
                        3,
                        3,
                        3,
                    ], reports
                return
            time.sleep(0.2)
        pytest.fail(f"shared group did not complete: {state}")
