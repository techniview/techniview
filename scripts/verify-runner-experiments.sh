#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
compose=(docker compose --env-file /dev/null -p techniview-runner-verify
  -f compose.integration.yml -f compose.benchmark.yml)
export LOAD_JUDGE0_WORKERS=1 JUDGE0_REUSE_CONNECTIONS=0 RUNNER_CALLBACK_OUTBOX=0
cleanup() {
  status=$?
  trap - EXIT
  "${compose[@]}" logs --no-color > benchmark-results/local-runner/verification-services.log || true
  "${compose[@]}" down --volumes --remove-orphans || true
  exit "$status"
}
trap cleanup EXIT
"${compose[@]}" build backend tests app_worker judge workers
"${compose[@]}" up -d --wait --wait-timeout 180 backend judge workers app_worker
"${compose[@]}" run --rm --no-deps tests python -m pytest -v integration -k "not fifty_near_simultaneous" --override-ini=pythonpath=.
"${compose[@]}" run --rm --no-deps -e RUNNER_OUTBOX_TESTS=1 -e RUNNER_CALLBACK_OUTBOX=1 \
  judge bundle exec ruby -r ./config/environment scripts/test_callback_delivery.rb
for phase in setup recover; do
  "${compose[@]}" run --rm --no-deps -e RUNNER_OUTBOX_TESTS=1 \
    --volume "$PWD/internal-judge0-fork/api/scripts/test_callback_restart.rb:/api/scripts/test_callback_restart.rb:ro" \
    judge bundle exec ruby -r ./config/environment scripts/test_callback_restart.rb "$phase"
done
