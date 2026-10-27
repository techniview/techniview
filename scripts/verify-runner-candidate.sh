#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mode=${1:?Expected baseline, dispatch, go-judge, go-judge-shared, go-pooled or combined}
compose=(docker compose --env-file /dev/null -p "techniview-verify-$mode"
  -f compose.integration.yml -f compose.benchmark.yml)
export LOAD_JUDGE0_WORKERS=${VERIFY_RUNNER_WORKERS:-8} JUDGE0_REUSE_CONNECTIONS=0 RUNNER_CALLBACK_OUTBOX=0 WORKER_DISPATCH_CONCURRENCY=1
case "$mode" in
  baseline) ;;
  dispatch) export WORKER_DISPATCH_CONCURRENCY=4 ;;
  go-judge) compose+=(-f compose.go-judge-experiment.yml) ;;
  go-judge-shared) compose+=(-f compose.go-judge-shared.yml) ;;
  go-pooled)
    compose+=(-f compose.go-judge-shared.yml)
    export JUDGE0_REUSE_CONNECTIONS=1
    ;;
  combined)
    compose+=(-f compose.go-judge-shared.yml)
    export JUDGE0_REUSE_CONNECTIONS=1 WORKER_DISPATCH_CONCURRENCY=4
    ;;
  *) exit 2 ;;
esac
cleanup() {
  status=$?; trap - EXIT
  "${compose[@]}" logs --no-color > "benchmark-results/local-runner/resume/verify-$mode-services.log" || true
  "${compose[@]}" --profile callback-outbox down --volumes --remove-orphans || true
  exit "$status"
}
trap cleanup EXIT
"${compose[@]}" up -d --wait --wait-timeout 180 --scale app_worker=4 backend judge workers app_worker
"${compose[@]}" run --rm --no-deps --volume "$PWD/backend/integration/test_runner_isolation.py:/app/integration/test_runner_isolation.py:ro" tests python -m pytest -v integration -k "${VERIFY_TEST_SELECTOR:-not fifty_near_simultaneous}" --override-ini=pythonpath=.
"${compose[@]}" run --rm --no-deps -e RUNNER_ADAPTER_TESTS=1 judge \
  bundle exec ruby -r ./config/environment scripts/test_go_judge_adapter.rb
