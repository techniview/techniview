"""Exercise the real runner, never a mocked sandbox.

Requires INTEGRATION_TESTS=1 and a disposable runner API/worker/database stack.
The worker needs actual Linux namespaces, writable delegated cgroup v2 memory
controllers, and kernel >=5.19 for memory accounting. Failures on unsupported
hosts must not be treated as evidence that isolation works. RUNNER_TEST_URL can
point to a separately provisioned disposable runner instead of compose DNS.
"""

import os
import time

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="requires isolated integration stack"
)


@pytest.fixture(scope="module")
def runner():
    url = os.getenv("RUNNER_TEST_URL", "http://judge:2358")
    with httpx.Client(base_url=url, timeout=45) as client:
        deadline = time.monotonic() + 90
        while True:
            try:
                client.get("/about", timeout=5).raise_for_status()
                break
            except httpx.HTTPError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(1)
        yield client


def submit(runner, source, **fields):
    response = runner.post(
        "/submissions?base64_encoded=false&wait=true",
        json={"source_code": source, **fields},
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["status"]["id"] not in {1, 2, 13}, result
    return result


def test_python_standard_library(runner):
    result = submit(
        runner,
        "import json, math, sqlite3, ssl, sys\n"
        "assert ssl.OPENSSL_VERSION\n"
        "with sqlite3.connect(':memory:') as db:\n"
        "    assert db.execute('select 6 * 7').fetchone()[0] == 42\n"
        "print(math.isqrt(json.loads(sys.stdin.read())['value']))\n",
        stdin='{"value": 1764}',
        expected_output="42\n",
    )
    assert result["status"]["id"] == 3, result
    assert result["stdout"] == "42\n"


def test_wrong_answer(runner):
    result = submit(runner, "print(41)", expected_output="42\n")
    assert result["status"]["id"] == 4, result


def test_runtime_error(runner):
    result = submit(runner, "raise ValueError('runner integration failure')")
    assert result["status"]["id"] == 11, result
    assert "ValueError: runner integration failure" in result["stderr"]


def test_cpu_limit(runner):
    result = submit(
        runner,
        "while True:\n    pass\n",
        cpu_time_limit=0.5,
        cpu_extra_time=0,
        wall_time_limit=5,
    )
    assert result["status"]["id"] == 5, result
    assert 0 <= float(result["time"]) <= 6, result


def test_memory_limit(runner):
    result = submit(
        runner,
        "blocks = []\n"
        "for _ in range(256):\n"
        "    blocks.append(bytearray(1024 * 1024))\n"
        "print('allocation unexpectedly succeeded')\n",
        memory_limit=32768,
        cpu_time_limit=3,
        wall_time_limit=8,
    )
    assert result["status"]["id"] in {7, 11, 12}, result
    assert "allocation unexpectedly succeeded" not in (result["stdout"] or "")
    assert 0 < int(result["memory"]) <= 65536, result


def test_output_file_limit(runner):
    result = submit(
        runner,
        "import os\nfor _ in range(256):\n    os.write(1, b'x' * 4096)\n",
        max_file_size=8,
        wall_time_limit=5,
    )
    assert result["status"]["id"] in {8, 11}, result
    assert 0 < len((result["stdout"] or "").encode()) <= 8 * 1024, result


@pytest.mark.parametrize("path", ["/api", "/run/secrets"])
def test_private_runner_paths_are_inaccessible(runner, path):
    result = submit(
        runner,
        "import os\n"
        "try:\n"
        f"    os.listdir({path!r})\n"
        "except (FileNotFoundError, PermissionError):\n"
        "    print('denied')\n"
        "else:\n"
        "    raise AssertionError('private runner directory is visible')\n",
        expected_output="denied\n",
    )
    assert result["status"]["id"] == 3, result


def test_outbound_network_is_unavailable(runner):
    result = submit(
        runner,
        "import socket\n"
        "with socket.socket() as connection:\n"
        "    connection.settimeout(1)\n"
        "    try:\n"
        "        connection.connect(('1.1.1.1', 443))\n"
        "    except OSError:\n"
        "        print('denied')\n"
        "    else:\n"
        "        raise AssertionError('outbound network is reachable')\n",
        expected_output="denied\n",
        wall_time_limit=5,
    )
    assert result["status"]["id"] == 3, result


@pytest.mark.parametrize(
    "field,value",
    [("enable_network", True), ("language_id", 71), ("additional_files", "UEsFBg==")],
)
def test_unsupported_submission_features_are_rejected(runner, field, value):
    response = runner.post(
        "/submissions?base64_encoded=false&wait=true",
        json={"source_code": "print(42)", field: value},
    )
    assert response.status_code == 422, response.text
    assert field in response.json()["fields"]
