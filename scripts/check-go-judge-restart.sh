#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
compose=(docker compose --env-file /dev/null -p techniview-go-restart
  -f compose.integration.yml -f compose.benchmark.yml -f compose.go-judge-experiment.yml)
export LOAD_JUDGE0_WORKERS=8
cleanup() { status=$?; trap - EXIT; "${compose[@]}" logs --no-color; "${compose[@]}" --profile callback-outbox down --volumes --remove-orphans; exit "$status"; }
trap cleanup EXIT
"${compose[@]}" up -d --wait --wait-timeout 180 judge workers
"${compose[@]}" run --rm --no-deps tests python -c '
import time,urllib.request
for i in range(90):
 try: urllib.request.urlopen("http://judge:2358/about").read();break
 except OSError:
  if i==89: raise
  time.sleep(1)'
probe=("${compose[@]}" run --rm --no-deps --volume "$PWD/backend/performance/restart_probe.py:/app/performance/restart_probe.py:ro" tests python -m performance.restart_probe)
probe_token=$("${probe[@]}" start)
"${compose[@]}" exec -T go-judge /opt/python/bin/python3.14 -c '
import time
from pathlib import Path
for _ in range(100):
 found=False
 for path in Path("/proc").glob("[0-9]*/cmdline"):
  try:
   args=path.read_bytes().split(b"\0")
   started=(path.parent/"root/tmp/techniview-execution-started").exists()
   found=found or (args[0].endswith(b"python3.14") and b"script.py" in args and started)
  except FileNotFoundError: pass
 if found: print("Observed student process before engine interruption");break
 time.sleep(.1)
else: raise AssertionError("Student process was not observed")'
"${compose[@]}" kill -s KILL go-judge
"${probe[@]}" verify "$probe_token"
"${compose[@]}" up -d --wait --wait-timeout 90 go-judge
"${probe[@]}" verify "$probe_token"
"${compose[@]}" run --rm --no-deps tests python -c '
import httpx
r=httpx.post("http://judge:2358/submissions?wait=true&base64_encoded=false",json={"source_code":"print(42)","expected_output":"42\n"},timeout=30)
r.raise_for_status()
assert r.json()["status"]["id"]==3,r.text
print("New execution passed after engine restart; interrupted case stayed terminal")'
