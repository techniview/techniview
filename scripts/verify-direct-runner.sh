#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

project=techniview-direct-restart
results="$ROOT/test-results/direct-restart"
compose=(docker compose --env-file /dev/null -p "$project" -f compose.integration.yml -f compose.direct-experiment.yml)
base_compose=("${compose[@]}")

mkdir -p "$results"
rm -f "$results/restart-test.log"
export DIRECT_EXECUTION_SLOTS=4 DIRECT_WORKER_PROCESSES=1 RUNNER_CPU_LIMIT=6

running=$("${base_compose[@]}" ps --status running -q)
if [[ -n "$running" ]]; then
  echo "Compose project $project already has running containers; inspect them first." >&2
  exit 2
fi

cleanup() {
  status=$?
  trap - EXIT
  mkdir -p "$results"
  "${compose[@]}" logs --no-color > "$results/services.log" || true
  "${compose[@]}" down --volumes --remove-orphans || true
  exit "$status"
}
trap cleanup EXIT

"${compose[@]}" build backend tests app_worker go-judge
"${compose[@]}" up -d --wait --wait-timeout 180 --scale app_worker=4 \
  backend go-judge app_worker

test_log="$results/restart-test.log"
mkdir -p "$results"
"${compose[@]}" run --rm --no-deps -e DIRECT_RESTART_TEST=1 tests \
  python -m pytest -v -s \
  integration/test_direct_runner.py::test_direct_worker_restart \
  --override-ini=pythonpath=. > "$test_log" 2>&1 &
test_pid=$!

deadline=$((SECONDS + 90))
while ! grep -q 'DIRECT_RESTART_READY' "$test_log"; do
  if ! kill -0 "$test_pid" 2>/dev/null; then
    wait "$test_pid" || status=$?
    cat "$test_log"
    exit "${status:-1}"
  fi
  if (( SECONDS >= deadline )); then
    echo "Restart test did not reach a running group within 90 seconds." >&2
    cat "$test_log"
    exit 1
  fi
  sleep 0.2
done

echo "Interrupting the app workers while a direct case is executing."
"${compose[@]}" kill -s SIGKILL app_worker
sleep 3
"${compose[@]}" up -d --wait --wait-timeout 120 --scale app_worker=4 app_worker

if wait "$test_pid"; then
  echo "Direct worker restart recovery check passed."
else
  status=$?
  cat "$test_log"
  exit "$status"
fi
