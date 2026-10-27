"""Create or verify one execution interrupted by an engine-service restart."""

import json
import sys
import time

import httpx


def main():
    with httpx.Client(base_url="http://judge:2358", timeout=10) as client:
        if sys.argv[1] == "start":
            response = client.post(
                "/submissions?base64_encoded=false",
                json={
                    "source_code": (
                        "import time\n"
                        "from pathlib import Path\n"
                        "Path('/tmp/techniview-execution-started').write_text('started')\n"
                        "time.sleep(15)\nprint('completed')\n"
                    ),
                    "cpu_time_limit": 2,
                    "wall_time_limit": 20,
                },
            )
            response.raise_for_status()
            print(response.json()["token"], flush=True)
            return
        token = sys.argv[2]
        deadline = time.monotonic() + 30
        while True:
            response = client.get(f"/submissions/{token}?base64_encoded=false")
            response.raise_for_status()
            result = response.json()
            if result["status"]["id"] not in (1, 2):
                assert result["status"]["id"] == 13, result
                assert (
                    result.get("infrastructure_error_code") == "runner_outcome_unknown"
                ), result
                break
            assert time.monotonic() < deadline, result
            time.sleep(0.2)
        time.sleep(1)
        assert client.get(f"/submissions/{token}?base64_encoded=false").json() == result
        print(
            json.dumps(
                {
                    "event": "interrupted_execution_final",
                    "token": token,
                    "status": result["status"],
                    "message": result.get("message"),
                }
            )
        )


if __name__ == "__main__":
    main()
