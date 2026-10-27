#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
compose=(docker compose --env-file /dev/null -p techniview-runner-restart
  -f compose.integration.yml -f compose.benchmark.yml)
export LOAD_JUDGE0_WORKERS=8
cleanup() { status=$?; trap - EXIT; "${compose[@]}" logs --no-color; "${compose[@]}" down --volumes --remove-orphans; exit "$status"; }
trap cleanup EXIT
"${compose[@]}" up -d --wait --wait-timeout 180 judge workers
check='import json,time,urllib.request
healthy=0
for _ in range(100):
 try:
  rows=json.load(urllib.request.urlopen("http://judge:2358/workers"))
  count=sum(r["available"] for r in rows)
  healthy=healthy+1 if count==8 else 0
  if healthy>=10: print("Exactly eight registered workers for ten consecutive samples");break
 except OSError: pass
 time.sleep(0.2)
else: raise AssertionError(rows)'
"${compose[@]}" run --rm --no-deps tests python -c "$check"
"${compose[@]}" up -d --no-deps --force-recreate workers
"${compose[@]}" run --rm --no-deps tests python -c "$check"
shared=("${compose[@]}" -f compose.go-judge-shared.yml)
"${compose[@]}" stop workers
"${shared[@]}" up -d --wait --wait-timeout 90 --force-recreate workers
"${compose[@]}" run --rm --no-deps tests python -c "$check"
"${shared[@]}" stop workers
"${compose[@]}" up -d --wait --wait-timeout 90 --force-recreate workers
"${compose[@]}" run --rm --no-deps tests python -c "$check"
