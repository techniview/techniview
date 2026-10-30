"""Real sandbox probes in the disposable integration stack."""

import json
import os
import time
from ipaddress import ip_address
from uuid import uuid4

import pytest
from app.core import go_judge
from app.models import Problem, Submission
from integration import test_submission_mysql as fixtures
from sqlalchemy import select

client = fixtures.client
database = fixtures.database

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1",
    reason="requires direct integration stack",
)


@pytest.mark.parametrize(
    "source,expected,code,cpu,memory",
    [
        ("print(42)", "42", 3, 2, 128000),
        ("print(41)", "42", 4, 2, 128000),
        ('raise ValueError("probe")', "", 11, 2, 128000),
        ("import os; os._exit(7)", "", 11, 2, 128000),
        ("while True: pass", "", 5, 0.1, 128000),
        ('x = bytearray(256*1024*1024); print("bad")', "", 12, 2, 32768),
        ('print("x" * (2*1024*1024))', "", 8, 2, 128000),
        ('import os; print(os.path.exists("/api"))', "False", 3, 2, 128000),
    ],
)
def test_direct_sandbox_limits(source, expected, code, cpu, memory):
    report = go_judge.execute(go_judge.Execution(source, "", expected, cpu, memory))
    if memory == 32768:
        # Strict allocation denial can surface as Python MemoryError or OOM kill.
        assert report["status"]["id"] in (11, 12), report
    elif code == 8:
        # RLIMIT_FSIZE may surface as Python OSError before collector termination.
        assert report["status"]["id"] in (8, 11), report
        assert len(report["stdout"].encode()) <= 1024 * 1024
    else:
        assert report["status"]["id"] == code, report
    assert report["stdout"] != "bad\n"


def test_direct_cases_are_fresh():
    first = (
        "import collections; collections.marker=True; "
        'open("/tmp/marker", "w").write("x")'
    )
    second = (
        'import collections, os; print(hasattr(collections,"marker"), '
        'os.path.exists("/tmp/marker"))'
    )
    assert (
        go_judge.execute(go_judge.Execution(first, "", "", 2, 128000))["status"]["id"]
        == 3
    )
    assert (
        go_judge.execute(go_judge.Execution(second, "", "False False", 2, 128000))[
            "status"
        ]["id"]
        == 3
    )


def test_sandbox_cannot_reach_parent_network_or_read_host_resources():
    parent_targets = json.loads(os.environ["SANDBOX_NETWORK_PROBE_TARGETS"])
    assert {target["name"] for target in parent_targets} == {
        "application_api",
        "database",
        "external_peer",
    }
    for target in parent_targets:
        ip_address(target["address"])

    source = """
import json
import os
import socket

parent_targets = __PARENT_TARGETS__
readable_paths = (
    "/etc/shadow",
    "/root/.ssh/authorized_keys",
    "/proc/1/environ",
    "/proc/1/root/etc/shadow",
    "/sys/fs/cgroup/cgroup.procs",
)
socket_paths = ("/var/run/docker.sock", "/run/docker.sock")
exposed = {
        "readable_host_paths": [],
    "reachable_unix_sockets": [],
    "reachable_tcp_services": [],
    "reachable_parent_services": [],
    "effective_capabilities": None,
    "sandbox_uid": os.geteuid(),
    "sandbox_gid": os.getegid(),
    "runner_env_secret_present": bool(os.environ.get("RUNNER_SECRET_PROBE")),
    "visible_pid1_cmdline": None,
}
with open("/proc/1/cmdline", "rb") as pid1_cmdline:
    exposed["visible_pid1_cmdline"] = " ".join(
        filter(None, pid1_cmdline.read().decode().split("\\0"))
    )
with open("/proc/self/status", encoding="ascii") as status_file:
    for line in status_file:
        if line.startswith("CapEff:"):
            exposed["effective_capabilities"] = line.split()[1]
for path in readable_paths:
    try:
        with open(path, "rb") as resource:
            resource.read(1)
        exposed["readable_host_paths"].append(path)
    except (OSError, PermissionError):
        pass
for path in socket_paths:
    try:
        connection = socket.socket(socket.AF_UNIX)
        connection.settimeout(0.2)
        connection.connect(path)
        connection.close()
        exposed["reachable_unix_sockets"].append(path)
    except OSError:
        pass
for host, port, label in (("127.0.0.1", 5050, "runner_api"),):
    try:
        connection = socket.create_connection((host, port), timeout=0.3)
        connection.close()
        exposed["reachable_tcp_services"].append(label)
    except OSError:
        pass
for target in parent_targets:
    try:
        connection = socket.create_connection(
            (target["address"], target["port"]), timeout=0.3
        )
        connection.close()
        exposed["reachable_parent_services"].append(target["name"])
    except OSError:
        pass
print(json.dumps(exposed, sort_keys=True))
"""
    source = source.replace("__PARENT_TARGETS__", json.dumps(parent_targets))
    expected = (
        '{"effective_capabilities": "0000000000000000", '
        '"reachable_parent_services": [], "reachable_tcp_services": [], '
        '"reachable_unix_sockets": [], '
        '"readable_host_paths": [], "runner_env_secret_present": false, '
        '"sandbox_gid": 1536, "sandbox_uid": 1536, '
        '"visible_pid1_cmdline": "/proc/self/exe container_init"}'
    )
    report = go_judge.execute(go_judge.Execution(source, "", expected, 2, 128000))
    assert report["status"]["id"] == 3, report
    exposed = json.loads(report["stdout"])
    assert exposed == {
        "effective_capabilities": "0000000000000000",
        "reachable_parent_services": [],
        "reachable_tcp_services": [],
        "reachable_unix_sockets": [],
        "readable_host_paths": [],
        "runner_env_secret_present": False,
        "sandbox_gid": 1536,
        "sandbox_uid": 1536,
        "visible_pid1_cmdline": "/proc/self/exe container_init",
    }, exposed


@pytest.mark.skipif(
    os.getenv("DIRECT_RESTART_TEST") != "1", reason="requires host restart control"
)
def test_direct_worker_restart(database, client):
    problem = database.scalar(select(Problem).where(Problem.title == "Sum a List"))
    response = client.post(
        "/api/submissions",
        headers={"Idempotency-Key": uuid4().hex},
        json={
            "problem_id": problem.id,
            "source_code": (
                "import time\ndef sum_list(v):\n    time.sleep(3)\n    return sum(v)"
            ),
        },
    )
    response.raise_for_status()
    sid = response.json()["id"]
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        database.rollback()
        database.expire_all()
        row = database.get(Submission, sid)
        if any(c.dispatch_started_at for c in row.case_results):
            print("DIRECT_RESTART_READY", flush=True)
            break
        time.sleep(0.05)
    else:
        pytest.fail("case was never dispatched")
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        database.rollback()
        database.expire_all()
        row = database.get(Submission, sid)
        if row.completed_at:
            break
        time.sleep(0.2)
    else:
        pytest.fail("submission never recovered")
    assert row.failure_code == "runner_outcome_unknown"
    assert all(c.dispatch_attempt_count == 1 for c in row.case_results)
    assert any(c.judge0_status_id == 13 for c in row.case_results)
    assert any(c.judge0_status_id == 3 for c in row.case_results)
