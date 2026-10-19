#!/usr/bin/env bash
set -euo pipefail

results_directory=${1:?Results directory is required}
mkdir -p "$results_directory"
results_file="$results_directory/results.jsonl"
: > "$results_file"

for workers in 1 2 4 8; do
  for repetition in 1 2 3; do
    profile="judge0-${workers}-workers-run-${repetition}"
    log_file="$results_directory/${profile}.log"
    result_file="$results_directory/${profile}.json"

    echo "Running $profile"
    make load-test \
      LOAD_STUDENTS=100 \
      LOAD_CONCURRENCY=100 \
      LOAD_CASES_PER_SUBMISSION=1 \
      LOAD_APP_WORKERS=4 \
      LOAD_JUDGE0_WORKERS="$workers" \
      2>&1 | tee "$log_file"

    sed -n '/^{.*}$/p' "$log_file" | tail -n 1 > "$result_file"
    python3 -m json.tool "$result_file" >/dev/null
    cat "$result_file" >> "$results_file"
  done
done
