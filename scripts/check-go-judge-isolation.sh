#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
compose=(docker compose --env-file /dev/null -p techniview-go-isolation
  -f compose.integration.yml -f compose.benchmark.yml -f compose.go-judge-shared.yml)
export LOAD_JUDGE0_WORKERS=8
cleanup() { status=$?; trap - EXIT; "${compose[@]}" logs --no-color; "${compose[@]}" --profile callback-outbox down --volumes --remove-orphans; exit "$status"; }
trap cleanup EXIT
"${compose[@]}" up -d --wait --wait-timeout 90 judge workers
"${compose[@]}" exec -T workers /opt/python/bin/python3.14 - < backend/performance/isolation_probe.py
