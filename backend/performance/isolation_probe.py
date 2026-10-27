"""Check environment reuse and descendant cleanup in the local go-judge service."""

import json
import time
import urllib.request
from pathlib import Path

URL = "http://127.0.0.1:5050/run"
MARKER = b"techniview-leftover-probe"


def execute(source):
    command = {
        "args": ["/opt/python/bin/python3.14", "-I", "-B", "script.py"],
        "env": ["HOME=/tmp", "LANG=C.UTF-8"],
        "files": [
            {"content": ""},
            {"name": "stdout", "max": 4096},
            {"name": "stderr", "max": 4096},
        ],
        "copyIn": {"script.py": {"content": source}},
        "cpuLimit": 2_000_000_000,
        "clockLimit": 5_000_000_000,
        "memoryLimit": 128000 * 1024,
        "procLimit": 60,
    }
    request = urllib.request.Request(
        URL,
        data=json.dumps({"cmd": [command]}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)[0]


def main():
    for _ in range(16):
        result = execute(
            "import os, collections\n"
            "assert not os.path.exists('/tmp/techniview-reuse-state')\n"
            "assert not hasattr(collections, 'techniview_reuse_state')\n"
            "open('/tmp/techniview-reuse-state','w').write('state')\n"
            "collections.techniview_reuse_state = True\n"
            "print('clean')\n"
        )
        assert result["status"] == "Accepted", result
        assert result["files"]["stdout"] == "clean\n", result
    result = execute(
        "import subprocess, sys\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)', "
        "'techniview-leftover-probe'], stdin=subprocess.DEVNULL, "
        "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        "print('parent finished')\n"
    )
    assert result["status"] in {"Accepted", "Time Limit Exceeded"}, result
    deadline = time.monotonic() + 5
    while True:
        found = False
        for path in Path("/proc").glob("[0-9]*/cmdline"):
            try:
                found = found or MARKER in path.read_bytes().split(b"\0")
            except FileNotFoundError:
                pass
        if not found:
            break
        assert time.monotonic() < deadline, (
            "Student descendant survived sandbox cleanup"
        )
        time.sleep(0.1)
    print(
        json.dumps(
            {
                "environment_reuse_cases_passed": 16,
                "descendant_cleanup_passed": True,
                "descendant_case_status": result["status"],
            }
        )
    )


if __name__ == "__main__":
    main()
