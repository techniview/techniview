#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mode=${1:?Expected a supported runner profile}
compose=(docker compose --env-file /dev/null -p "techniview-verify-$mode"
  -f compose.integration.yml -f compose.benchmark.yml)
base_compose=(docker compose --env-file /dev/null -p "techniview-verify-$mode"
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
  go-judge-group-persistent)
    compose+=(-f compose.go-judge-shared.yml -f compose.group-experiment.yml
      -f compose.persistent-workers.yml)
    export JUDGE0_REUSE_CONNECTIONS=1
    ;;
  *) exit 2 ;;
esac
cleanup() {
  status=$?; trap - EXIT
  mkdir -p benchmark-results/local-runner
  "${compose[@]}" logs --no-color > "benchmark-results/local-runner/verify-$mode-services.log" || true
  "${compose[@]}" --profile callback-outbox down --volumes --remove-orphans || true
  exit "$status"
}
trap cleanup EXIT
"${base_compose[@]}" build workers
"${compose[@]}" build backend tests app_worker judge workers
"${compose[@]}" up -d --wait --wait-timeout 180 --scale app_worker=4 backend judge workers app_worker
"${compose[@]}" run --rm --no-deps tests python -m pytest -v integration -k "${VERIFY_TEST_SELECTOR:-not fifty_near_simultaneous}" --override-ini=pythonpath=.
"${compose[@]}" run --rm --no-deps -e RUNNER_ADAPTER_TESTS=1 judge \
  bundle exec ruby -r ./config/environment scripts/test_go_judge_adapter.rb
