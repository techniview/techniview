"""Exercise the submission group through the real runner."""

import os
import time
from uuid import uuid4

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1",
    reason="requires the disposable group runner profile",
)


def test_group_is_idempotent_and_keeps_fresh_case_state():
    key = uuid4().hex
    cases = [
        {
            "case_id": 11,
            "source_code": (
                "import collections\n"
                "collections.techniview_group_marker = True\n"
                "open('/tmp/group-marker', 'w').write('first')\n"
                "print('first')\n"
            ),
            "expected_output": "first\n",
        },
        {
            "case_id": 12,
            "source_code": (
                "import collections, os\n"
                "assert not hasattr(collections, 'techniview_group_marker')\n"
                "assert not os.path.exists('/tmp/group-marker')\n"
                "print('second')\n"
            ),
            "expected_output": "second\n",
        },
    ]
    with httpx.Client(base_url="http://judge:2358", timeout=20) as runner:
        created = runner.post(
            "/internal/submission-groups",
            json={"idempotency_key": key, "cases": cases},
        )
        assert created.status_code == 201, created.text
        group = created.json()
        assert [case["case_id"] for case in group["cases"]] == [11, 12]
        repeated = runner.post(
            "/internal/submission-groups",
            json={"idempotency_key": key, "cases": cases},
        )
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["token"] == group["token"]
        conflict = runner.post(
            "/internal/submission-groups",
            json={"idempotency_key": key, "cases": cases[:1]},
        )
        assert conflict.status_code == 409, conflict.text
        by_key = runner.get(f"/internal/submission-groups/by-key/{key}")
        assert by_key.status_code == 200
        assert by_key.json()["token"] == group["token"]

        deadline = time.monotonic() + 90
        reports = []
        final = {}
        while time.monotonic() < deadline:
            reports = [
                runner.get(
                    f"/submissions/{item['token']}?base64_encoded=false",
                    timeout=5,
                ).json()
                for item in group["cases"]
            ]
            final = runner.get(f"/internal/submission-groups/{group['token']}").json()
            if (
                all(report["status"]["id"] not in {1, 2} for report in reports)
                and final["state"] == "complete"
            ):
                assert [report["status"]["id"] for report in reports] == [3, 3]
                assert [report["stdout"] for report in reports] == [
                    "first\n",
                    "second\n",
                ]
                return
            time.sleep(0.2)
        pytest.fail(
            f"group did not complete: state={final.get('state')}, reports={reports}"
        )


@pytest.mark.skipif(
    os.getenv("RUNNER_RESTART_TEST") != "1",
    reason="requires the host-controlled go-judge restart verifier",
)
def test_worker_restart_does_not_retry_ambiguous_group_case():
    key = uuid4().hex
    cases = [
        {
            "case_id": 21,
            "source_code": (
                "import time\ntime.sleep(15)\nprint('finished-after-restart')\n"
            ),
            "expected_output": "finished-after-restart\n",
            "wall_time_limit": 20,
        }
    ]
    with httpx.Client(base_url="http://judge:2358", timeout=10) as runner:
        created = runner.post(
            "/internal/submission-groups",
            json={"idempotency_key": key, "cases": cases},
        )
        assert created.status_code == 201, created.text
        group = created.json()

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            state = runner.get(f"/internal/submission-groups/{group['token']}").json()
            if state["state"] == "running" and state["cases"][0]["state"] == "running":
                # Allow the Go Judge request to reach the executing worker before the
                # host verifier interrupts that worker container.
                time.sleep(1.5)
                print("GO_JUDGE_RESTART_READY", flush=True)
                break
            time.sleep(0.1)
        else:
            pytest.fail(f"group never entered execution: {state}")

        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            final = runner.get(f"/internal/submission-groups/{group['token']}").json()
            report = runner.get(
                f"/submissions/{group['cases'][0]['token']}?base64_encoded=false"
            ).json()
            if final["state"] == "complete":
                break
            time.sleep(0.2)
        else:
            pytest.fail(f"group did not recover after engine restart: {final}")

        assert report["status"]["description"] == "Internal Error", report
        assert report["message"] == "runner_outcome_unknown", report

        repeated = runner.post(
            "/internal/submission-groups",
            json={"idempotency_key": key, "cases": cases},
        )
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["token"] == group["token"]
        assert repeated.json()["state"] == "complete"
        time.sleep(2)
        final_report = runner.get(
            f"/submissions/{group['cases'][0]['token']}?base64_encoded=false"
        ).json()
        assert final_report["status"]["description"] == "Internal Error"
        assert final_report["message"] == "runner_outcome_unknown"
