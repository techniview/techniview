#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

project=techniview-restart-verify
results="$ROOT/benchmark-results/local-runner/go-judge-worker-restart-verification"
compose=(docker compose --env-file /dev/null -p "$project"
  -f compose.integration.yml
  -f compose.benchmark.yml
  -f compose.go-judge-shared.yml
  -f compose.group-experiment.yml
  -f compose.persistent-workers.yml)
base_compose=(docker compose --env-file /dev/null -p "$project"
  -f compose.integration.yml -f compose.benchmark.yml)

mkdir -p "$results"
rm -f "$results/restart-test.log"
export LOAD_JUDGE0_WORKERS=8
export JUDGE0_REUSE_CONNECTIONS=1
export RUNNER_CALLBACK_OUTBOX=0
export WORKER_DISPATCH_CONCURRENCY=1

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
  "${compose[@]}" --profile callback-outbox down --volumes --remove-orphans || true
  exit "$status"
}
trap cleanup EXIT

"${base_compose[@]}" build workers
"${compose[@]}" build backend tests app_worker judge workers
"${compose[@]}" up -d --wait --wait-timeout 180 --scale app_worker=4 \
  backend judge workers app_worker

test_log="$results/restart-test.log"
mkdir -p "$results"
"${compose[@]}" run --rm --no-deps -e RUNNER_RESTART_TEST=1 tests \
  python -m pytest -v -s \
  integration/test_grouped_runner.py::test_worker_restart_does_not_retry_ambiguous_group_case \
  --override-ini=pythonpath=. > "$test_log" 2>&1 &
test_pid=$!

deadline=$((SECONDS + 90))
while ! grep -q 'GO_JUDGE_RESTART_READY' "$test_log"; do
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

echo "Interrupting the go-judge workers while a grouped case is executing."
"${compose[@]}" stop --timeout 1 workers
sleep 3
"${compose[@]}" up -d --wait --wait-timeout 120 workers

if wait "$test_pid"; then
  echo "go-judge worker restart recovery check passed."
else
  status=$?
  cat "$test_log"
  exit "$status"
fi
